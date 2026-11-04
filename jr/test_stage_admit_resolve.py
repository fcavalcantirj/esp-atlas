"""jr/stage_admit.py x jr/launcher_resolve.py (G1b, 2026-11-03): launcher entries whose `github`
is None or owner-only are resolved by ONE counted gh search, decided once as `no_source_repo`
when that search is not conclusive, and never leave an empty id/repo in the ledger. Tmp tree +
fake gh, no network; fixtures are real launcher-shaped rows."""
from __future__ import annotations

import json
import urllib.parse
from datetime import timedelta
from types import SimpleNamespace

import pytest

import launcher_resolve
import memory
import stage_admit
import tick
import tools
from budget import Budget
from test_stage_admit import DEVICE_TREE, NOW, _meta, root  # noqa: F401 — `root` is the shared tmp-tree fixture

pytestmark = pytest.mark.usefixtures("esp_sketch_raw")

IBUTTON = {"fid": "ec0b5f11b7a6a85445a1d4dc5ad65508", "name": "IButton M5Stick C Plus2",
           "author": "geo_tp", "github": "https://github.com/geo-tp", "category": "stickc",
           "download": 214, "description": None}
AMBIGUOUS = {"fid": "aa11bb22cc33dd44ee55ff6677889900", "name": "Pocket Synth", "author": "Muart",
             "github": None, "category": "cardputer", "download": 90, "description": None}
NOWHERE = {"fid": "0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f", "name": "Rare Radio Toy", "author": "nobody42",
           "github": None, "category": "cardputer", "download": 12, "description": None}
EMPTY = {"fid": "", "name": "", "author": "", "github": "", "category": None, "download": 0}


def _item(full_name):
    return {"full_name": full_name, "name": full_name.split("/")[1]}


class FakeGh:
    """`gh api repos/<o>/<r>` from `metas`, `gh api search/repositories?q=...` from `searches`
    keyed by the decoded q (repo paths case-insensitive, like GitHub); records every call except
    the submissions listing every admit run makes."""

    def __init__(self, metas=None, searches=None):
        self.metas, self.searches, self.calls = metas or {}, searches or {}, []

    def __call__(self, *a):
        if "/issues?" in a[1]:
            return SimpleNamespace(returncode=0, stdout="[]", stderr="")
        self.calls.append(a)
        if a[1].startswith("search/repositories?"):
            q = urllib.parse.parse_qs(urllib.parse.urlsplit(a[1]).query)["q"][0]
            items = self.searches.get(q, [])
            return SimpleNamespace(returncode=0, stdout=json.dumps({"total_count": len(items),
                                                                     "incomplete_results": False,
                                                                     "items": items}), stderr="")
        doc = {k.lower(): v for k, v in self.metas.items()}.get(a[1].lower())
        if doc is None and "/git/trees/" in a[1]:
            doc = DEVICE_TREE              # the device-build evidence gate passes: not under test here
        if doc is None:
            return SimpleNamespace(returncode=1, stdout="", stderr="404 not found")
        return SimpleNamespace(returncode=0, stdout=json.dumps(doc), stderr="")

    def searched(self):
        return [c for c in self.calls if c[1].startswith("search/repositories?")]


def _ctx(root, fake, budget=None, dry_run=False):
    budget = budget or Budget(clock=lambda: 0.0)
    return tick.TickContext(root=root, ledger_path=root / "jr" / "proposed_ledger.json", now=NOW,
                            gh=budget.wrap(fake), git=lambda *a: None, budget=budget,
                            dry_run=dry_run, env={})


def _ledger(root):
    return memory.load(root / "jr" / "proposed_ledger.json")


def _catalog(monkeypatch, entries):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [dict(e) for e in entries])


def _no_empty_keys(led):
    for k, rec in led["by_id"].items():
        assert k and rec.get("id") and rec.get("repo"), rec
    assert all(k for k in led["by_repo"])


