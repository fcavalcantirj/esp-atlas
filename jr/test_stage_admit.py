"""Tests for jr/stage_admit.py — the Track A admission stage, end to end on a tmp tree with
fake network. The tmp root carries a COPY of the real data/boards + data/modules (the stage
resolves chips against the tree it writes), so nothing real is written."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import memory
import stage_admit
import tick
import tools
import writers
from budget import Budget

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
          license="MIT", rid=1):
    return {"full_name": full_name, "description": description, "license": {"spdx_id": license},
            "topics": [], "homepage": None, "default_branch": "main",
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


def _ctx(root, dry_run=False, budget=None, metas=None):
    metas = metas or {}
    budget = budget or Budget(clock=lambda: 0.0)

    def gh(*a):
        doc = metas.get(a[1])
        if doc is None:
            return SimpleNamespace(returncode=1, stdout="", stderr="404 not found")
        return SimpleNamespace(returncode=0, stdout=json.dumps(doc), stderr="")

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
        if doc is None:
            return SimpleNamespace(returncode=1, stdout="", stderr="404 not found")
        return SimpleNamespace(returncode=0, stdout=json.dumps(doc), stderr="")
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


def test_submission_without_a_hint_uses_the_repo_build_files_as_evidence(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    issues = [_issue(8, "https://github.com/s/relwriter")]
    metas = {"repos/s/relwriter": _meta("s/relwriter", stars=40, description="Firmware", rid=81)}
    api_docs = {"repos/s/relwriter/releases/latest": {"tag_name": "v1", "assets": [
                    {"name": "relwriter-v1.2.0-m5cardputer.bin", "size": 10, "browser_download_url": "https://github.com/s/relwriter/releases/download/v1/relwriter-v1.2.0-m5cardputer.bin"},
                    {"name": "relwriter-v1.2.0-m5stick_cplus2.bin", "size": 10, "browser_download_url": "https://github.com/s/relwriter/releases/download/v1/relwriter-v1.2.0-m5stick_cplus2.bin"}]},
                "repos/s/relwriter/git/trees/main?recursive=1": {"tree": [{"path": "README.md", "type": "blob"}], "truncated": False}}
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


def test_a_launcher_entry_without_a_name_or_a_parseable_url_is_still_labelled_in_the_summary(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("", "https://github.com/n/nameless"), _entry("", "")])
    res = stage_admit.run(_ctx(root, metas={}), budget=2)
    assert "nameless: skip repo_unresolved" in res.summary
    assert "(unnamed entry): skip" in res.summary and ": skip" not in res.summary.replace("nameless: skip", "").replace("(unnamed entry): skip", "")
