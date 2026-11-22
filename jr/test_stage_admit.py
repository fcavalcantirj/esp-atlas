"""Tests for jr/stage_admit.py — the Track A admission stage, end to end on a tmp tree with
fake network. The tmp root carries a COPY of the real data/boards + data/modules (the stage
resolves chips against the tree it writes), so nothing real is written."""
from __future__ import annotations

import autoreview
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import device_evidence
import memory
import pending_prs
import safe_fetch
import stage_admit
import tick
import tools
import writers
from budget import Budget
from test_device_evidence import VALID_S3_IMAGE

REPO = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)

SEED_FW = """\
---
id: seed-original
type: firmware
name: Seed Original
url: https://github.com/o/original
category: multi
socs:
- esp32
sources:
- field: '*'
  url: https://github.com/o/original
  verified: '2026-09-01'
---

Seed.
"""


def _meta(full_name, stars=30, forks=0, fork=False, source=None, archived=False, description=None,
          license="MIT", rid=1, homepage=None):
    return {"full_name": full_name, "description": description, "license": {"spdx_id": license},
            "topics": [], "homepage": homepage, "default_branch": "main",
            "stargazers_count": stars, "archived": archived, "forks_count": forks,
            "id": rid, "fork": fork,
            "source": {"full_name": source} if source else None,
            "parent": {"full_name": source} if source else None,
            "pushed_at": "2026-09-01T00:00:00Z", "language": "C"}


def _entry(name, github, category="cardputer", download=100, description=None):
    return {"name": name, "description": description, "category": category, "github": github,
            "download": download}


@pytest.fixture
def root(tmp_path):
    shutil.copytree(REPO / "data" / "boards", tmp_path / "data" / "boards")
    shutil.copytree(REPO / "data" / "modules", tmp_path / "data" / "modules")
    (tmp_path / "data" / "firmware" / "seed-original").mkdir(parents=True)
    (tmp_path / "data" / "firmware" / "seed-original" / "firmware.md").write_text(SEED_FW)
    (tmp_path / "data" / "recipes").mkdir()
    (tmp_path / "jr").mkdir()
    return tmp_path


# The device-build evidence gate (jr/device_evidence.py) reads every candidate's tree: unless a test
# serves its own, a repo has an Arduino sketch whose sketch.yaml names an ESP board (served by the
# esp_sketch_raw fixture), so the gates under test here are the only ones that bite.
DEVICE_TREE = {"tree": [{"path": "src/main.ino", "type": "blob"}, {"path": "src/sketch.yaml", "type": "blob"}], "truncated": False}
pytestmark = pytest.mark.usefixtures("esp_sketch_raw")


def _reply(doc, path):
    """A fake `gh api` reply: a missing doc is 404 (a tree defaults to DEVICE_TREE), a doc
    {"__status__": msg} a failed call with that stderr."""
    if doc is None and "/git/trees/" in path:
        doc = DEVICE_TREE
    if doc is None:
        return SimpleNamespace(returncode=1, stdout="", stderr="404 not found")
    if isinstance(doc, dict) and "__status__" in doc:
        return SimpleNamespace(returncode=1, stdout="", stderr=doc["__status__"])
    return SimpleNamespace(returncode=0, stdout=json.dumps(doc), stderr="")


def _ctx(root, dry_run=False, budget=None, metas=None):
    metas = metas or {}
    budget = budget or Budget(clock=lambda: 0.0)

    def gh(*a):
        return _reply(metas.get(a[1]), a[1])

    return tick.TickContext(root=root, ledger_path=root / "jr" / "proposed_ledger.json", now=NOW,
                            gh=budget.wrap(gh), git=lambda *a: None,
                            budget=budget, dry_run=dry_run, env={})


def _firmware_schema():
    return json.loads((REPO / "schema" / "firmware.schema.json").read_text())


def _read_fm(path):
    import jsonschema
    fm = yaml.safe_load(path.read_text().split("\n---\n")[0].split("---\n", 1)[1])
    jsonschema.validate(fm, _firmware_schema())   # the real schema, additionalProperties false
    return fm


