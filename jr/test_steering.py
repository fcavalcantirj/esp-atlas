"""jr/steering.py — the committed steering constants, fail-closed to the defaults."""
from __future__ import annotations

import json
from pathlib import Path

import steering

REPO = Path(__file__).resolve().parent.parent


def test_the_committed_file_is_valid_and_matches_the_defaults_today():
    cfg, warnings = steering.load(REPO)
    assert warnings == [] and cfg == steering.DEFAULTS
    assert json.loads((REPO / steering.RELPATH).read_text())["yield"]["window_ticks"] == 24


def test_a_missing_or_broken_file_steers_like_the_defaults_and_says_so(tmp_path):
    cfg, w = steering.load(tmp_path)
    assert cfg == steering.DEFAULTS and w == ["jr/steering.json missing: steering defaults"]
    (tmp_path / "jr").mkdir()
    (tmp_path / "jr/steering.json").write_text("{not json")
    cfg, w = steering.load(tmp_path)
    assert cfg == steering.DEFAULTS and "unreadable" in w[0]


def test_each_invalid_value_falls_back_alone(tmp_path):
    (tmp_path / "jr").mkdir()
    (tmp_path / "jr/steering.json").write_text(json.dumps(
        {"hourly_units": 8, "yield": {"window_ticks": 0, "floor_units": "2", "stall_ticks": 36}, "delegate_runs_per_day": True}))
    cfg, w = steering.load(tmp_path)
    assert cfg["hourly_units"] == 8 and cfg["yield"] == {"window_ticks": 24, "floor_units": 1, "stall_ticks": 36, "topics_stall_ticks": 48}
    assert cfg["delegate_runs_per_day"] == 2 and len(w) == 3
