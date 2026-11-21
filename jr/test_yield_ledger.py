"""jr/yield_ledger.py — rows per stage per tick, trailing-window lane yield, dead and stalled lanes."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import yield_ledger as yl

NOW = datetime(2026, 11, 17, 23, 2, tzinfo=timezone.utc)
SPLIT = {"backfill": 3, "firmware": 3}


def stages(backfill=0, admit=0, boardmap=0, topics=0):
    return [{"name": "backfill", "paths": [], "produced": backfill, "counts": {"filled": backfill, "skipped": 0, "cooled": 0, "cooling": 84}},
            {"name": "admit", "paths": [], "produced": admit, "counts": {}},
            {"name": "boardmap", "paths": ["data/firmware/x/recipes/y.md"] * boardmap, "produced": boardmap, "counts": {}},
            {"name": "admit_topics", "paths": [], "produced": topics, "counts": {}},
            {"name": "popularity_refresh", "paths": [], "produced": 0, "counts": {}}]


def test_rows_carry_units_produced_counts_and_the_tick_budget():
    rows = yl.rows_for_tick(stages(boardmap=2), SPLIT, NOW, calls=49, seconds=91.04, units_topics=2)
    assert [r["stage"] for r in rows] == ["backfill", "admit", "boardmap", "admit_topics"]   # the refresh stage is no lane
    by = {r["stage"]: r for r in rows}
    assert by["backfill"] == {"tick": "2026-11-17T23:00Z", "stage": "backfill", "units": 3, "produced": 0, "paths": 0,
                              "counts": {"filled": 0, "skipped": 0, "cooled": 0, "cooling": 84}, "calls": 49, "seconds": 91.0}
    assert (by["admit"]["units"], by["boardmap"]["units"], by["admit_topics"]["units"]) == (1, 2, 2)   # boardmap takes the odd unit
    assert by["boardmap"]["produced"] == 2 and by["boardmap"]["paths"] == 2


def test_append_is_idempotent_per_tick_and_stage_and_skips_corrupt_lines(tmp_path):
    p = tmp_path / "docs/telemetry/yield.jsonl"
    yl.append_rows(p, yl.rows_for_tick(stages(), SPLIT, NOW))
    yl.append_rows(p, yl.rows_for_tick(stages(boardmap=1), SPLIT, NOW))       # the same tick again: replaced, not doubled
    p.write_text(p.read_text() + "not json\n{\"tick\": 1}\n")
    rows = yl.read_rows(p)
    assert len(rows) == 4 and {r["stage"]: r["produced"] for r in rows}["boardmap"] == 1
    later = yl.append_rows(p, yl.rows_for_tick(stages(), SPLIT, NOW + timedelta(hours=1)))
    assert [r["tick"] for r in later] == ["2026-11-17T23:00Z"] * 4 + ["2026-11-18T00:00Z"] * 4
    assert all(json.loads(l) for l in p.read_text().splitlines())                  # the corrupt lines are gone after a rewrite


def ledger(hours, backfill=0, admit=0, boardmap=0, topics=0, split=SPLIT):
    rows = []
    for h in range(hours, 0, -1):
        rows += yl.rows_for_tick(stages(backfill, admit, boardmap, topics), split, NOW - timedelta(hours=h), units_topics=2)
    return rows


def test_lane_yield_counts_the_trailing_window_before_this_tick_only():
    rows = ledger(30, boardmap=1) + yl.rows_for_tick(stages(boardmap=9), SPLIT, NOW, units_topics=2)      # this tick's own row is never evidence
    y = yl.lane_yield(rows, NOW, 24)
    assert y["ticks_in_window"] == 24 and y["backfill"] == {"ticks": 24, "units": 72, "produced": 0}
    assert y["firmware"] == {"ticks": 24, "units": 72, "produced": 24} and y["topics"] == {"ticks": 24, "units": 48, "produced": 0}


def test_a_lane_without_units_in_a_tick_is_not_counted_for_that_tick():
    rows = ledger(24, boardmap=1, split={"backfill": 0, "firmware": 6})
    y = yl.lane_yield(rows, NOW, 24)
    assert y["backfill"] == {"ticks": 0, "units": 0, "produced": 0} and y["firmware"]["ticks"] == 24
    assert yl.dead_lanes(y, 24) == []            # parked is not dead


def test_dead_and_stalled_lanes_from_the_measured_shape():
    y = yl.lane_yield(ledger(24, boardmap=1), NOW, 24)
    assert yl.dead_lanes(y, 24) == ["backfill"] and yl.stalled_lanes(y, 24) == ["backfill", "topics"]
    silent = yl.lane_yield(ledger(51), NOW, 24)
    assert yl.dead_lanes(silent, 24) == [] and yl.stalled_lanes(silent, 24) == ["backfill", "firmware", "topics"]
    short = yl.lane_yield(ledger(23), NOW, 24)
    assert yl.dead_lanes(short, 24) == [] and yl.stalled_lanes(short, 24) == []
    assert yl.summary(y) == "yield backfill 0/72u firmware 24/72u topics 0/48u (24 ticks)"


def test_merging_two_copies_keeps_every_row_once_and_mains_row_on_a_shared_key():
    main = (json.dumps({"tick": "2026-11-18T08:00Z", "stage": "admit", "produced": 0}) + "\n"
            + json.dumps({"tick": "2026-11-18T05:00Z", "stage": "admit", "produced": 0, "src": "main"}) + "\n")
    pr = (json.dumps({"tick": "2026-11-18T05:00Z", "stage": "admit", "produced": 0, "src": "pr"}) + "\n"
          + "not json\n" + json.dumps({"tick": "2026-11-18T06:00Z", "stage": "boardmap", "produced": 1}) + "\n")
    rows = [json.loads(line) for line in yl.merge_text(main, pr).splitlines()]
    assert [(r["tick"], r["stage"]) for r in rows] == [("2026-11-18T05:00Z", "admit"), ("2026-11-18T06:00Z", "boardmap"),
                                                       ("2026-11-18T08:00Z", "admit")]
    assert rows[0]["src"] == "main" and rows[1]["produced"] == 1
    assert yl.merge_text(yl.merge_text(main, pr), pr) == yl.merge_text(main, pr)
