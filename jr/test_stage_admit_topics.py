"""Tests for jr/stage_admit_topics.py — the GitHub-topics tick stage, end to end on a tmp tree
with a fake topic source, fake repo-meta fetch and a fake guard (never a real subprocess). The
tmp root carries a COPY of the real data/boards + data/modules (score_entry resolves boards
against the tree it writes, same as test_stage_admit.py's fixture), so nothing real is written."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import drain
import ledger
import memory
import pending_prs
import source_topics
import stage_admit_topics
import tick
import tools
from budget import Budget, BudgetExceeded

pytestmark = pytest.mark.usefixtures("esp_sketch_raw")   # the device-build gate passes (conftest)

REPO = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)

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


@pytest.fixture
def root(tmp_path):
    shutil.copytree(REPO / "data" / "boards", tmp_path / "data" / "boards")
    shutil.copytree(REPO / "data" / "modules", tmp_path / "data" / "modules")
    (tmp_path / "data" / "firmware" / "seed-original").mkdir(parents=True)
    (tmp_path / "data" / "firmware" / "seed-original" / "firmware.md").write_text(SEED_FW)
    (tmp_path / "data" / "recipes").mkdir()
    (tmp_path / "jr").mkdir()
    return tmp_path


def _default_gh(*a):
    """Empty replies, except a repo tree: an Arduino sketch whose sketch.yaml names an ESP board
    (esp_sketch_raw), so the device-build evidence gate (jr/device_evidence.py) passes and the
    gates under test here are the only ones that bite."""
    if len(a) > 1 and "/git/trees/" in a[1]:
        return SimpleNamespace(returncode=0, stdout=json.dumps({"tree": [{"path": "main.ino", "type": "blob"},
                                                                         {"path": "sketch.yaml", "type": "blob"}]}), stderr="")
    return SimpleNamespace(returncode=0, stdout="", stderr="")


def _ctx(root, dry_run=False, budget=None, gh=None, now=NOW):
    budget = budget or Budget(clock=lambda: 0.0)
    gh = gh or _default_gh
    return tick.TickContext(root=root, ledger_path=root / "jr" / "proposed_ledger.json", now=now,
                            gh=budget.wrap(gh), git=lambda *a: None,
                            budget=budget, dry_run=dry_run, env={})


def _topic_entry(name, github, description=None):
    return {"name": name, "github": github, "source": "topic:cardputer", "description": description}


def _meta(full_name, stars=30, forks=0, fork=False, source=None, archived=False, description=None,
         license="MIT", rid=1, homepage=None):
    return {"full_name": full_name, "description": description, "license": license,
           "topics": [], "homepage": homepage, "default_branch": "main",
           "stars": stars, "archived": archived, "forks": forks,
           "id": rid, "fork": fork, "source_full_name": source, "parent_full_name": source,
           "pushed_at": "2026-09-01T00:00:00Z", "language": "C",
           "readme_title": None, "readme_body": "", "has_library_manifest": False}


def _fake_fetch_meta(metas):
    def fetch_meta(github_url):
        parts = github_url.rstrip("/").replace("https://github.com/", "").split("/")
        key = "/".join(parts[:2])
        return metas.get(key) or {"error": f"no fixture for {key}"}
    return fetch_meta


def _read_fm(path):
    return yaml.safe_load(path.read_text().split("\n---\n")[0].split("---\n", 1)[1])


@pytest.fixture(autouse=True)
def _fake_guard(monkeypatch):
    """Every real run passes through run_drain -> author_selected -> tools.run_guard() once per
    candidate plus once at the end; never spawn the real scripts/validate.py subprocess here."""
    monkeypatch.setattr(tools, "run_guard", lambda: {"ok": True, "output": ""})


def test_authors_at_most_budget_and_reports_them(root, monkeypatch):
    entries = [
        _topic_entry("My Cardputer Tool", "https://github.com/n/newtool", "A Cardputer tool"),
        _topic_entry("Second Cardputer Tool", "https://github.com/n/second", "Another Cardputer tool"),
        _topic_entry("Third Cardputer Tool", "https://github.com/n/third", "A third Cardputer tool"),
    ]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    metas = {
        "n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101),
        "n/second": _meta("n/second", stars=40, description="Another Cardputer tool", rid=102),
        "n/third": _meta("n/third", stars=50, description="A third Cardputer tool", rid=103),
    }
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))

    res = stage_admit_topics.run(_ctx(root), budget=2)

    assert res.name == "admit_topics"
    assert res.admitted == 2
    assert len(res.paths) == 4   # 2 firmware.md + 2 recipe.md
    assert {p.split("/")[2] for p in res.paths if p.startswith("data/firmware/")} == {"newtool", "second"}
    assert {it["id"] for it in res.items} == {"newtool", "second"}
    assert "authored=2" in res.summary

    fm = _read_fm(root / "data" / "firmware" / "newtool" / "firmware.md")
    assert fm["url"] == "https://github.com/n/newtool" and fm["socs"] == ["esp32-s3"]
    assert not (root / "data" / "firmware" / "third").exists()   # budget-capped, never authored


def test_dry_run_scores_but_writes_nothing(root, monkeypatch):
    entries = [_topic_entry("My Cardputer Tool", "https://github.com/n/newtool", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    metas = {"n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101)}
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))

    res = stage_admit_topics.run(_ctx(root, dry_run=True), budget=2)

    assert res.admitted == 0 and res.paths == []
    assert "newtool: would admit" in res.summary
    assert {p.name for p in (root / "data" / "firmware").iterdir()} == {"seed-original"}
    assert not root.joinpath("jr", "proposed_ledger.json").exists()
    writes = {(w["path"], w["field"]) for w in res.would_write}
    assert ("data/firmware/newtool/firmware.md", "*") in writes and ("jr/proposed_ledger.json", "by_id.newtool") in writes
    assert any(p.startswith("data/recipes/") and p.endswith("__newtool/recipe.md") for p, _ in writes)


def test_dry_run_lists_the_below_floor_note_a_real_run_records(root, monkeypatch):
    entries = [_topic_entry("Tiny Cardputer Tool", "https://github.com/t/tiny", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta({"t/tiny": _meta("t/tiny", stars=1, forks=0, rid=7, description="A Cardputer tool")}))

    res = stage_admit_topics.run(_ctx(root, dry_run=True), budget=2)

    assert res.would_write == [{"path": "jr/proposed_ledger.json", "field": "by_id.tiny", "value": "seen (below floor)"}], (res.summary, res.rejects)
    assert not root.joinpath("jr", "proposed_ledger.json").exists()


def test_authored_ids_are_recorded_proposed_in_the_ledger(root, monkeypatch):
    entries = [_topic_entry("My Cardputer Tool", "https://github.com/n/newtool", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    metas = {"n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101)}
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))

    stage_admit_topics.run(_ctx(root), budget=2)

    led = memory.load(root / "jr" / "proposed_ledger.json")
    rec = led["by_id"]["newtool"]
    assert rec["status"] == "proposed" and rec["repo"] == "n/newtool"


def test_second_tick_does_not_reauthor_an_open_pr_candidate(root, monkeypatch):
    """Guards the historical duplicate-PR bug (#158/#159): once an id is recorded `proposed` (as
    the first tick does), a second tick's prefilter must skip its repo before ever fetching it
    again — run_drain threads the ledger through drain.prefilter for exactly this."""
    entries = [_topic_entry("My Cardputer Tool", "https://github.com/n/newtool", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    metas = {"n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101)}
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))

    first = stage_admit_topics.run(_ctx(root), budget=2)
    assert first.admitted == 1
    shutil.rmtree(root / "data" / "firmware" / "newtool")   # simulate: PR not yet merged, worktree starts fresh next tick

    second = stage_admit_topics.run(_ctx(root), budget=2)
    assert second.admitted == 0 and second.paths == []



@pytest.mark.parametrize("dry_run", [False, True])
def test_an_id_an_open_or_vetoed_tick_pr_holds_never_reaches_the_drain(root, monkeypatch, dry_run):
    """jr/pending_prs.py: the PR's own file list holds the id even when the ledger never heard of it
    (the proposal lives only on the un-merged PR branch, or that PR was closed: a veto)."""
    entries = [_topic_entry("My Cardputer Tool", "https://github.com/n/newtool", "A Cardputer tool"),
               _topic_entry("Second Cardputer Tool", "https://github.com/n/second", "Another Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    fetched = []
    metas = {"n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101),
             "n/second": _meta("n/second", stars=40, description="Another Cardputer tool", rid=102)}
    fetch = _fake_fetch_meta(metas)
    monkeypatch.setattr(drain, "default_fetch_meta", lambda url: fetched.append(url) or fetch(url))
    closed = {"number": 1478, "headRefName": "jr/tick-20261106-0900", "mergedAt": None,
              "closedAt": (NOW - timedelta(days=2)).isoformat(), "files": [{"path": "data/firmware/second/firmware.md"},
                                                                                         {"path": "data/recipes/m5cardputer__second/recipe.md"}]}
    opened = {"number": 1500, "headRefName": "jr/tick-20261106-2200",
              "files": [{"path": "data/recipes/m5cardputer__newtool/recipe.md"}]}
    ctx = _ctx(root, dry_run=dry_run)
    ctx.pending = pending_prs.build([opened], [closed], NOW)

    res = stage_admit_topics.run(ctx, budget=2)

    assert res.admitted == 0 and res.paths == [] and fetched == []
    assert res.rejects.get("already_proposed") == 1 and res.rejects.get("vetoed") == 1
    assert "newtool: already_proposed (#1500 open)" in res.summary and "second: vetoed (#1478" in res.summary

def _hour_surfacing(root, topic):
    """A tick clock whose rotation slice includes `topic` — so a test can pin which seed topic
    the stage searches without hard-coding the seed list's order."""
    seed = source_topics.seed_topics(root)
    for h in range(len(seed)):
        if topic in source_topics.topics_for_tick(seed, h, tick.TOPICS_PER_TICK):
            return datetime.fromtimestamp(h * 3600, tz=timezone.utc)
    raise AssertionError(f"{topic} never rotates in")


