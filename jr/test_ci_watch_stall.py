"""SPEC-jr-self-heal.md §1b — a lane that produced nothing over the stall window is an incident for the heal
delegate, in the same store as a red CI check; a lane producing again resolves it. No GitHub, no network."""
from __future__ import annotations

import ci_watch as cw

NOW = "2026-11-18T23:02:00+00:00"
LATER = "2026-11-19T06:02:00+00:00"
Y = {"backfill": {"ticks": 24, "units": 72, "produced": 0}, "firmware": {"ticks": 24, "units": 72, "produced": 0},
     "topics": {"ticks": 24, "units": 48, "produced": 0}, "window_ticks": 24, "ticks_in_window": 24}
STALL = {"lanes": ["backfill", "topics"], "stall_ticks": 24, "yields": Y}
STAGES = [{"name": "backfill", "summary": "backfilled 0, skipped 0, cooling 84", "counts": {"filled": 0, "skipped": 0, "cooled": 0, "cooling": 84}},
          {"name": "admit_topics", "summary": "topics=v1:unexpected-maker,waveshare fetched=102 prefiltered=10 scored_clean=0 authored=0", "counts": {}}]
REJECTS = {"already_catalogued": 90, "skipped_scoring": 10}


def test_one_incident_per_stalled_lane_with_the_ticks_evidence(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    out = cw.stall_watch(store, STALL, Y, NOW, stages=STAGES, rejects=REJECTS)
    assert out["status"] == "ok" and len(out["incidents"]) == 2 and out["resolved"] == []
    recs = store._load()["incidents"]
    back = next(r for r in recs.values() if r["context"]["check"] == "stall:backfill")
    assert back["state"] == "open" and back["branch"].startswith("jr/heal-") and back["fingerprint"] == cw.stall_fingerprint("backfill")
    ev = back["context"]["evidence"]
    assert ev["stage_summaries"] == {"backfill": "backfilled 0, skipped 0, cooling 84"} and ev["stage_counts"]["backfill"]["cooling"] == 84
    assert ev["yield"] == Y["backfill"] and ev["tick_rejects"] == REJECTS and back["context"]["kind_detail"] == "stall"
    assert any("stall" in n.lower() or "produced nothing" in n for n in out["nudges"])


def test_the_same_stalled_lane_next_tick_is_not_a_second_incident(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    cw.stall_watch(store, STALL, Y, NOW, stages=STAGES)
    out = cw.stall_watch(store, STALL, Y, LATER, stages=STAGES)
    assert out["incidents"] == ["stall:backfill already open", "stall:topics already open"]
    assert len(store._load()["incidents"]) == 2


def test_a_lane_producing_again_resolves_its_incident_and_a_recurrence_gets_a_suffix(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    cw.stall_watch(store, STALL, Y, NOW, stages=STAGES)
    y2 = {**Y, "backfill": {"ticks": 24, "units": 72, "produced": 2}}
    out = cw.stall_watch(store, {**STALL, "lanes": ["topics"]}, y2, LATER)
    recs = store._load()["incidents"]
    back_id = next(r["id"] for r in recs.values() if r["context"]["check"] == "stall:backfill")
    assert out["resolved"] == [back_id] and recs[back_id]["state"] == "resolved"
    assert any(n.startswith("✅ Jr stall") and "backfill produced again" in n for n in out["nudges"])
    again = cw.stall_watch(store, STALL, Y, "2026-11-21T00:02:00+00:00")
    assert any(i.endswith("-2") for i in again["incidents"])


def test_the_launcher_claims_a_stall_incident_like_a_ci_one(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    cw.stall_watch(store, {**STALL, "lanes": ["backfill"]}, Y, NOW, stages=STAGES)
    rec = store.claim(LATER)
    assert rec is not None and rec["state"] == "dispatched" and rec["context"]["check"] == "stall:backfill"
    assert rec["context"]["failed"] == "backfill produced nothing over 24 ticks"


def test_dry_run_records_nothing_and_no_stall_records_nothing(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    out = cw.stall_watch(store, STALL, Y, NOW, dry_run=True)
    assert out["would"] == ["record stall incident stall:backfill", "record stall incident stall:topics"]
    assert not (tmp_path / "incidents.json").exists()
    out = cw.stall_watch(store, None, Y, NOW)
    assert out == {"status": "ok", "incidents": [], "resolved": [], "nudges": []}
    assert cw.stall_verdicts({"lanes": []}) == [] and cw.stall_verdicts("x") == []


def test_a_broken_store_is_unavailable_never_fatal(tmp_path):
    p = tmp_path / "incidents.json"
    p.write_text("{not json")
    out = cw.stall_watch(cw.Store(p), STALL, Y, NOW)
    assert out["status"] == "unavailable" and "unreadable incident store" in out["why"]
