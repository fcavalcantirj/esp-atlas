"""Tests for jr/stage_boardmap.py — the Track B unit, end to end on a tmp tree with fake network.
The real data/boards tree is read (board socs, the resolver); nothing real is written."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import stage_boardmap as sb
import tick
from budget import Budget

FIX = Path(__file__).resolve().parent / "fixtures" / "derive"
MARAUDER_RELEASE = json.loads((FIX / "marauder-release.json").read_text())
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)

FW = """\
---
id: marauder
type: firmware
name: "ESP32 Marauder"
url: https://github.com/justcallmekoko/ESP32Marauder
category: pentest
socs:
- esp32
sources:
- field: '*'
  url: https://github.com/justcallmekoko/ESP32Marauder
  verified: '2026-08-24'
---

Body.
"""


def fake_api(path):
    if path == "repos/justcallmekoko/ESP32Marauder":
        return {"default_branch": "master"}
    if path == "repos/justcallmekoko/ESP32Marauder/releases/latest":
        return MARAUDER_RELEASE
    if path.startswith("repos/justcallmekoko/ESP32Marauder/git/trees/"):
        return {"tree": [{"path": "README.md", "type": "blob"}], "truncated": False}
    raise RuntimeError("404 " + path)


def fake_raw(url):
    return None


@pytest.fixture
def root(tmp_path):
    (tmp_path / "data" / "firmware" / "marauder").mkdir(parents=True)
    (tmp_path / "data" / "firmware" / "marauder" / "firmware.md").write_text(FW)
    (tmp_path / "data" / "firmware" / "nogithub").mkdir(parents=True)
    (tmp_path / "data" / "firmware" / "nogithub" / "firmware.md").write_text(FW.replace("id: marauder", "id: nogithub").replace("https://github.com/justcallmekoko/ESP32Marauder", "https://gitlab.com/x/y"))
    (tmp_path / "data" / "recipes").mkdir()
    return tmp_path


def ctx(root, dry_run=False, budget=None):
    return tick.TickContext(root=root, ledger_path=root / "jr" / "proposed_ledger.json", now=NOW,
                            gh=lambda *a: SimpleNamespace(returncode=0, stdout="{}"), git=lambda *a: None,
                            budget=budget or Budget(clock=lambda: 0.0), dry_run=dry_run, env={})


def test_owner_repo_of():
    assert sb.owner_repo_of("https://github.com/justcallmekoko/ESP32Marauder") == "justcallmekoko/ESP32Marauder"
    assert sb.owner_repo_of("https://github.com/o/r.git/") == "o/r"
    assert sb.owner_repo_of("https://gitlab.com/o/r") is None and sb.owner_repo_of("") is None


def test_select_firmware_prefers_under_mapped_and_skips_fresh_and_non_github(root):
    (root / "data" / "firmware" / "second").mkdir()
    (root / "data" / "firmware" / "second" / "firmware.md").write_text(FW.replace("id: marauder", "id: second").replace("ESP32Marauder", "Second"))
    (root / "data" / "recipes" / "m5cardputer__second").mkdir()          # second has 1 recipe → after marauder
    assert sb.select_firmware(root, 5, NOW) == ["marauder", "second"]
    (root / "data" / "firmware" / "marauder" / "signals.json").write_text(json.dumps({"fetched": "2026-09-05"}))
    assert sb.select_firmware(root, 5, NOW) == ["second"]                 # 2 days old → fresh → skipped
    (root / "data" / "firmware" / "marauder" / "signals.json").write_text(json.dumps({"fetched": "2026-08-01"}))
    assert sb.select_firmware(root, 1, NOW) == ["marauder"]               # old signals, fewest recipes → first
    assert "nogithub" not in sb.select_firmware(root, 9, NOW)


def test_map_one_writes_cited_recipes_widens_socs_and_persists_signals(root):
    r = sb.map_one("marauder", root=root, api=fake_api, raw=fake_raw, today="2026-09-07")
    assert {"m5cardputer__marauder", "m5stick-cplus2__marauder", "m5nanoc6__marauder"} <= set(r["written"])
    assert r["existing"] == [] and r["refused"] == [] and r["unresolved"] > 0 and r["signals"] == 26
    assert "data/firmware/marauder/signals.json" in r["paths"] and "data/firmware/marauder/firmware.md" in r["paths"]
    assert "esp32-s3" in r["socs_added"] and "esp32-c6" in r["socs_added"]
    fw = (root / "data/firmware/marauder/firmware.md").read_text()
    assert "socs:\n- esp32\n- esp32-c5\n- esp32-c6\n- esp32-s3" in fw or "- esp32-s3" in fw
    assert "- field: socs" in fw and fw.endswith("Body.\n")
    sig = json.loads((root / "data/firmware/marauder/signals.json").read_text())
    assert sig["repo"] == "justcallmekoko/ESP32Marauder" and sig["fetched"] == "2026-09-07"
    assert "m5cardputer" in sig["resolved"]["boards"] and sig["calls"] >= 3
    rec = (root / "data/recipes/m5cardputer__marauder/recipe.md").read_text()
    assert "method: release-bin" in rec and "esp32_marauder_v1_15_1_20260824_m5cardputer.bin" in rec
    # second run: nothing new, signals refreshed, socs untouched
    r2 = sb.map_one("marauder", root=root, api=fake_api, raw=fake_raw, today="2026-09-08")
    assert r2["written"] == [] and set(r2["existing"]) == set(r["written"]) and r2["socs_added"] == []
    assert r2["paths"] == ["data/firmware/marauder/signals.json"]


def test_map_one_dry_run_writes_nothing_but_reports(root):
    r = sb.map_one("marauder", root=root, api=fake_api, raw=fake_raw, today="2026-09-07", dry_run=True)
    assert r["paths"] == [] and "m5cardputer__marauder" in r["would_write"]
    assert not (root / "data/firmware/marauder/signals.json").exists()
    assert not list((root / "data/recipes").iterdir())


def test_stage_run_returns_a_stage_result_with_paths_and_charges_the_budget(root):
    c = ctx(root, budget=Budget(max_calls=150, clock=lambda: 0.0))
    res = sb.run(c, budget=2, api=fake_api, raw=fake_raw)
    assert res.name == "boardmap" and res.admitted >= 3 and res.rejects == {}
    assert any(p.startswith("data/recipes/") for p in res.paths) and "data/firmware/marauder/signals.json" in res.paths
    assert "marauder: +" in res.summary and c.budget.calls >= 3


def test_stage_run_stops_when_the_tick_budget_cannot_afford_another_derivation(root):
    c = ctx(root, budget=Budget(max_calls=10, clock=lambda: 0.0))
    res = sb.run(c, budget=2, api=fake_api, raw=fake_raw)
    assert res.paths == [] and "tick budget low" in res.summary and c.budget.calls == 0


def test_stage_run_dry_run_reports_without_writing_or_charging(root):
    c = ctx(root, dry_run=True)
    res = sb.run(c, budget=2, api=fake_api, raw=fake_raw)
    assert res.paths == [] and "would write" in res.summary and c.budget.calls == 0
    assert not list((root / "data/recipes").iterdir())