def _search_gh(results, calls):
    """A fake ctx.gh answering `search/repositories?q=topic:X` from `results[X]` (recorded in
    `calls`); a repo-tree read gets _default_gh's sketch (not recorded: it is not a search)."""
    def gh(*args):
        if len(args) >= 2 and "/git/trees/" in args[1]:
            return _default_gh(*args)
        calls.append(args)
        prefix = "search/repositories?q=topic:"
        if len(args) >= 2 and args[0] == "api" and args[1].startswith(prefix):
            topic = args[1][len(prefix):].split("&", 1)[0]
            return SimpleNamespace(returncode=0, stdout=json.dumps({"items": results.get(topic, [])}), stderr="")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"items": []}), stderr="")
    return gh


def test_topic_search_is_routed_through_ctx_gh_and_counted(root, monkeypatch):
    calls = []
    gh = _search_gh({"cardputer": [{"full_name": "n/newtool", "description": "A Cardputer tool"}]}, calls)
    budget = Budget(clock=lambda: 0.0)
    metas = {"n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101)}
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))

    res = stage_admit_topics.run(_ctx(root, budget=budget, gh=gh, now=_hour_surfacing(root, "cardputer")), budget=2)

    assert res.admitted == 1
    assert len(calls) == tick.TOPICS_PER_TICK   # one search call per rotated-in topic
    assert budget.calls >= tick.TOPICS_PER_TICK   # every ctx.gh call is counted


