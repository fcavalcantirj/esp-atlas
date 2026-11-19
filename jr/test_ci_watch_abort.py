"""SPEC-jr-self-heal.md §1c — a tick that aborts the same way twice in a row is an incident for the heal
delegate, in the same store as a red CI check; a tick that completes resolves it. Transient aborts (GitHub
unreadable or rate-limited, another tick holding the lock, the call budget) and those only a human can
clear (a stuck tick PR, branch protection) never open one. No GitHub, no network.

2026-11-18: four ticks (18Z..21Z) aborted on the same pending-PR gap and nothing reacted but Telegram."""
from __future__ import annotations

import json

import ci_watch as cw

T1, T2, T3, T4 = (f"2026-11-18T{h}:00:50+00:00" for h in (18, 19, 20, 21))
WLED = ("pending-PR inventory incomplete, nothing staged or published: Jr PR #1839's committed repo id for wled "
        "is not bound to its firmware.md source at that head and confirmed by GitHub")
OTHER = "TypeError: 'NoneType' object is not subscriptable"


def _store(tmp_path):
    return cw.Store(tmp_path / "incidents.json")


def _abort_incidents(store):
    return [r for r in store._load()["incidents"].values() if r["context"]["check"].startswith(cw.ABORT_CHECK)]


def test_the_first_abort_is_counted_not_an_incident(tmp_path):
    store = _store(tmp_path)
    out = cw.abort_watch(store, WLED, T1)
    assert out["status"] == "ok" and out["incidents"] == [] and out["consecutive"] == 1
    assert _abort_incidents(store) == []


def test_the_same_abort_twice_in_a_row_opens_one_incident_with_its_evidence(tmp_path):
    store = _store(tmp_path)
    cw.abort_watch(store, WLED, T1)
    out = cw.abort_watch(store, WLED, T2)
    [rec] = _abort_incidents(store)
    assert out["incidents"] == [rec["id"]] and rec["state"] == "open" and rec["branch"].startswith("jr/heal-")
    c = rec["context"]
    assert c["check"] == "abort:pending-pr-inventory-incomplete" and c["kind_detail"] == "abort" and c["source"] == "tick"
    assert c["evidence"]["reason"] == WLED and c["evidence"]["consecutive"] == 2
    assert c["evidence"]["first_seen"] == T1 and c["evidence"]["last_seen"] == T2
    assert any("abort" in n.lower() and "heal delegate" in n for n in out["nudges"])


def test_further_identical_aborts_keep_one_incident(tmp_path):
    store = _store(tmp_path)
    for t in (T1, T2, T3, T4):
        out = cw.abort_watch(store, WLED, t)
    assert len(_abort_incidents(store)) == 1 and out["consecutive"] == 4
    assert out["incidents"] == ["abort:pending-pr-inventory-incomplete already open"]


def test_the_same_abort_for_another_pr_number_is_the_same_break(tmp_path):
    store = _store(tmp_path)
    cw.abort_watch(store, WLED, T1)
    cw.abort_watch(store, WLED.replace("#1839", "#1901"), T2)
    assert len(_abort_incidents(store)) == 1


def test_the_same_kind_with_another_detail_continues_the_streak(tmp_path):
    store = _store(tmp_path)
    cw.abort_watch(store, WLED, T1)
    out = cw.abort_watch(store, WLED.replace("wled", "circuitpython"), T2)
    assert out["consecutive"] == 2 and len(_abort_incidents(store)) == 1
    assert _abort_incidents(store)[0]["context"]["evidence"]["reason"].count("circuitpython") == 1


def test_a_different_abort_restarts_the_count(tmp_path):
    store = _store(tmp_path)
    cw.abort_watch(store, WLED, T1)
    out = cw.abort_watch(store, OTHER, T2)
    assert out["consecutive"] == 1 and _abort_incidents(store) == []
    cw.abort_watch(store, OTHER, T3)
    [rec] = _abort_incidents(store)
    assert rec["context"]["check"] == "abort:typeerror"


def test_a_completed_tick_resolves_the_incident_and_resets_the_count(tmp_path):
    store = _store(tmp_path)
    cw.abort_watch(store, WLED, T1)
    cw.abort_watch(store, WLED, T2)
    out = cw.abort_watch(store, None, T3)
    assert out["resolved"] == [_abort_incidents(store)[0]["id"]]
    assert _abort_incidents(store)[0]["state"] == "resolved"
    assert any("resolved" in n for n in out["nudges"])
    assert cw.abort_watch(store, WLED, T4)["consecutive"] == 1          # the streak starts over


def test_a_completed_tick_leaves_other_incidents_alone(tmp_path):
    store = _store(tmp_path)
    ci = cw.Verdict(kind="incident", source="main", check="validate", fingerprint="f" * 64)
    store.record(ci, T1)
    cw.abort_watch(store, None, T2)
    assert store.get(("f" * 64)[:12])["state"] == "open"


def test_transient_and_human_only_aborts_never_open_an_incident_nor_break_a_streak(tmp_path):
    store = _store(tmp_path)
    cw.abort_watch(store, WLED, T1)
    for reason in ("GitHub rate limit low: 120 < 500", "gh unavailable (rate_limit query failed)",
                   "gh pr list failed (cannot see open Jr PRs)", "another tick is running (lock held: /tmp/x)",
                   "cannot open tick lock /tmp/x: denied", "budget: 150 gh calls", "branch protection: missing",
                   "a Jr tick PR has been open > 3 h: #7 (jr/tick-x) · conflicting · lists no changed files — needs a human"):
        for _ in range(3):
            out = cw.abort_watch(store, reason, T2)
            assert out["status"] == "ok" and out.get("skipped") and out["incidents"] == [], reason
    assert _abort_incidents(store) == []
    cw.abort_watch(store, WLED, T3)                                       # still the 2nd in a row
    assert len(_abort_incidents(store)) == 1


def test_the_launcher_claims_an_abort_incident_even_with_stall_dispatch_off(tmp_path):
    store = _store(tmp_path)
    cw.abort_watch(store, WLED, T1)
    cw.abort_watch(store, WLED, T2)
    rec = store.claim(T2, allow_stall=False)
    assert rec and rec["context"]["check"].startswith(cw.ABORT_CHECK) and rec["state"] == "dispatched"


def test_a_dry_run_writes_nothing(tmp_path):
    store = _store(tmp_path)
    for t in (T1, T2):
        out = cw.abort_watch(store, WLED, t, dry_run=True)
    assert out["status"] == "ok" and out.get("would") is not None
    assert not (tmp_path / "incidents.json").exists()


def test_a_broken_store_never_raises(tmp_path):
    (tmp_path / "incidents.json").write_text("{not json")
    out = cw.abort_watch(_store(tmp_path), WLED, T1)
    assert out["status"] == "unavailable" and "unreadable" in out["why"]
    (tmp_path / "incidents.json").write_text(json.dumps({"version": 1, "incidents": {}}))
