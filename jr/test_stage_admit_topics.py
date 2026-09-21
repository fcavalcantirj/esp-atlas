"""Tests for jr/stage_admit_topics.py — the GitHub-topics tick stage, end to end on a tmp tree
with a fake topic source, fake repo-meta fetch and a fake guard (never a real subprocess). The
tmp root carries a COPY of the real data/boards + data/modules (score_entry resolves boards
against the tree it writes, same as test_stage_admit.py's fixture), so nothing real is written."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import drain
import ledger
import memory
import source_topics
import stage_admit_topics
import tick
import tools
from budget import Budget, BudgetExceeded

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


def _ctx(root, dry_run=False, budget=None, gh=None):
    budget = budget or Budget(clock=lambda: 0.0)
    gh = gh or (lambda *a: SimpleNamespace(returncode=0, stdout="", stderr=""))
    return tick.TickContext(root=root, ledger_path=root / "jr" / "proposed_ledger.json", now=NOW,
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


def test_topic_search_is_routed_through_ctx_gh_and_counted(root, monkeypatch):
    calls = []

    def gh(*args):
        calls.append(args)
        if args[:2] == ("api", "search/repositories?q=topic:cardputer&sort=stars&order=desc&per_page=100"):
            return SimpleNamespace(returncode=0, stdout=json.dumps({"items": [
                {"full_name": "n/newtool", "description": "A Cardputer tool"}]}), stderr="")
        return SimpleNamespace(returncode=0, stdout=json.dumps({"items": []}), stderr="")

    budget = Budget(clock=lambda: 0.0)
    metas = {"n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=101)}
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta(metas))

    res = stage_admit_topics.run(_ctx(root, budget=budget, gh=gh), budget=2)

    assert res.admitted == 1
    assert len(calls) == len(source_topics.DEFAULT_TOPICS)   # one search call per topic
    assert budget.calls >= len(source_topics.DEFAULT_TOPICS)   # every ctx.gh call is counted


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