def test_fork_of_catalogued_is_rejected_without_writing(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Fork Tool", "https://github.com/f/fork")])
    metas = {"repos/f/fork": _meta("f/fork", fork=True, source="o/original", rid=11)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.name == "admit" and res.admitted == 0 and res.paths == []
    assert res.rejects == {"fork_of_catalogued": 1}
    assert "fork_of_catalogued" in res.summary
    assert {p.name for p in (root / "data" / "firmware").iterdir()} == {"seed-original"}
    led = memory.load(root / "jr" / "proposed_ledger.json")
    rec = led["by_id"]["fork"]
    assert rec["status"] == "rejected" and rec["repo_id"] == 11
    assert rec["expires"] is not None   # TTL'd, re-checked after SEEN_TTL_DAYS


def test_floor_failing_repo_is_rejected_with_ttl_and_blocked(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Tiny Tool", "https://github.com/t/tiny")])
    metas = {"repos/t/tiny": _meta("t/tiny", stars=3, forks=4, rid=12)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 0 and res.rejects == {"below_floor": 1}
    led = memory.load(root / "jr" / "proposed_ledger.json")
    assert memory.is_blocked(led, repo_id=12, now=NOW)
    rec = led["by_id"]["tiny"]
    assert rec["reason"].startswith("below_floor:") and rec["repo_id"] == 12


def test_editorial_home_class_is_admitted_despite_low_stars_and_forks(root, monkeypatch):
    """RogueDuck class: 6 stars, 3 forks -- below BOTH floors -- but a real independent
    editorial homepage clears it via the third signal, and the live admission path (this
    stage) actually consults it. REGRESSION (floor-enforcement drift, fixed 2026-10-08): the
    homepage that admitted this record must also be STAMPED into the persisted popularity
    snapshot as `editorial_home`, or the OFFLINE audit (scripts/firmware_floor_audit.py, which
    cannot fetch a live homepage) would flag this exact record as below-floor on every
    subsequent tick, discard the worktree, and re-discover/re-reject the candidate forever --
    this is the admit-vs-offline-guard disagreement the stamp closes."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("My Cardputer Tool", "https://github.com/n/newtool")])
    metas = {"repos/n/newtool": _meta("n/newtool", stars=6, forks=3,
                                      homepage="https://ethicalhackersden.org",
                                      description="A Cardputer tool", rid=13)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 1 and res.rejects == {}
    fm = _read_fm(root / "data" / "firmware" / "newtool" / "firmware.md")
    assert fm["popularity"] == {"stars": 6, "forks": 3,
                                "editorial_home": "https://ethicalhackersden.org",
                                "as_of": "2026-09-07"}

    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    import firmware_floor_audit
    report = firmware_floor_audit.audit(data_dir=root / "data")
    assert "newtool" not in {e["id"] for e in report["flagged"]}
    assert "newtool" not in {e["id"] for e in report["unstamped"]}


def test_github_homepage_does_not_rescue_a_below_floor_repo(root, monkeypatch):
    """A homepage pointing back at github.com/github.io is not an independent editorial home --
    still rejected below_floor."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Tiny Tool", "https://github.com/t/tiny")])
    metas = {"repos/t/tiny": _meta("t/tiny", stars=3, forks=4,
                                   homepage="https://t.github.io", rid=12)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 0 and res.rejects == {"below_floor": 1}


def test_admitted_record_is_schema_valid_proposed_and_cited(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("My Cardputer Tool", "https://github.com/n/newtool")])
    metas = {"repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 1 and not res.needs_human and res.rejects == {}
    assert res.paths == ["data/firmware/newtool/firmware.md", "data/recipes/m5cardputer__newtool"]
    # the first recipe lands in the same write, so the record is never an orphan for the guard
    rec = yaml.safe_load((root / "data/recipes/m5cardputer__newtool/recipe.md").read_text().split("\n---\n")[0].split("---\n", 1)[1])
    import jsonschema
    jsonschema.validate(rec, json.loads((REPO / "schema" / "recipe.schema.json").read_text()))
    assert rec["board"] == "m5cardputer" and rec["firmware"] == "newtool" and rec["chip_family"] == "esp32-s3"
    assert rec["status"] == "unverified" and "flash" not in rec
    assert [s["field"] for s in rec["sources"]] == ["*", "board"] and rec["sources"][1]["url"] == "https://github.com/n/newtool"
    assert "names this board as Cardputer in its repository name/description; named in the repository itself, not verified on hardware." in rec["notes"]
    from esp_atlas_core.validate import check_orphan_firmware, known_ids
    assert not [m for m in check_orphan_firmware(known_ids(root / "data")) if "newtool" in m]   # the seed fixture has no recipe by design
    fm = _read_fm(root / "data" / "firmware" / "newtool" / "firmware.md")
    assert fm["id"] == "newtool" and fm["type"] == "firmware"
    assert fm["url"] == "https://github.com/n/newtool" and fm["category"] == "multi"
    assert fm["socs"] == ["esp32-s3"] and fm["maintainer"] == "n"
    assert fm["popularity"] == {"stars": 30, "forks": 0, "as_of": "2026-09-07"}      # the floor gate reads this in CI
    assert fm["sources"] == [
        {"field": "*", "url": "https://github.com/n/newtool", "verified": "2026-09-07"},
        {"field": "popularity", "url": "https://github.com/n/newtool", "verified": "2026-09-07"}]
    body = (root / "data" / "firmware" / "newtool" / "firmware.md").read_text().split("---\n")[-1]
    assert "Admitted by jr/scorer.py rule authored." in body
    led = memory.load(root / "jr" / "proposed_ledger.json")
    assert led["by_id"]["newtool"]["status"] == "proposed"
    assert led["by_id"]["newtool"]["repo_id"] == 13


def test_high_star_admission_flags_needs_human(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Big Tool", "https://github.com/b/big", download=10)])
    metas = {"repos/b/big": _meta("b/big", stars=60000, description="A Cardputer tool", rid=14)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 1 and res.needs_human
    assert "(needs_human)" in res.summary
    body = (root / "data" / "firmware" / "big" / "firmware.md").read_text()
    assert "Admitted by jr/scorer.py rule needs_human." in body


def test_second_run_admits_nothing(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("My Cardputer Tool", "https://github.com/n/newtool")])
    metas = {"repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13)}
    first = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert first.admitted == 1
    second = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert second.admitted == 0 and second.paths == [] and second.rejects == {}
    assert "already decided" in second.summary


def test_budget_stop_line_and_order_are_deterministic(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("B Tool", "https://github.com/n/btool"),
        _entry("A Tool", "https://github.com/n/atool"),
    ])
    metas = {"repos/n/atool": _meta("n/atool", stars=30, description="A Cardputer tool", rid=15),
             "repos/n/btool": _meta("n/btool", stars=30, description="B Cardputer tool", rid=16)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=1)
    assert res.admitted == 1 and res.paths[0] == "data/firmware/atool/firmware.md"  # name, then github
    assert "budget reached (1 admitted)" in res.summary


def test_dry_run_scores_and_reports_but_writes_nothing(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("My Cardputer Tool", "https://github.com/n/newtool"),
        _entry("Tiny Tool", "https://github.com/t/tiny"),
    ])
    metas = {"repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13),
             "repos/t/tiny": _meta("t/tiny", stars=1, forks=0, rid=12)}
    res = stage_admit.run(_ctx(root, metas=metas, dry_run=True), budget=3)
    assert res.admitted == 0 and res.paths == [] and res.rejects == {"below_floor": 1}
    assert "would admit" in res.summary
    assert not (root / "data" / "firmware" / "newtool").exists()
    assert not (root / "jr" / "proposed_ledger.json").exists()   # memory untouched
    writes = {(w["path"], w["field"]) for w in res.would_write}
    assert ("data/firmware/newtool/firmware.md", "*") in writes
    assert ("jr/proposed_ledger.json", "by_id.newtool") in writes
    assert ("jr/proposed_ledger.json", "by_id.tiny") in writes      # the below-floor rejection a real run records
    assert any(p.startswith("data/recipes/") and p.endswith("__newtool/recipe.md") for p, _ in writes)


def test_repo_id_memory_hit_skips_before_fetch(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Bruce 1.12", "https://github.com/BruceDevices/firmware")])
    memory.record_rejected("bruce", "brucedevices/firmware", "duplicate_of bruce (repo_id 795166961)",
                           ttl_days=None, repo_id=795166961,
                           path=root / "jr" / "proposed_ledger.json", now=NOW)
    def boom(*a):
        raise AssertionError("must not fetch a memory-blocked repo")
    c = _ctx(root)
    c = tick.TickContext(root=c.root, ledger_path=c.ledger_path, now=c.now,
                         gh=c.budget.wrap(boom), git=c.git, budget=c.budget, dry_run=False, env=c.env)
    res = stage_admit.run(c, budget=3)
    assert res.admitted == 0 and res.rejects == {} and "already decided" in res.summary


def test_render_firmware_refuses_a_non_schema_id():
    with pytest.raises(ValueError):
        writers.render_firmware({"id": "Bad Id!", "chip": "esp32"}, [], "2026-09-07")


# --- submissions: GitHub issues labelled `submission` -------------------------------------------

ISSUES_PATH = "repos/fcavalcantirj/esp-atlas/issues?labels=submission&state=open&per_page=50"


def _issue(n, body, title="Submission: x"):
    return {"number": n, "title": title, "body": body, "html_url": f"https://github.com/fcavalcantirj/esp-atlas/issues/{n}"}


def _ctx_sub(root, issues, metas=None, api_docs=None, dry_run=False, budget=None):
    """A TickContext whose gh serves the submission issues, repo metas, derive's api paths and
    records every POST/PATCH (comments, closes)."""
    metas, api_docs = metas or {}, api_docs or {}
    budget = budget or Budget(clock=lambda: 0.0)
    calls = []

    def gh(*a):
        calls.append(a)
        if a[:2] == ("api", ISSUES_PATH):
            return SimpleNamespace(returncode=0, stdout=json.dumps(issues), stderr="")
        if a[:2] == ("api", "-X"):
            return SimpleNamespace(returncode=0, stdout="{}", stderr="")
        doc = metas.get(a[1]) if len(a) > 1 else None
        if doc is None:
            doc = api_docs.get(a[1]) if len(a) > 1 else None
        return _reply(doc, a[1] if len(a) > 1 else "")
    ctx = tick.TickContext(root=root, ledger_path=root / "jr" / "proposed_ledger.json", now=NOW,
                           gh=budget.wrap(gh), git=lambda *a: None, budget=budget, dry_run=dry_run, env={})
    ctx.calls = calls   # type: ignore[attr-defined]
    return ctx


def _answers(ctx):
    return [(a[2], a[3], a[5] if len(a) > 5 else None) for a in ctx.calls if a[:2] == ("api", "-X")]


def test_parse_submission_reads_the_issue_form_and_plain_lines():
    assert stage_admit.parse_submission("### Repository URL\n\nhttps://github.com/o/r\n\n### Boards\n\nCardputer, T-Deck\n") == \
        {"github": "https://github.com/o/r", "hint": "Cardputer, T-Deck"}
    assert stage_admit.parse_submission("Repo: https://github.com/o/r.git\nBoards: Cardputer") == {"github": "https://github.com/o/r", "hint": "Cardputer"}
    assert stage_admit.parse_submission("### Boards\n\n_No response_\n\nhttps://github.com/o/r/") == {"github": "https://github.com/o/r", "hint": None}
    assert stage_admit.parse_submission("nothing here") is None and stage_admit.parse_submission(None) is None


def test_submission_with_a_board_hint_is_admitted_first_and_answered(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Zed Cardputer Tool", "https://github.com/z/zed")])
    issues = [_issue(7, "### Repository URL\n\nhttps://github.com/s/subtool\n\n### Boards\n\nM5Stack Cardputer\n")]
    metas = {"repos/s/subtool": _meta("s/subtool", stars=40, description="A writer tool", rid=71),
             "repos/z/zed": _meta("z/zed", stars=30, description="A Cardputer tool", rid=72)}
    ctx = _ctx_sub(root, issues, metas)
    res = stage_admit.run(ctx, budget=3)
    assert res.admitted == 2 and res.rejects == {}
    assert res.paths[0] == "data/firmware/subtool/firmware.md"          # the submission came first
    assert "subtool: +record (submission #7)" in res.summary
    rec = yaml.safe_load((root / "data/recipes/m5cardputer__subtool/recipe.md").read_text().split("\n---\n")[0].split("---\n", 1)[1])
    assert rec["board"] == "m5cardputer" and rec["chip_family"] == "esp32-s3"
    # the board came from the submitter, so the citation is the submission issue, not the repo page
    assert rec["sources"][1] == {"field": "board", "url": "https://github.com/fcavalcantirj/esp-atlas/issues/7", "verified": "2026-09-07"}
    assert "names this board as M5Stack Cardputer in its submission issue; named by the submitter, not verified on hardware." in rec["notes"]
    answers = _answers(ctx)
    assert answers[0][0] == "POST" and answers[0][1] == "repos/fcavalcantirj/esp-atlas/issues/7/comments"
    assert "**Admitted.**" in answers[0][2] and "m5cardputer__subtool" in answers[0][2]
    assert answers[1][:2] == ("PATCH", "repos/fcavalcantirj/esp-atlas/issues/7")
    assert ctx.calls[0][:2] == ("api", ISSUES_PATH)                       # listed before any meta fetch


@pytest.mark.sandbox
def test_submission_without_a_hint_uses_the_repo_build_files_as_evidence(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    issues = [_issue(8, "https://github.com/s/relwriter")]
    metas = {"repos/s/relwriter": _meta("s/relwriter", stars=40, description="Firmware", rid=81)}
    api_docs = {"repos/s/relwriter/releases/latest": {"tag_name": "v1", "assets": [
                    {"name": "relwriter-v1.2.0-m5cardputer.bin", "size": 10, "browser_download_url": "https://github.com/s/relwriter/releases/download/v1/relwriter-v1.2.0-m5cardputer.bin"},
                    {"name": "relwriter-v1.2.0-m5stick_cplus2.bin", "size": 10, "browser_download_url": "https://github.com/s/relwriter/releases/download/v1/relwriter-v1.2.0-m5stick_cplus2.bin"}]},
                "repos/s/relwriter/git/trees/main?recursive=1": {"tree": [{"path": "README.md", "type": "blob"}], "truncated": False}}
    api_docs["repos/s/relwriter/releases?per_page=10"] = [api_docs["repos/s/relwriter/releases/latest"]]   # the evidence gate's read
    monkeypatch.setattr(device_evidence, "default_fetch", lambda url: safe_fetch.Fetched(VALID_S3_IMAGE, url=url))   # the gate's GET: a whole S3 image
    ctx = _ctx_sub(root, issues, metas, api_docs)
    res = stage_admit.run(ctx, budget=1, raw=lambda u: None)          # no network: raw files absent
    assert res.admitted == 1 and "relwriter: +record (submission #8)" in res.summary
    rec = yaml.safe_load((root / "data/recipes/m5cardputer__relwriter/recipe.md").read_text().split("\n---\n")[0].split("---\n", 1)[1])
    assert rec["sources"][1]["url"] == "https://github.com/s/relwriter/releases/tag/v1"      # the release page that lists the asset
    assert rec["flash"] == {"method": "release-bin"} and "in its release" in rec["notes"]
    assert any(a[:2] == ("api", "repos/s/relwriter/releases/latest") for a in ctx.calls)   # derive ran, counted


def test_submission_below_the_floor_is_answered_with_the_rule_and_closed(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    issues = [_issue(9, "https://github.com/s/tiny\nBoards: Cardputer")]
    metas = {"repos/s/tiny": _meta("s/tiny", stars=3, forks=0, rid=91)}
    ctx = _ctx_sub(root, issues, metas)
    res = stage_admit.run(ctx, budget=1)
    assert res.admitted == 0 and res.rejects == {"below_floor": 1}
    assert "tiny: skip below_floor (submission #9)" in res.summary          # a submission's skip is worth a line
    a = _answers(ctx)
    assert "**Not admitted** — `below_floor: 3 stars / 0 forks`" in a[0][2] and "25 stars or 25 forks" in a[0][2]
    assert a[1][0] == "PATCH"
    assert memory.is_blocked(memory.load(root / "jr" / "proposed_ledger.json"), repo="s/tiny", now=NOW)


def test_submission_without_a_repo_url_is_invalid_and_closed(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    ctx = _ctx_sub(root, [_issue(10, "please add my thing")])
    res = stage_admit.run(ctx, budget=1)
    assert res.rejects == {"invalid": 1} and "submission #10: invalid" in res.summary
    a = _answers(ctx)
    assert "`invalid: no github.com/owner/repo URL" in a[0][2] and a[1][0] == "PATCH"


def test_submission_already_decided_is_answered_from_memory_without_a_fetch(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    memory.record_rejected("tiny", "s/tiny", "below_floor: 3 stars / 0 forks", ttl_days=30, path=root / "jr" / "proposed_ledger.json", now=NOW)
    ctx = _ctx_sub(root, [_issue(11, "https://github.com/s/tiny")])
    res = stage_admit.run(ctx, budget=1)
    assert "submission #11: already decided" in res.summary
    a = _answers(ctx)
    assert "already_decided: below_floor" in a[0][2] and a[1][0] == "PATCH"
    assert not any(a[:2] == ("api", "repos/s/tiny") for a in ctx.calls)


def test_submission_dry_run_scores_but_never_comments_or_closes(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    issues = [_issue(12, "https://github.com/s/subtool\nBoards: Cardputer")]
    metas = {"repos/s/subtool": _meta("s/subtool", stars=40, rid=121)}
    ctx = _ctx_sub(root, issues, metas, dry_run=True)
    res = stage_admit.run(ctx, budget=1)
    assert "subtool: would admit (submission #12)" in res.summary
    assert _answers(ctx) == [] and not (root / "data/firmware/subtool").exists()


def test_submission_defers_the_derive_when_the_budget_cannot_afford_it(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    issues = [_issue(13, "https://github.com/s/relwriter")]
    metas = {"repos/s/relwriter": _meta("s/relwriter", stars=40, rid=131)}
    ctx = _ctx_sub(root, issues, metas, budget=Budget(max_calls=20, clock=lambda: 0.0))
    res = stage_admit.run(ctx, budget=1, raw=lambda u: None)
    assert "submission #13: deferred, tick budget low for a derive" in res.summary
    assert _answers(ctx) == [] and res.admitted == 0


def test_scorer_uses_the_board_hint_only_as_the_last_fallback():
    import scorer
    meta = {"full_name": "s/x", "stars": 40, "forks": 1, "description": "A writer tool", "license": "MIT", "fork": False}
    entry = {"name": "Scribbler", "github": "https://github.com/s/x", "category": None, "download": None}
    assert scorer.score_entry(entry, meta, set(), set(), {})["reason"].startswith("no_board_evidence")
    res = scorer.score_entry(entry, meta, set(), set(), {}, board_hint="m5cardputer")
    assert res["decision"] == "authored" and res["record"]["board"] == "m5cardputer" and res["record"]["chip"] == "esp32-s3"
    named = scorer.score_entry(dict(entry, name="Scribbler for Cardputer"), meta, set(), set(), {}, board_hint="lolin-d32")
    assert named["record"]["board"] == "m5cardputer"                 # a device named in the text still wins over the hint


def test_launcher_skips_are_one_aggregate_line_never_one_per_entry(root, monkeypatch):
    """PR #149's body listed 313 launcher skips one by one — unreadable. Counts, sorted by size."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("", "https://github.com/n/nameless"), _entry("", ""), _entry("Tiny Cardputer", "https://github.com/t/tiny")])
    metas = {"repos/t/tiny": _meta("t/tiny", stars=1, forks=0, rid=12)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    # the empty-github entry has no fid to key it by: a counted `unkeyed` skip, never a ledger row (G1b)
    assert res.summary == ("backlog 2 undecided (top: n/nameless, 100 downloads); "
                           "skipped 3 launcher repos: below_floor 1, repo_unresolved 1, unkeyed 1")
    assert res.rejects == {"repo_unresolved": 1, "below_floor": 1, "unkeyed": 1}
    assert ": skip" not in res.summary


def test_launcher_entries_with_an_unresolvable_empty_repo_never_leave_a_falsy_key_in_the_ledger(root, monkeypatch):
    """jr/proposed_ledger.json shipped a record keyed by '' once (id empty, repo empty), and
    scripts/ledger_guard.py then refused every tick PR with "bad key". The admission stage must
    never write a ledger record under a falsy id, whatever the launcher entry looks like. G1b: nor
    under an empty repo — the "(unnamed entry)" row with repo '' every tick is gone too."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("", "")])
    res = stage_admit.run(_ctx(root), budget=1)
    assert res.rejects == {"unkeyed": 1}
    led = memory.load(root / "jr" / "proposed_ledger.json")
    assert "" not in led["by_id"] and "(unnamed entry)" not in led["by_id"]
    assert all(rec.get("repo") for rec in led["by_id"].values())


def test_admit_stops_scanning_the_launcher_at_its_call_share_but_still_answers_submissions(root, monkeypatch):
    """22:00 UTC tick: admit spent all 146 calls scanning the backlog and boardmap got none."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry(f"Tool {i}", f"https://github.com/l/tool{i}") for i in range(20)])
    metas = {f"repos/l/tool{i}": _meta(f"l/tool{i}", stars=1, forks=0, rid=100 + i) for i in range(20)}
    issues = [_issue(30, "https://github.com/s/subtool\nBoards: Cardputer")]
    metas["repos/s/subtool"] = _meta("s/subtool", stars=40, rid=301)
    b = Budget(max_calls=150, clock=lambda: 0.0)
    ctx = _ctx_sub(root, issues, metas, budget=b)
    res = stage_admit.run(ctx, budget=5, call_share=0.05)          # 5% of 150 = 7 calls for the launcher scan
    assert "subtool: +record (submission #30)" in res.summary        # the submission was answered regardless
    assert "admit's call share used (7 of the tick's calls); the rest is Track B's" in res.summary
    assert b.calls <= 7 + 3 + 2                                       # issues list + submission meta + a few launcher metas
    assert res.rejects.get("below_floor", 0) < 20                     # most of the backlog was left for the next tick


# --- stable repository identity (jr/pending_prs.py): the fetched GitHub id is matched before the slug ----

def _held_as(fid, owner_repo, rid):
    """A pending index whose open tick PR #1500 holds `fid`, verified as repository `rid` (by load(),
    from the ledger committed at its head: `_identities`)."""
    body = pending_prs.render_identity([{"kind": "firmware", "id": fid, "url": f"https://github.com/{owner_repo}",
                                         "repo_id": rid}])
    pr = {"number": 1500, "headRefName": "jr/tick-20261107-0300", "body": body, "_identities": {fid: (rid, owner_repo)},
          "files": [{"path": f"data/firmware/{fid}/firmware.md"}, {"path": f"data/recipes/m5cardputer__{fid}/recipe.md"}]}
    return pending_prs.build([pr], [], NOW)


def test_a_submitted_repository_renamed_since_its_pr_is_answered_held_and_closed(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    ctx = _ctx_sub(root, [_issue(12, "https://github.com/n/newtool\nBoards: Cardputer")],
                   {"repos/n/newtool": _meta("n/newtool", stars=30, rid=4242)})
    ctx.pending = _held_as("oldtool", "n/oldtool", 4242)
    res = stage_admit.run(ctx, budget=1)
    assert res.admitted == 0 and res.paths == [] and res.rejects == {"already_proposed": 1}
    a = _answers(ctx)
    assert "already_proposed" in a[0][2] and "oldtool" in a[0][2] and "4242" in a[0][2] and a[1][0] == "PATCH"


def test_a_submission_whose_slug_is_held_under_another_id_is_left_open_unanswered(root, monkeypatch):
    """Identity ambiguity is not a decision: the submitter's issue stays open (submissions are read
    from open issues only) and is looked at again once the hold ends."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    ctx = _ctx_sub(root, [_issue(13, "https://github.com/m/newtool\nBoards: Cardputer")],
                   {"repos/m/newtool": _meta("m/newtool", stars=30, rid=7777)})
    ctx.pending = _held_as("newtool", "n/newtool", 4242)
    res = stage_admit.run(ctx, budget=1)
    assert res.admitted == 0 and res.paths == [] and res.rejects == {"identity_ambiguous": 1}
    assert _answers(ctx) == []
    assert "submission #13: deferred, identity_ambiguous" in res.summary and "7777" in res.summary


def test_a_dry_run_never_would_admit_a_held_repository_renamed_upstream(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        {"name": "New Tool", "description": "A Cardputer tool", "category": "cardputer",
         "github": "https://github.com/n/newtool", "download": 100}])
    ctx = _ctx_sub(root, [], {"repos/n/newtool": _meta("n/newtool", stars=30, rid=4242)}, dry_run=True)
    ctx.pending = _held_as("oldtool", "n/oldtool", 4242)
    res = stage_admit.run(ctx, budget=1)
    assert res.rejects == {"already_proposed": 1} and not res.would_write
    assert "renamed newtool" in res.summary


# --- the admit wall (2026-11-14): a catalogued repository never spends the launcher scan's call share ----
# Every tick from 2026-11-12 to 2026-11-14 read "admitted 0 · stopped before brucedevices/firmware":
# a repo whose ledger record is `merged` was fetched again on every tick (only blocked/seen records
# skip for free, and memory._write refuses an already_catalogued rejection over a merged record),
# Bruce alone has ~35 launcher entries, and the ~46-call share ran out inside them every hour.

def _merged(fid, owner_repo, rid, root):
    path = root / "jr" / "proposed_ledger.json"
    memory.record_proposed(fid, owner_repo, pr_ref="#1", repo_id=rid, path=path, now=NOW)
    memory.reconcile_merged({fid}, path=path, now=NOW)


def _counting_ctx(root, metas, budget, dry_run=False):
    """_ctx whose gh records every path it is asked for."""
    asked = []

    def gh(*a):
        asked.append(a[1] if len(a) > 1 else "")
        return _reply(metas.get(a[1]), a[1])

    ctx = tick.TickContext(root=root, ledger_path=root / "jr" / "proposed_ledger.json", now=NOW,
                           gh=budget.wrap(gh), git=lambda *a: None, budget=budget, dry_run=dry_run, env={})
    return ctx, asked


def test_a_merged_catalogued_repository_costs_no_call_and_never_starves_the_scan(root, monkeypatch):
    _merged("seed-original", "o/original", 7001, root)
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: (
        [_entry(f"Aaa Seed {i:02}", "https://github.com/o/original") for i in range(30)]
        + [_entry("Zed Cardputer Tool", "https://github.com/n/newtool")]))
    metas = {"repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13)}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
    res = stage_admit.run(ctx, budget=3, call_share=0.05)            # 5% of 150 = 7 calls for the scan
    assert "repos/o/original" not in asked                           # the catalogued repo is decided for free
    assert res.admitted == 1 and "data/firmware/newtool/firmware.md" in res.paths
    assert res.rejects.get("already_catalogued") == 1                # 30 entries of one repo: one free decision
    assert "call share used" not in res.summary


def test_a_catalogued_repository_with_no_known_id_is_fetched_once_and_its_id_recorded(root, monkeypatch):
    """The free skip needs the repo's GitHub id in a live ledger record: that id is the rename-proof
    identity net (_catalogued_ids). With none, the repo is fetched as before and the id recorded."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Seed", "https://github.com/o/original")])
    metas = {"repos/o/original": _meta("o/original", rid=7002)}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
    first = stage_admit.run(ctx, budget=3)
    assert asked.count("repos/o/original") == 1 and first.rejects == {"already_catalogued": 1}
    led = memory.load(root / "jr" / "proposed_ledger.json")
    assert memory.lookup(led, repo_id=7002) is not None
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
    stage_admit.run(ctx, budget=3)
    assert "repos/o/original" not in asked


def test_an_expired_record_does_not_count_as_a_known_id(root, monkeypatch):
    path = root / "jr" / "proposed_ledger.json"
    memory.record_rejected("seed-original", "o/original", "already_catalogued: o/original is already in the atlas",
                           ttl_days=1, repo_id=7003, path=path, now=datetime(2026, 8, 1, tzinfo=timezone.utc))
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Seed", "https://github.com/o/original")])
    metas = {"repos/o/original": _meta("o/original", rid=7003)}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
    stage_admit.run(ctx, budget=3)
    assert asked.count("repos/o/original") == 1                      # refreshed, so the identity net stays live


def test_one_paid_fetch_per_repository_per_tick(root, monkeypatch):
    """A dry run writes no rejection, so before this every launcher entry of one repo paid again."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: (
        [_entry(f"Aaa Tiny {i:02}", "https://github.com/t/tiny") for i in range(20)]
        + [_entry("Zed Cardputer Tool", "https://github.com/n/newtool")]))
    metas = {"repos/t/tiny": _meta("t/tiny", stars=1, forks=0, rid=12),
             "repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13)}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0), dry_run=True)
    res = stage_admit.run(ctx, budget=3, call_share=0.05)
    assert asked.count("repos/t/tiny") == 1
    assert "would admit" in res.summary and "call share used" not in res.summary


def test_a_submission_of_a_merged_catalogued_repository_is_answered_without_a_fetch(root, monkeypatch):
    _merged("seed-original", "o/original", 7004, root)
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    ctx = _ctx_sub(root, [_issue(41, "https://github.com/o/original\nBoards: Cardputer")],
                   metas={"repos/o/original": _meta("o/original", rid=7004)})
    stage_admit.run(ctx, budget=3)
    assert not [a for a in ctx.calls if len(a) > 1 and a[1] == "repos/o/original"]
    a = _answers(ctx)
    assert a and "already_catalogued" in a[0][2] and a[1][:2] == ("PATCH", "repos/fcavalcantirj/esp-atlas/issues/41")


# --- the backlog queue (2026-11-14): admit walks the UNDECIDED backlog by downloads, never the alphabet ----
# The alphabetical rescan from "A" with a fixed call share stopped before brucedevices/firmware every
# hour from 2026-11-12: 1,205 undecided repos (1.35 M downloads) were never reached.

def _paid(asked, repo):
    return asked.count(f"repos/{repo}")


def test_the_queue_decides_the_most_downloaded_repo_first(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("Aaa Cardputer Low", "https://github.com/l/low", download=10),
        _entry("Zzz Cardputer High", "https://github.com/h/high", download=5000)])
    metas = {"repos/l/low": _meta("l/low", stars=30, description="A Cardputer tool", rid=21),
             "repos/h/high": _meta("h/high", stars=30, description="A Cardputer tool", rid=22)}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
    res = stage_admit.run(ctx, budget=1)
    assert res.admitted == 1 and res.paths[0] == "data/firmware/high/firmware.md"
    assert _paid(asked, "l/low") == 0


def test_a_repo_listed_many_times_is_one_item_ranked_by_its_total_downloads(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: (
        [_entry(f"Multi Cardputer {i}", "https://github.com/m/multi", download=100) for i in range(5)]
        + [_entry("Aaa Cardputer Single", "https://github.com/s/single", download=400)]))
    metas = {"repos/m/multi": _meta("m/multi", stars=30, description="A Cardputer tool", rid=31),
             "repos/s/single": _meta("s/single", stars=30, description="A Cardputer tool", rid=32)}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
    res = stage_admit.run(ctx, budget=1)
    assert res.paths[0] == "data/firmware/multi/firmware.md" and _paid(asked, "m/multi") == 1


def test_a_refused_decision_is_remembered_so_the_repo_is_never_paid_again(root, monkeypatch):
    """A renamed upstream (pr3y/bruce -> brucedevices/firmware) scores duplicate_of the merged record,
    and memory._write refuses any rejection over `merged`: nothing was remembered, so it was paid
    for on every tick. The decision is now kept under the repo's own note key."""
    _merged("widget", "orig/widget", 9001, root)
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Widget", "https://github.com/fork2/widget")])
    metas = {"repos/fork2/widget": _meta("fork2/widget", stars=30, rid=9001)}
    paid = 0
    for _ in range(3):
        ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
        res = stage_admit.run(ctx, budget=3)
        paid += _paid(asked, "fork2/widget")
    assert paid == 1 and res.backlog == 0
    led = memory.load(root / "jr" / "proposed_ledger.json")
    assert led["by_id"]["widget"]["status"] == "merged"                 # the merged record is untouched
    assert memory.is_blocked(led, repo="fork2/widget", now=NOW)


def test_a_catalogued_repo_without_a_live_id_waits_behind_new_work(root, monkeypatch):
    """The identity refresh (rename net) still happens, but only after the real backlog."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("Aaa Seed", "https://github.com/o/original", download=90000),
        _entry("Zed Cardputer Tool", "https://github.com/n/newtool", download=5)])
    metas = {"repos/o/original": _meta("o/original", rid=7002),
             "repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13)}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
    stage_admit.run(ctx, budget=3)
    assert "repos/n/newtool" in asked and "repos/o/original" in asked
    assert asked.index("repos/n/newtool") < asked.index("repos/o/original")


def test_the_backlog_counts_only_undecided_repos_and_leads_the_summary(root, monkeypatch):
    path = root / "jr" / "proposed_ledger.json"
    memory.record_rejected("blocked", "b/blocked", "below_floor: 1 stars / 0 forks", ttl_days=60, path=path, now=NOW)
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("Seed", "https://github.com/o/original"),                 # catalogued: not backlog
        _entry("Blocked", "https://github.com/b/blocked"),               # decided in memory: not backlog
        _entry("New Cardputer Tool", "https://github.com/n/newtool", download=50),
        _entry("Tiny", "https://github.com/t/tiny", download=20)])
    metas = {"repos/o/original": _meta("o/original", rid=7002),
             "repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13),
             "repos/t/tiny": _meta("t/tiny", stars=1, forks=0, rid=12)}
    ctx, _ = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0), dry_run=True)
    res = stage_admit.run(ctx, budget=3)
    assert res.backlog == 2
    assert res.summary.startswith("backlog 2 undecided (top: n/newtool, 50 downloads)")


def test_a_repo_renamed_upstream_and_decided_under_its_id_is_never_paid_by_the_queue(root, monkeypatch):
    """ji1ore/remotekeyer_wifi became ji1ore/Wifi_Rig_CW (same GitHub id). The old path's record had
    expired; the new path's record, under the same id, was a live below_floor rejection. The queue
    looks records up by PATH, so the old path led the undecided backlog on every tick (2026-11-17:
    12+ ticks, "top: ji1ore/remotekeyer_wifi, 132 downloads"), paid one meta fetch, and the loop's id
    gate then took the decision silently. The queue now takes it for free, by the record's repo_id."""
    from datetime import timedelta
    path = root / "jr" / "proposed_ledger.json"
    memory.record_rejected("old-name", "ji/old-name", "below_floor: 1 stars / 0 forks", ttl_days=30,
                           repo_id=4242, path=path, now=NOW - timedelta(days=60))        # expired
    memory.record_rejected("new-name", "ji/new-name", "below_floor: 1 stars / 0 forks", ttl_days=30,
                           repo_id=4242, path=path, now=NOW)                             # live, same id
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("Old Name", "https://github.com/ji/old-name", download=132),
        _entry("New Cardputer Tool", "https://github.com/n/newtool", download=50)])
    metas = {"repos/ji/old-name": _meta("ji/old-name", stars=1, forks=0, rid=4242),
             "repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13)}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0), dry_run=True)
    res = stage_admit.run(ctx, budget=3)
    assert _paid(asked, "ji/old-name") == 0
    assert res.backlog == 1 and res.summary.startswith("backlog 1 undecided (top: n/newtool, 50 downloads)")


def test_a_renamed_repo_whose_id_record_has_expired_too_is_undecided_again(root, monkeypatch):
    """Both records expired: nothing live decides the repo, so it is back in the backlog and paid once."""
    from datetime import timedelta
    path = root / "jr" / "proposed_ledger.json"
    memory.record_rejected("old-name", "ji/old-name", "below_floor: 1 stars / 0 forks", ttl_days=30,
                           repo_id=4242, path=path, now=NOW - timedelta(days=60))
    memory.record_rejected("new-name", "ji/new-name", "below_floor: 1 stars / 0 forks", ttl_days=30,
                           repo_id=4242, path=path, now=NOW - timedelta(days=45))
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Old Name", "https://github.com/ji/old-name", download=132)])
    metas = {"repos/ji/old-name": _meta("ji/old-name", stars=1, forks=0, rid=4242)}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0), dry_run=True)
    res = stage_admit.run(ctx, budget=3)
    assert res.backlog == 1 and _paid(asked, "ji/old-name") == 1


def test_the_backlog_drains_every_tick_and_no_repo_is_paid_twice(root, monkeypatch):
    """60 below-floor repos plus 3 renamed duplicates of merged records, at a 10-call share: the
    backlog shrinks on every tick until it is empty, and each repo is fetched exactly once."""
    for i in range(3):
        _merged(f"w{i}", f"orig/w{i}", 9100 + i, root)
    entries = [_entry(f"Tool {i:02}", f"https://github.com/d/tool{i:02}", download=1000 - i) for i in range(60)]
    entries += [_entry(f"W {i}", f"https://github.com/fork2/w{i}", download=2000 + i) for i in range(3)]
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: entries)
    metas = {f"repos/d/tool{i:02}": _meta(f"d/tool{i:02}", stars=1, forks=0, rid=200 + i) for i in range(60)}
    metas.update({f"repos/fork2/w{i}": _meta(f"fork2/w{i}", stars=30, rid=9100 + i) for i in range(3)})
    seen, sizes = [], []
    for _ in range(12):
        ctx, asked = _counting_ctx(root, metas, Budget(max_calls=200, clock=lambda: 0.0))
        res = stage_admit.run(ctx, budget=3, call_share=0.05)               # 5% of 200 = 10 calls
        sizes.append(res.backlog)
        seen += [p for p in asked if p.startswith("repos/d/") or p.startswith("repos/fork2/")]
        if res.backlog == 0:
            break
    assert sizes[0] == 63 and sizes[-1] == 0 and len(sizes) <= 10
    assert all(b < a for a, b in zip(sizes, sizes[1:]))                   # strictly shrinking, every tick
    assert len(seen) == len(set(seen)) == 63                              # each repo paid exactly once


