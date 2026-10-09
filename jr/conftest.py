"""Shared jr/ test fixtures."""
from __future__ import annotations

import pytest

import tick


@pytest.fixture(autouse=True)
def _isolated_tick_lock(tmp_path, monkeypatch):
    """Every real-run tick under pytest takes its overlap lock in tmp_path, never the box's lock
    file: a test run must neither block nor be blocked by a live hourly tick on the same machine."""
    monkeypatch.setattr(tick, "DEFAULT_TICK_LOCK", tmp_path / "jr-tick-run.lock")