def test_each_tick_searches_only_its_rotation_slice_never_more_than_topics_per_tick(root, monkeypatch):
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta({}))
    seed = source_topics.seed_topics(root)
    searched = set()
    for h in range(-(-len(seed) // tick.TOPICS_PER_TICK)):
        calls = []
        now = datetime.fromtimestamp(h * 3600, tz=timezone.utc)
        stage_admit_topics.run(_ctx(root, gh=_search_gh({}, calls), now=now), budget=2)
        topics = [c[1].split("topic:", 1)[1].split("&", 1)[0] for c in calls]
        assert len(topics) <= tick.TOPICS_PER_TICK
        assert topics == source_topics.topics_for_tick(seed, h, tick.TOPICS_PER_TICK)
        searched.update(topics)
    assert searched == set(seed)   # a full rotation reaches every seed topic


@pytest.mark.parametrize("stars,admitted", [(3, 0), (30, 1)])
def test_floor_is_the_gate_for_a_repo_surfaced_by_a_new_topic(root, monkeypatch, stars, admitted):
    """A repo only the expanded seed list reaches (topic:meshtastic): below the popularity floor
    it is rejected below_floor; the SAME fixture above the floor is admitted — so the floor, not
    some other gate, is what decides."""
    item = {"full_name": "n/meshnode", "description": "Meshtastic mesh firmware for the LilyGO T-Deck"}
    metas = {"n/meshnode": _meta("n/meshnode", stars=stars, forks=0, description=item["description"], rid=201)}
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))

    res = stage_admit_topics.run(_ctx(root, gh=_search_gh({"meshtastic": [item]}, []),
                                      now=_hour_surfacing(root, "meshtastic")), budget=2)

    assert res.admitted == admitted
    assert (root / "data" / "firmware" / "meshnode").exists() == bool(admitted)
    if not admitted:
        assert res.paths == [] and res.rejects.get("below_floor") == 1
    else:
        assert "meshnode<-topic:meshtastic" in res.summary