def test_a_repo_with_a_merged_record_costs_no_call_even_outside_the_catalog_strings(root, monkeypatch):
    _merged("gone", "m/gone", 9300, root)               # merged, but no data/firmware url names m/gone
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Gone", "https://github.com/m/gone", download=9999)])
    ctx, asked = _counting_ctx(root, {"repos/m/gone": _meta("m/gone", stars=30, rid=9300)}, Budget(max_calls=150, clock=lambda: 0.0))
    res = stage_admit.run(ctx, budget=3)
    assert "repos/m/gone" not in asked and res.backlog == 0


# --- exploration (2026-11-14, owner: "add some random/shuffle, otherwise always fetching the same") ----
# The paid order interleaves the download order with a shuffle seeded by the tick's UTC hour: the most
# wanted repo still goes first, every other paid slot is a random undecided repo, an hour replays the
# same order (reproducible), and the next hour explores different repos.

def _hour(h):
    return NOW.replace(hour=h)


def _fetched_in(root, monkeypatch, entries, metas, hour):
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=200, clock=lambda: 0.0), dry_run=True)
    ctx = tick.TickContext(root=ctx.root, ledger_path=ctx.ledger_path, now=_hour(hour), gh=ctx.gh, git=ctx.git,
                           budget=ctx.budget, dry_run=True, env=ctx.env)
    stage_admit.run(ctx, budget=3, call_share=0.05)                       # 10 calls: a few paid slots
    return [p for p in asked if p.startswith("repos/d/")]