def test_owner_only_geo_tp_entry_resolves_to_its_one_repo_and_is_admitted(root, monkeypatch):
    _catalog(monkeypatch, [IBUTTON])
    fake = FakeGh(
        metas={"repos/geo-tp/M5Stick-IButton": _meta("geo-tp/M5Stick-IButton", stars=60, forks=5, rid=5001,
                                                     description="iButton reader for the M5StickC Plus2")},
        searches={"ibutton user:geo-tp": [_item("geo-tp/M5Stick-IButton"), _item("geo-tp/ESP32-Bus-Pirate")]})
    res = stage_admit.run(_ctx(root, fake), budget=3)
    assert res.admitted == 1, res.summary
    assert (root / "data" / "firmware" / "m5stick-ibutton" / "firmware.md").exists()
    assert len(fake.searched()) == 1
    led = _ledger(root)
    assert led["by_id"]["m5stick-ibutton"]["status"] == "proposed"
    note = led["by_id"]["launcher-ec0b5f11b7a6a85445a1d4dc5ad65508"]
    assert note["status"] == "seen" and note["reason"] == "resolved: geo-tp/M5Stick-IButton"
    assert note["repo"] == "launcher:ec0b5f11b7a6a85445a1d4dc5ad65508"
    _no_empty_keys(led)
    # next tick: the launcher entry is already decided — no second search
    again = FakeGh(metas=fake.metas, searches=fake.searches)
    stage_admit.run(_ctx(root, again), budget=3)
    assert again.searched() == []


def test_none_entry_with_an_ambiguous_author_is_decided_once_as_no_source_repo(root, monkeypatch):
    _catalog(monkeypatch, [AMBIGUOUS])
    fake = FakeGh(searches={"pocket synth user:muart": [_item("muart/pocket-synth"),
                                                         _item("muart/synth-pocket-v2")]})
    res = stage_admit.run(_ctx(root, fake), budget=3)
    assert res.admitted == 0 and res.rejects == {"no_source_repo": 1}
    assert "no_source_repo 1" in res.summary
    assert [c for c in fake.calls if c[1].startswith("repos/")] == []      # nothing to fetch
    rec = _ledger(root)["by_id"]["launcher-aa11bb22cc33dd44ee55ff6677889900"]
    assert rec["status"] == "rejected" and rec["reason"].startswith("no_source_repo")
    assert rec["repo"] == "launcher:aa11bb22cc33dd44ee55ff6677889900"
    assert rec["expires"] == (NOW + timedelta(days=memory.UNRESOLVED_REJECT_DAYS)).isoformat()
    again = FakeGh(searches=fake.searches)
    second = stage_admit.run(_ctx(root, again), budget=3)
    assert again.calls == []
    assert second.rejects == {} and "1 already decided" in second.summary


def test_none_entry_with_zero_hits_is_no_source_repo(root, monkeypatch):
    _catalog(monkeypatch, [NOWHERE])
    fake = FakeGh()
    res = stage_admit.run(_ctx(root, fake), budget=3)
    assert res.rejects == {"no_source_repo": 1} and len(fake.searched()) == 1
    rec = _ledger(root)["by_id"]["launcher-0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0f"]
    assert rec["status"] == "rejected" and "0 matches" in rec["reason"]


def test_empty_github_entry_never_reaches_the_ledger_and_is_a_counted_skip(root, monkeypatch):
    _catalog(monkeypatch, [EMPTY, dict(EMPTY, name="Nameless", github=None)])
    fake = FakeGh()
    res = stage_admit.run(_ctx(root, fake), budget=3)
    assert res.rejects == {"unkeyed": 2}
    assert res.summary == "skipped 2 launcher entries: unkeyed 2"
    assert fake.calls == []                                                   # no key -> no search
    led = _ledger(root)
    assert led["by_id"] == {} and led["by_repo"] == {}


def test_resolver_searches_are_capped_per_tick_and_the_rest_wait_unrecorded(root, monkeypatch):
    n = launcher_resolve.RESOLVER_CALLS_PER_TICK + 5
    entries = [dict(NOWHERE, fid=f"{i:032x}", name=f"Radio Toy {chr(97 + i)}{chr(97 + i)}{chr(97 + i)}")
               for i in range(n)]
    _catalog(monkeypatch, entries)
    fake = FakeGh()
    res = stage_admit.run(_ctx(root, fake), budget=3)
    assert len(fake.searched()) == launcher_resolve.RESOLVER_CALLS_PER_TICK
    assert res.rejects == {"no_source_repo": launcher_resolve.RESOLVER_CALLS_PER_TICK, "resolve_deferred": 5}
    led = _ledger(root)
    assert len(led["by_id"]) == launcher_resolve.RESOLVER_CALLS_PER_TICK    # deferred ones are not recorded
    # the next tick picks up exactly the deferred ones
    nxt = FakeGh()
    stage_admit.run(_ctx(root, nxt), budget=3)
    assert len(nxt.searched()) == 5


def test_resolver_searches_stay_inside_admits_call_share(root, monkeypatch):
    entries = [dict(NOWHERE, fid=f"{i:032x}", name=f"Radio Toy {chr(97 + i) * 3}") for i in range(8)]
    _catalog(monkeypatch, entries)
    fake = FakeGh()
    b = Budget(max_calls=150, clock=lambda: 0.0)
    res = stage_admit.run(_ctx(root, fake, budget=b), budget=3, call_share=0.03)   # 3% of 150 = 4 calls
    assert b.calls <= 4
    assert "admit's call share used (4 of the tick's calls)" in res.summary