def test_report_line_names_the_rotated_topics_and_the_seed_topic_of_each_admit(root, monkeypatch):
    item = {"full_name": "n/newtool", "description": "A Cardputer tool"}
    metas = {"n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101)}
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))
    now = _hour_surfacing(root, "cardputer")
    rotated = source_topics.topics_for_tick(source_topics.seed_topics(root), source_topics.hour_index(now),
                                            tick.TOPICS_PER_TICK)

    res = stage_admit_topics.run(_ctx(root, gh=_search_gh({"cardputer": [item]}, []), now=now), budget=2)

    assert res.admitted == 1
    assert f"topics=v{source_topics.SEED_VERSION}:{','.join(rotated)}" in res.summary
    assert "newtool<-topic:cardputer" in res.summary
    assert [(it["id"], it["source"]) for it in res.items] == [("newtool", "topic:cardputer")]


def test_budget_exceeded_during_topic_search_stops_cleanly(root, monkeypatch):
    exhausted = Budget(max_calls=0, clock=lambda: 0.0)
    monkeypatch.setattr(source_topics, "fetch_topic_repos",
                        lambda topics, search=None: (_ for _ in ()).throw(BudgetExceeded("call budget exhausted: 0+1 > 0 (gh)")))
    res = stage_admit_topics.run(_ctx(root, budget=exhausted), budget=2)
    assert res.admitted == 0 and res.paths == [] and "stopped" in res.summary


