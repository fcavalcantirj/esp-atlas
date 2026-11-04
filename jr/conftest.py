"""Shared jr/ test fixtures."""
from __future__ import annotations

import pytest

import derive
import device_evidence
import drain
import tick


@pytest.fixture(autouse=True)
def _isolated_tick_lock(tmp_path, monkeypatch):
    """Every real-run tick under pytest takes its overlap lock in tmp_path, never the box's lock
    file: a test run must neither block nor be blocked by a live hourly tick on the same machine."""
    monkeypatch.setattr(tick, "DEFAULT_TICK_LOCK", tmp_path / "jr-tick-run.lock")


@pytest.fixture(autouse=True)
def _no_live_device_evidence(monkeypatch):
    """No jr test reaches GitHub. derive's default network effects raise (a test that forgets to
    inject `api`/`raw` sees its reads fail — derive._Calls turns that into an unreadable result,
    so the candidate is skipped, never fetched), and the drain's live device-build
    evidence check (jr/device_evidence.py) passes by default so the gates a drain test targets stay
    the only ones that bite; tests of that gate inject `evidence=` or patch it themselves. The
    gate's ranged GET of a release asset is offline the same way."""
    monkeypatch.setattr(derive, "default_api", _offline)
    monkeypatch.setattr(derive, "default_raw", _offline)
    monkeypatch.setattr(device_evidence, "default_head", _offline)
    monkeypatch.setattr(drain, "default_device_evidence",
                        lambda owner_repo, ref: {"ok": True, "verdict": device_evidence.ESP_TARGET, "kind": "arduino_sketch",
                                                 "url": None, "calls": 0, "notes": [], "ambiguous": []})


def _offline(*a, **k):
    raise RuntimeError("live network in a jr test: inject api/raw/head")


# The ESP fqbn `esp_sketch_raw` serves for every sketch.yaml.
ESP_SKETCH_YAML = "default_fqbn: esp32:esp32:m5stack_cardputer\n"


@pytest.fixture
def esp_sketch_raw(monkeypatch):
    """derive.default_raw (the stages' raw reader when a test passes none) serves every
    `sketch.yaml` as an ESP fqbn; any other read stays offline."""
    def raw(url):
        if url.endswith("/sketch.yaml"):
            return ESP_SKETCH_YAML
        return _offline(url)
    monkeypatch.setattr(derive, "default_raw", raw)