def _forty(monkeypatch):
    entries = [_entry(f"Tool {i:02}", f"https://github.com/d/tool{i:02}", download=10_000 - i) for i in range(40)]
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: entries)
    return entries, {f"repos/d/tool{i:02}": _meta(f"d/tool{i:02}", stars=1, forks=0, rid=400 + i) for i in range(40)}


def test_an_hour_is_reproducible_and_the_most_wanted_repo_goes_first(root, monkeypatch):
    entries, metas = _forty(monkeypatch)
    a = _fetched_in(root, monkeypatch, entries, metas, 10)
    b = _fetched_in(root, monkeypatch, entries, metas, 10)
    assert a == b and a[0] == "repos/d/tool00"


def test_each_hour_explores_repos_the_download_order_alone_would_not_reach(root, monkeypatch):
    """A dry run remembers nothing, so it shows the bare paid order: with the download order alone
    every hour would fetch the very same few repos (any decision that fails to stick would hold the
    head of the queue forever). Six hours must reach well beyond one hour's set."""
    entries, metas = _forty(monkeypatch)
    hours = [_fetched_in(root, monkeypatch, entries, metas, h) for h in range(10, 16)]
    one = set(hours[0])
    union = set().union(*map(set, hours))
    assert all(h[0] == "repos/d/tool00" for h in hours)                    # exploitation: the top is always first
    assert len(union) >= 2 * len(one)                                      # exploration: other repos each hour
    assert any(set(h) != one for h in hours[1:])