def test_below_floor_skips_are_recorded_seen_with_expires_and_pass_ledger_guard(root, monkeypatch):
    """The hourly-tick stall bug: run_drain's only ledger write for a below-floor skip is
    ledger.record_seen (jr/ledger.py), a v1 write with no `expires` — scripts/ledger_guard.py
    rejects any "seen" record a PR adds or changes that lacks one. This stage must re-record every
    skip via memory.record_seen (the v2, TTL'd writer) so the ledger it ships always carries
    `expires` on "seen" entries and the guard stays green."""
    entries = [
        _topic_entry("My Cardputer Tool", "https://github.com/n/newtool", "A Cardputer tool"),
        _topic_entry("Filler Cardputer Tool", "https://github.com/n/filler", "A filler Cardputer tool"),
    ]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    metas = {
        "n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101),
        "n/filler": _meta("n/filler", stars=3, forks=0, description="A filler Cardputer tool", rid=102),
    }
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))

    res = stage_admit_topics.run(_ctx(root), budget=2)

    assert res.admitted == 1
    assert res.rejects.get("below_floor") == 1

    led = json.loads((root / "jr" / "proposed_ledger.json").read_text())
    seen = [rec for rec in led["by_id"].values() if rec["status"] == "seen"]
    assert seen and all(rec.get("expires") for rec in seen)

    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    import ledger_guard  # noqa: E402
    assert ledger_guard.check({"by_id": {}}, led) == []


def _admit_newtool(root, monkeypatch, **meta_kw):
    entries = [_topic_entry("My Cardputer Tool", "https://github.com/n/newtool", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    metas = {"n/newtool": _meta("n/newtool", description="A Cardputer tool", rid=101, **meta_kw)}
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))
    return stage_admit_topics.run(_ctx(root), budget=1)


def test_firmware_item_carries_the_fields_of_the_record_it_wrote(root, monkeypatch):
    """PR #1434 rendered '— None' / 'board None (None)' because this stage's item carried only
    kind/id/source. It now carries what stage_admit's item does, read back from the firmware.md
    and recipe.md it actually wrote — never invented — plus the GitHub id the metadata fetch read
    (the PR body's identity marker, jr/pending_prs.py)."""
    res = _admit_newtool(root, monkeypatch, stars=31, forks=4)

    fm = _read_fm(root / "data" / "firmware" / "newtool" / "firmware.md")
    [rdir] = sorted((root / "data" / "recipes").glob("*__newtool"))
    rc = _read_fm(rdir / "recipe.md")
    [it] = res.items
    assert it == {"kind": "firmware", "id": "newtool", "source": "topic:cardputer",
                  "name": fm["name"], "url": "https://github.com/n/newtool", "repo_id": 101,
                  "stars": 31, "forks": 4, "license": None,
                  "board": rc["board"], "chip": rc["chip_family"], "recipe": rdir.name,
                  "evidence": "surfaced by `topic:cardputer`; recipe cites https://github.com/n/newtool",
                  "needs_human": False}
    assert rdir.name == f"{rc['board']}__newtool" and rc["chip_family"] == "esp32-s3"


def test_firmware_item_leaves_popularity_unknown_when_the_record_has_none(root, monkeypatch):
    """No popularity snapshot written -> stars/forks stay None (rendered '?'), not 0."""
    monkeypatch.setattr(tools, "author_firmware_and_recipes",
                        _without_popularity(tools.author_firmware_and_recipes))
    res = _admit_newtool(root, monkeypatch)
    [it] = res.items
    assert it["stars"] is None and it["forks"] is None


def _without_popularity(author):
    def wrapped(**kw):
        return author(**{**kw, "stars": None, "forks": None, "downloads": None, "homepage": None})
    return wrapped


def test_topics_item_renders_in_the_pr_body_with_real_url_board_and_recipe_and_no_none(root, monkeypatch):
    """Regression for PR #1434's body: the topics-path item, rendered end to end."""
    import report
    res = _admit_newtool(root, monkeypatch, stars=31, forks=4)
    [it] = res.items
    body = report.render_pr_body(report.TickReport(when=NOW, stages=[
        {"name": res.name, "paths": res.paths, "summary": res.summary, "needs_human": False, "items": res.items}]))

    assert "None" not in body
    assert "- **My Cardputer Tool** (`newtool`) — https://github.com/n/newtool" in body
    assert "31 ★ / 4 forks" in body
    assert (f"  - ✅ board `{it['board']}` (esp32-s3): surfaced by `topic:cardputer`; recipe cites "
            f"https://github.com/n/newtool → recipe `{it['board']}__newtool`, status unverified") in body