def test_resolver_searches_stop_before_the_tick_budget_runs_low(root, monkeypatch):
    entries = [dict(NOWHERE, fid=f"{i:032x}", name=f"Radio Toy {chr(97 + i) * 3}") for i in range(8)]
    _catalog(monkeypatch, entries)
    fake = FakeGh()
    b = Budget(max_calls=9, clock=lambda: 0.0)                     # the catalog fetch + submissions listing take 2
    res = stage_admit.run(_ctx(root, fake, budget=b), budget=3)
    assert len(fake.searched()) == 2                                          # 7, 6 left -> search; 5 left -> stop
    assert b.remaining_calls() == stage_admit.MIN_CALLS_TO_CONTINUE
    assert "tick budget low (5 calls left)" in res.summary
    assert len(_ledger(root)["by_id"]) == 2                                   # the unsearched ones are not recorded


def test_resolved_repo_below_the_floor_is_still_rejected_below_floor(root, monkeypatch):
    _catalog(monkeypatch, [IBUTTON])
    fake = FakeGh(
        metas={"repos/geo-tp/M5Stick-IButton": _meta("geo-tp/M5Stick-IButton", stars=4, forks=1, rid=5002,
                                                     description="iButton reader for the M5StickC Plus2")},
        searches={"ibutton user:geo-tp": [_item("geo-tp/M5Stick-IButton")]})
    res = stage_admit.run(_ctx(root, fake), budget=3)
    assert res.admitted == 0 and res.rejects == {"below_floor": 1}
    led = _ledger(root)
    rec = led["by_id"]["m5stick-ibutton"]
    assert rec["status"] == "rejected" and rec["reason"].startswith("below_floor:") and rec["repo_id"] == 5002
    assert led["by_id"]["launcher-ec0b5f11b7a6a85445a1d4dc5ad65508"]["status"] == "seen"
    assert not (root / "data" / "firmware" / "m5stick-ibutton").exists()


def test_dry_run_resolves_but_writes_no_ledger(root, monkeypatch):
    _catalog(monkeypatch, [AMBIGUOUS, IBUTTON])
    fake = FakeGh(
        metas={"repos/geo-tp/M5Stick-IButton": _meta("geo-tp/M5Stick-IButton", stars=4, forks=1, rid=5002)},
        searches={"ibutton user:geo-tp": [_item("geo-tp/M5Stick-IButton")]})
    res = stage_admit.run(_ctx(root, fake, dry_run=True), budget=3)
    assert res.rejects == {"no_source_repo": 1, "below_floor": 1}               # both paths ran: one resolved
    assert not (root / "jr" / "proposed_ledger.json").exists() or _ledger(root)["by_id"] == {}


def test_resolved_entry_whose_repo_fetch_fails_is_retried_on_the_unresolved_ttl(root, monkeypatch):
    """The launcher note follows its repo's decision: a transient 404/5xx on the resolved repo is
    repo_unresolved (7 d), so the entry must not sit behind a 30-day note."""
    _catalog(monkeypatch, [IBUTTON])
    fake = FakeGh(searches={"ibutton user:geo-tp": [_item("geo-tp/M5Stick-IButton")]})   # no meta: 404
    res = stage_admit.run(_ctx(root, fake), budget=3)
    assert res.rejects == {"repo_unresolved": 1}
    note = _ledger(root)["by_id"]["launcher-ec0b5f11b7a6a85445a1d4dc5ad65508"]
    assert note["expires"] == (NOW + timedelta(days=memory.UNRESOLVED_REJECT_DAYS)).isoformat()


def test_resolved_and_admitted_entry_keeps_the_seen_ttl(root, monkeypatch):
    _catalog(monkeypatch, [IBUTTON])
    fake = FakeGh(
        metas={"repos/geo-tp/M5Stick-IButton": _meta("geo-tp/M5Stick-IButton", stars=60, forks=5, rid=5001,
                                                     description="iButton reader for the M5StickC Plus2")},
        searches={"ibutton user:geo-tp": [_item("geo-tp/M5Stick-IButton")]})
    stage_admit.run(_ctx(root, fake), budget=3)
    note = _ledger(root)["by_id"]["launcher-ec0b5f11b7a6a85445a1d4dc5ad65508"]
    assert note["expires"] == (NOW + timedelta(days=memory.SEEN_TTL_DAYS)).isoformat()