def test_the_queue_interleaves_the_download_order_with_a_seeded_shuffle(root):
    catalog = [_entry(f"T{i:02}", f"https://github.com/d/t{i:02}", download=1000 - i) for i in range(30)]
    led = memory.load(root / "jr" / "proposed_ledger.json")
    q1, n1, _ = stage_admit.launcher_queue(catalog, led, set(), NOW, seed="2026-09-07T12")
    q2, _, _ = stage_admit.launcher_queue(catalog, led, set(), NOW, seed="2026-09-07T12")
    q3, _, _ = stage_admit.launcher_queue(catalog, led, set(), NOW, seed="2026-09-07T13")
    names = lambda q: [e["name"] for e in q]
    assert n1 == 30 and names(q1) == names(q2) and names(q1) != names(q3)
    assert sorted(names(q1)) == sorted(names(q3))                          # a permutation: nothing lost or doubled
    for q in (q1, q3):                                                     # the download lane's guarantee:
        for k in range(1, 11):                                             # the top k are always in the first 2k
            assert {f"T{i:02}" for i in range(k)} <= set(names(q)[:2 * k])


# --- the evidence gate on admission (SPEC-jr-review-routing.md §7, step 1) ---------------------------
# A board picked from the repo's name/description passes the same independent check as boardmap's edges,
# reading the README (one counted call). The ask-master class: description "using M5Stack Cardputer",
# README "Cardputer ADV firmware" -> the edge is the ADV, never the original.