# --- stable repository identity (jr/pending_prs.py): the GitHub id is matched before the slug -------------

def _identity_pending(fid, owner_repo, rid, vetoed=False):
    """An index whose one tick PR holds `fid` and verified it as repository `rid` (by load(), from the
    ledger committed at its head: `_identities`)."""
    pr = {"number": 1500, "headRefName": "jr/tick-20261106-2200", "mergedAt": None, "_identities": {fid: (rid, owner_repo)},
          "files": [{"path": f"data/firmware/{fid}/firmware.md"}, {"path": f"data/recipes/m5cardputer__{fid}/recipe.md"}],
          "body": pending_prs.render_identity([{"kind": "firmware", "id": fid, "url": f"https://github.com/{owner_repo}",
                                                "repo_id": rid}])}
    if vetoed:
        return pending_prs.build([], [{**pr, "closedAt": (NOW - timedelta(days=2)).isoformat()}], NOW)
    return pending_prs.build([pr], [], NOW)


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
@pytest.mark.parametrize("dry_run", [False, True])
def test_a_held_repository_renamed_upstream_is_not_authored_again(root, monkeypatch, vetoed, dry_run):
    entries = [_topic_entry("New Tool", "https://github.com/n/newtool", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(
        {"n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=4242)}))
    ctx = _ctx(root, dry_run=dry_run)
    ctx.pending = _identity_pending("oldtool", "n/oldtool", 4242, vetoed=vetoed)

    res = stage_admit_topics.run(ctx, budget=1)

    assert res.admitted == 0 and res.paths == [] and not (root / "data" / "firmware" / "newtool").exists()
    assert not getattr(res, "would_write", None) or not any("newtool" in w["path"] for w in res.would_write)
    reason = "vetoed" if vetoed else "already_proposed"
    assert res.rejects.get(reason) == 1 and "skipped_scoring" not in res.rejects, res.rejects
    assert "oldtool" in res.summary and "4242" in res.summary and "#1500" in res.summary, res.summary


@pytest.mark.parametrize("dry_run", [False, True])
def test_another_repository_with_a_held_slug_is_routed_fail_closed(root, monkeypatch, dry_run):
    entries = [_topic_entry("New Tool", "https://github.com/m/newtool", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(
        {"m/newtool": _meta("m/newtool", stars=30, description="A Cardputer tool", rid=7777)}))
    ctx = _ctx(root, dry_run=dry_run)
    ctx.pending = _identity_pending("newtool", "n/newtool", 4242)

    res = stage_admit_topics.run(ctx, budget=1)

    assert res.admitted == 0 and res.paths == [] and not (root / "data" / "firmware" / "newtool").exists()
    assert res.rejects.get("identity_ambiguous") == 1 and "already_proposed" not in res.rejects, res.rejects
    assert "7777" in res.summary and "4242" in res.summary, res.summary


def test_another_repository_with_another_name_is_authored_with_its_id(root, monkeypatch):
    entries = [_topic_entry("Fmt Check", "https://github.com/n/fmtcheck", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(
        {"n/fmtcheck": _meta("n/fmtcheck", stars=30, description="A Cardputer tool", rid=5151)}))
    ctx = _ctx(root)
    ctx.pending = _identity_pending("oldtool", "n/oldtool", 4242)

    res = stage_admit_topics.run(ctx, budget=1)

    assert res.admitted == 1 and "data/firmware/fmtcheck/firmware.md" in res.paths
    assert [it.get("repo_id") for it in res.items] == [5151]           # the next tick holds it by this id


# --- every paid decision is remembered (SPEC-espatlas-jr.md §3b, "The GitHub-topics source remembers") ---

def _expires_days(rec):
    t = datetime.fromisoformat(rec["timestamp"])
    return (datetime.fromisoformat(rec["expires"]) - t).days


def test_scorer_and_unresolved_skips_are_remembered_with_their_ttl(root, monkeypatch):
    """Nov 15-16: 24 ticks of prefiltered=10 scored_clean=0 — a scorer skip was never recorded, so
    every tick paid for the same top repos again. Each paid decision is now a TTL'd rejection under
    the repo's note key, and the ledger it ships passes the ledger guard."""
    import stage_admit
    entries = [
        _topic_entry("Old Cardputer Tool", "https://github.com/n/old", "A Cardputer tool"),
        _topic_entry("Vague Thing", "https://github.com/n/vague", "a thing"),
        _topic_entry("Gone Cardputer Tool", "https://github.com/n/gone", "A Cardputer tool"),
    ]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    metas = {
        "n/old": _meta("n/old", archived=True, description="A Cardputer tool", rid=201),
        # a library, not firmware: a scorer skip no build file can rescue (since 2026-11-17 a repo whose
        # prose names no board takes its board from its build file, and this test tree's fake
        # sketch.yaml names the Cardputer for every repo)
        "n/vague": dict(_meta("n/vague", description="a thing", rid=202), has_library_manifest=True),
    }
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))

    res = stage_admit_topics.run(_ctx(root), budget=1)

    assert res.admitted == 0
    led = json.loads((root / "jr" / "proposed_ledger.json").read_text())
    recs = {r: led["by_id"].get(stage_admit.repo_note_key(r)) for r in ("n/old", "n/vague", "n/gone")}
    assert all(rec and rec["status"] == "rejected" for rec in recs.values()), recs
    assert recs["n/old"]["reason"].startswith("archived")
    assert _expires_days(recs["n/old"]) == memory.ARCHIVED_REJECT_DAYS
    assert recs["n/gone"]["reason"].startswith("repo_unresolved")
    assert _expires_days(recs["n/gone"]) == memory.UNRESOLVED_REJECT_DAYS
    assert _expires_days(recs["n/vague"]) == memory.SEEN_TTL_DAYS

    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    import ledger_guard  # noqa: E402
    assert ledger_guard.check({"by_id": {}}, led) == []


def test_the_next_tick_walks_past_remembered_skips_to_the_next_repos(root, monkeypatch):
    """The point of the memory: with budget 1 a tick scores 5 repos; 5 archived repos lead the star
    order and a good one sits 6th. Tick 1 admits nothing, tick 2 reaches and admits the 6th."""
    junk = [_topic_entry(f"Junk Cardputer Tool {i}", f"https://github.com/j/junk{i}", "A Cardputer tool") for i in range(5)]
    good = _topic_entry("My Cardputer Tool", "https://github.com/n/newtool", "A Cardputer tool")
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: junk + [good])
    metas = {f"j/junk{i}": _meta(f"j/junk{i}", archived=True, description="A Cardputer tool", rid=300 + i) for i in range(5)}
    metas["n/newtool"] = _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101)
    fetched = []
    fetch = _fake_fetch_meta(metas)
    monkeypatch.setattr(drain, "default_fetch_meta", lambda url: fetched.append(url) or fetch(url))

    first = stage_admit_topics.run(_ctx(root), budget=1)
    second = stage_admit_topics.run(_ctx(root, now=NOW + timedelta(hours=1)), budget=1)

    assert first.admitted == 0 and second.admitted == 1
    assert {it["id"] for it in second.items} == {"newtool"}
    assert fetched.count("https://github.com/j/junk0") == 1      # paid once, never again while it holds


def test_a_remembered_skip_is_scored_again_after_its_ttl(root, monkeypatch):
    """A TTL is a re-check, not a veto: once the 30-day note expires the tick's expire() step
    reopens the repo and the prefilter scores it again."""
    import stage_admit
    entries = [_topic_entry("Vague Thing", "https://github.com/n/vague", "a thing")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(
        {"n/vague": dict(_meta("n/vague", description="a thing", rid=202), has_library_manifest=True)}))   # a scorer skip (library)
    stage_admit_topics.run(_ctx(root), budget=1)
    later = NOW + timedelta(days=memory.SEEN_TTL_DAYS + 1)
    memory.expire(path=root / "jr" / "proposed_ledger.json", now=later)
    led = ledger.load_ledger(root / "jr" / "proposed_ledger.json")
    assert not ledger.is_blocked(led, repo="n/vague")
    assert led["by_id"][stage_admit.repo_note_key("n/vague")]["status"] == "expired"


def test_dry_run_records_no_skip(root, monkeypatch):
    entries = [_topic_entry("Old Cardputer Tool", "https://github.com/n/old", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta({"n/old": _meta("n/old", archived=True, rid=201)}))
    stage_admit_topics.run(_ctx(root, dry_run=True), budget=1)
    assert not (root / "jr" / "proposed_ledger.json").exists()


def _repo_note(root, owner_repo):
    import stage_admit
    path = root / "jr" / "proposed_ledger.json"
    led = json.loads(path.read_text()) if path.exists() else {"by_id": {}}
    return led["by_id"].get(stage_admit.repo_note_key(owner_repo))


@pytest.mark.parametrize("pending,repo", [
    (("oldtool", "n/oldtool", 4242, False), "n/newtool"),   # renamed upstream an open PR holds
    (("oldtool", "n/oldtool", 4242, True), "n/newtool"),    # ... a closed PR vetoes
    (("newtool", "n/newtool", 4242, False), "m/newtool"),   # another repo with a held slug
], ids=["open", "vetoed", "ambiguous"])
def test_a_repo_a_tick_pr_holds_is_held_not_remembered(root, monkeypatch, pending, repo):
    """A hold is the open PR's decision, not this tick's: remembering it as a rejection would
    outlive the PR (and the veto's own 30 days)."""
    fid, held_repo, rid, vetoed = pending
    entries = [_topic_entry("New Tool", f"https://github.com/{repo}", "A Cardputer tool")]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(
        {repo: _meta(repo, stars=30, description="A Cardputer tool", rid=4242 if repo == "n/newtool" else 7777)}))
    ctx = _ctx(root)
    ctx.pending = _identity_pending(fid, held_repo, rid, vetoed=vetoed)

    res = stage_admit_topics.run(ctx, budget=1)

    assert res.admitted == 0
    assert _repo_note(root, repo) is None


def test_below_floor_and_device_skips_keep_their_own_records_only(root, monkeypatch):
    """Below the floor is a soft `seen` note and a device-evidence skip a rejection with the
    device TTL, both under the firmware id; neither also gets a 30-day repo-note rejection."""
    entries = [
        _topic_entry("Filler Cardputer Tool", "https://github.com/n/filler", "A filler Cardputer tool"),
        _topic_entry("Server Cardputer Tool", "https://github.com/n/server", "A Cardputer tool server"),
    ]
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: entries)
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta({
        "n/filler": _meta("n/filler", stars=3, forks=0, description="A filler Cardputer tool", rid=102),
        "n/server": _meta("n/server", stars=30, description="A Cardputer tool server", rid=103),
    }))

    def gh(*a):
        if len(a) > 1 and "/git/trees/" in a[1] and "n/server" in a[1]:
            return SimpleNamespace(returncode=0, stdout=json.dumps({"tree": [{"path": "main.go", "type": "blob"},
                                                                             {"path": "go.mod", "type": "blob"}]}), stderr="")
        return _default_gh(*a)

    res = stage_admit_topics.run(_ctx(root, gh=gh), budget=2)

    assert res.rejects.get("below_floor") == 1
    assert sum(v for k, v in res.rejects.items() if k not in ("below_floor",)) == 1, res.rejects
    assert _repo_note(root, "n/filler") is None
    assert _repo_note(root, "n/server") is None