import base64  # noqa: E402


def _readme(text):
    return {"content": base64.b64encode(text.encode()).decode()}


def test_admit_writes_the_adv_edge_when_the_readme_targets_only_the_adv(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Desk Tool", "https://github.com/n/desk")])
    metas = {"repos/n/desk": _meta("n/desk", stars=30, description="A desk helper using M5Stack Cardputer", rid=31),
             "repos/n/desk/readme": _readme("Cardputer ADV firmware. Select your Cardputer ADV and click Burn.")}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 1
    assert (root / "data/recipes/m5cardputer-adv__desk/recipe.md").exists()
    assert not (root / "data/recipes/m5cardputer__desk").exists()
    assert f"Evidence check v{autoreview.RULES_VERSION} PASS" in (root / "data/recipes/m5cardputer-adv__desk/recipe.md").read_text()


def test_admit_moves_to_the_adv_when_the_readme_rules_the_original_out(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Pet Tool", "https://github.com/n/pet")])
    metas = {"repos/n/pet": _meta("n/pet", stars=30, description="A tool for the Cardputer", rid=34),
             "repos/n/pet/readme": _readme("**Cardputer ADV only** — the original Cardputer has a different keyboard.")}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 1 and (root / "data/recipes/m5cardputer-adv__pet/recipe.md").exists()
    assert not (root / "data/recipes/m5cardputer__pet").exists()


def test_admit_refuses_an_edge_the_readme_rules_out(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Odd Tool", "https://github.com/n/odd")])
    metas = {"repos/n/odd": _meta("n/odd", stars=30, description="A tool for the Cardputer", rid=32),
             "repos/n/odd/readme": _readme("Runs on the LilyGO T-Deck. Not for the original Cardputer.")}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 0 and res.rejects.get("evidence_check") == 1
    assert not (root / "data/firmware/odd").exists()
    rec = memory.load(root / "jr" / "proposed_ledger.json")["by_id"]["odd"]
    assert rec["status"] == "rejected" and rec["reason"].startswith("evidence_check: ") and rec["expires"]


def test_admit_with_no_readme_still_writes_what_the_description_proves(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("My Cardputer Tool", "https://github.com/n/newtool")])
    metas = {"repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 1 and (root / "data/recipes/m5cardputer__newtool/recipe.md").exists()


def test_admit_writes_the_original_too_when_the_readme_names_both(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Area Tool", "https://github.com/n/area", category="cardputer-adv")])
    metas = {"repos/n/area": _meta("n/area", stars=30, description="An OS for the Cardputer ADV", rid=33),
             "repos/n/area/readme": _readme("Supports Cardputer ADV and Cardputer v1.1.")}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 1
    assert (root / "data/recipes/m5cardputer-adv__area/recipe.md").exists()
    assert (root / "data/recipes/m5cardputer__area/recipe.md").exists()


# --- a build-file board for every candidate (2026-11-17), not only submissions -------------------
# Generic-chip firmware ("ESP32-S3 air-quality station") names no board in prose, but its own
# platformio.ini says `board = esp32-s3-devkitc-1`, a catalogued Espressif devkit. The device-build
# evidence gate reads that file anyway; admit now takes the board from the targets it returns.

AURA_INI = "[env:aura]\nplatform = espressif32\nframework = arduino\nboard = esp32-s3-devkitc-1\n"
GENERIC_INI = "[env:any]\nplatform = espressif32\nframework = arduino\nboard = esp32dev\n"


def _ini_raw(ini):
    return lambda url: ini if url.endswith("/platformio.ini") else None


def _pio_tree():
    return {"tree": [{"path": "platformio.ini", "type": "blob"}, {"path": "src/main.cpp", "type": "blob"}], "truncated": False}


def test_a_candidate_naming_no_board_is_admitted_on_its_platformio_board(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Project Aura", "https://github.com/c/aura", category=None)])
    metas = {"repos/c/aura": _meta("c/aura", stars=797, description="ESP32-S3 air-quality station with LVGL UI, MQTT, Home Assistant", rid=61),
             "repos/c/aura/git/trees/main?recursive=1": _pio_tree()}
    ctx, asked = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
    res = stage_admit.run(ctx, budget=3, raw=_ini_raw(AURA_INI))
    assert res.admitted == 1 and "data/firmware/aura/firmware.md" in res.paths, res.summary
    recipe = (root / "data/recipes/esp32-s3-devkitc-1__aura/recipe.md").read_text()
    assert "platformio.ini#L4" in recipe                                   # the build file line is the citation
    assert asked.count("repos/c/aura/git/trees/main?recursive=1") == 1      # the gate ran once, not twice
    assert "aura: board esp32-s3-devkitc-1 from platformio" in res.summary


def test_a_build_file_naming_only_a_generic_target_is_still_no_board_evidence(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Any Station", "https://github.com/c/any", category=None)])
    metas = {"repos/c/any": _meta("c/any", stars=90, description="ESP32 station", rid=62),
             "repos/c/any/git/trees/main?recursive=1": _pio_tree()}
    ctx, _ = _counting_ctx(root, metas, Budget(max_calls=150, clock=lambda: 0.0))
    res = stage_admit.run(ctx, budget=3, raw=_ini_raw(GENERIC_INI))
    assert res.admitted == 0 and res.rejects.get("no_board_evidence") == 1
    assert not (root / "data/firmware/any").exists()
