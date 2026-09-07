"""Tests for jr/stage_boardmap.py — the Track B unit, end to end on a tmp tree with fake network.
The tmp root carries a COPY of the real data/boards + data/modules (the stage resolves against
the tree it writes), so nothing real is written."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import stage_boardmap as sb
import tick
from budget import Budget, BudgetExceeded

REPO = Path(__file__).resolve().parent.parent
FIX = Path(__file__).resolve().parent / "fixtures" / "derive"
MARAUDER_RELEASE = json.loads((FIX / "marauder-release.json").read_text())
RELEASE_PAGE = f"https://github.com/justcallmekoko/ESP32Marauder/releases/tag/{MARAUDER_RELEASE['tag_name']}"
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
    shutil.copytree(REPO / "data" / "boards", tmp_path / "data" / "boards")
    shutil.copytree(REPO / "data" / "modules", tmp_path / "data" / "modules")
    (tmp_path / "data" / "firmware" / "marauder").mkdir(parents=True)
    (tmp_path / "data" / "firmware" / "marauder" / "firmware.md").write_text(FW)
    (tmp_path / "data" / "firmware" / "nogithub").mkdir(parents=True)
    (tmp_path / "data" / "firmware" / "nogithub" / "firmware.md").write_text(FW.replace("id: marauder", "id: nogithub").replace("https://github.com/justcallmekoko/ESP32Marauder", "https://gitlab.com/x/y"))
    (tmp_path / "data" / "recipes").mkdir()
    return tmp_path


def _gh_from(api, counter=None):
    def gh(*a):
        if counter is not None:
            counter["api"] += 1
        return SimpleNamespace(returncode=0, stdout=json.dumps(api(a[1])))
    return gh


def ctx(root, dry_run=False, budget=None, api=fake_api, counter=None):
    """A TickContext wired like the tick's: gh goes through budget.wrap, so API calls are charged."""
    budget = budget or Budget(clock=lambda: 0.0)
    return tick.TickContext(root=root, ledger_path=root / "jr" / "proposed_ledger.json", now=NOW,
                            gh=budget.wrap(_gh_from(api, counter)), git=lambda *a: None,
                            budget=budget, dry_run=dry_run, env={})


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


def test_select_firmware_prefers_measured_under_map_over_fewest_recipes(root):
    (root / "data" / "firmware" / "full").mkdir()
    (root / "data" / "firmware" / "full" / "firmware.md").write_text(FW.replace("id: marauder", "id: full"))
    declared = ["m5cardputer", "m5stick-cplus2", "m5nanoc6"]      # declared, none has a recipe → missing 3
    for b in ["m5stamp-s3", "m5dial", "m5tough", "m5paper", "m5core2"]:
        d = root / "data" / "recipes" / f"{b}__full"
        d.mkdir(parents=True)
        (d / "recipe.md").write_text("x\n")
    (root / "data" / "firmware" / "full" / "signals.json").write_text(json.dumps({
        "fetched": "2026-08-01", "errors": 0, "signals": [{"token": "t"}],
        "resolved": {"boards": declared, "socs": [], "unresolved": []}}))
    (root / "data" / "firmware" / "empty").mkdir()                # no signals, no recipes
    (root / "data" / "firmware" / "empty" / "firmware.md").write_text(FW.replace("id: marauder", "id: empty"))
    assert sb.select_firmware(root, 1, NOW) == ["full"]           # 5 recipes + 3 missing beats 0 recipes + unmeasured
    assert sb.select_firmware(root, 3, NOW) == ["full", "empty", "marauder"]


def test_select_firmware_treats_failed_signals_as_unmeasured(root):
    (root / "data" / "firmware" / "full").mkdir()
    (root / "data" / "firmware" / "full" / "firmware.md").write_text(FW.replace("id: marauder", "id: full"))
    (root / "data" / "firmware" / "full" / "signals.json").write_text(json.dumps({
        "fetched": "2026-08-01", "errors": 0, "signals": [{"token": "t"}],
        "resolved": {"boards": ["m5cardputer", "m5stick-cplus2"], "socs": [], "unresolved": []}}))
    (root / "data" / "firmware" / "broken").mkdir()
    (root / "data" / "firmware" / "broken" / "firmware.md").write_text(FW.replace("id: marauder", "id: broken"))
    (root / "data" / "firmware" / "broken" / "signals.json").write_text(json.dumps({
        "fetched": "2026-09-06", "errors": 2, "signals": [],     # fresh but failed → unmeasured: not skipped
        "resolved": {"boards": ["m5cardputer", "m5stick-cplus2", "m5nanoc6"], "socs": [], "unresolved": []}}))
    assert sb.select_firmware(root, 1, NOW) == ["full"]           # 2 missing beats a failed file's 5 phantom boards
    assert "broken" in sb.select_firmware(root, 9, NOW)           # failed file: selectable, not freshness-skipped
    r = sb.map_one("marauder", root=root, api=fake_api, raw=fake_raw, today="2026-09-07")
    assert {"m5cardputer__marauder", "m5stick-cplus2__marauder", "m5nanoc6__marauder"} <= set(r["written"])
    assert r["existing"] == [] and r["refused"] == [] and r["unresolved"] > 0 and r["signals"] == 26 and r["errors"] == 0
    assert "data/firmware/marauder/signals.json" in r["paths"] and "data/firmware/marauder/firmware.md" in r["paths"]
    assert "esp32-s3" in r["socs_added"] and "esp32-c6" in r["socs_added"]
    fw = (root / "data/firmware/marauder/firmware.md").read_text()
    assert "- esp32-s3" in fw and "- esp32-c6" in fw and fw.endswith("Body.\n")
    import yaml
    fm = yaml.safe_load(fw.split("\n---\n")[0].split("---\n", 1)[1])
    soc_sources = [s for s in fm["sources"] if s["field"] == "socs"]
    assert soc_sources == [{"field": "socs", "url": RELEASE_PAGE, "verified": "2026-09-07"}]   # the page that lists every proving asset
    assert not any(".bin" in s["url"] for s in fm["sources"])
    sig = json.loads((root / "data/firmware/marauder/signals.json").read_text())
    assert sig["repo"] == "justcallmekoko/ESP32Marauder" and sig["fetched"] == "2026-09-07" and sig["errors"] == 0
    assert "m5cardputer" in sig["resolved"]["boards"] and sig["calls"] >= 3
    rec = (root / "data/recipes/m5cardputer__marauder/recipe.md").read_text()
    assert "method: release-bin" in rec and "bin_url" not in rec
    assert "esp32_marauder_v1_15_1_20260824_m5cardputer.bin" in rec                  # named in the prose for the human
    assert f"  url: {RELEASE_PAGE}\n" in rec
    # second run: nothing new, signals refreshed, socs untouched
    r2 = sb.map_one("marauder", root=root, api=fake_api, raw=fake_raw, today="2026-09-08")
    assert r2["written"] == [] and set(r2["existing"]) == set(r["written"]) and r2["socs_added"] == []
    assert r2["paths"] == ["data/firmware/marauder/signals.json"]


def test_map_one_resolves_against_root_not_the_clone(root):
    shutil.rmtree(root / "data" / "boards" / "m5stack")                    # root's catalog lacks every M5Stack board
    r = sb.map_one("marauder", root=root, api=fake_api, raw=fake_raw, today="2026-09-07")
    assert not any(w.startswith("m5") for w in r["written"]) and r["refused"] == []
    sig = json.loads((root / "data/firmware/marauder/signals.json").read_text())
    assert "m5cardputer" not in sig["resolved"]["boards"] and "m5cardputer" in sig["resolved"]["unresolved"]


def test_map_one_dry_run_writes_nothing_but_reports(root):
    r = sb.map_one("marauder", root=root, api=fake_api, raw=fake_raw, today="2026-09-07", dry_run=True)
    assert r["paths"] == [] and "m5cardputer__marauder" in r["would_write"]
    assert not (root / "data/firmware/marauder/signals.json").exists()
    assert not list((root / "data/recipes").iterdir())


def test_map_one_failed_read_persists_nothing(root):
    def api_403(path):
        raise RuntimeError("gh: API rate limit exceeded (HTTP 403)")
    r = sb.map_one("marauder", root=root, api=api_403, raw=fake_raw, today="2026-09-07")
    assert r["failed"] is True and r["paths"] == [] and r["errors"] >= 2
    assert r["notes"][-1].startswith("read failed (")
    assert not (root / "data/firmware/marauder/signals.json").exists()
    assert not list((root / "data/recipes").iterdir())
    assert (root / "data/firmware/marauder/firmware.md").read_text() == FW


def test_map_one_degraded_read_keeps_the_previous_signals(root):
    sb.map_one("marauder", root=root, api=fake_api, raw=fake_raw, today="2026-09-01")
    before = (root / "data/firmware/marauder/signals.json").read_text()
    def api_flaky(path):
        if "releases" in path:
            raise RuntimeError("HTTP 502 Bad Gateway")
        return fake_api(path)
    r = sb.map_one("marauder", root=root, api=api_flaky, raw=fake_raw, today="2026-09-09")
    assert r["errors"] == 1 and r["signals"] == 0 and r["failed"] is True     # nothing seen + an error → not a measurement
    assert (root / "data/firmware/marauder/signals.json").read_text() == before
    def api_partial(path):                                                     # sees SOMETHING, but fewer boards, with an error
        if "releases" in path:
            raise RuntimeError("HTTP 502 Bad Gateway")
        if "git/trees" in path:
            return {"tree": [{"path": "sdkconfig.defaults.esp32s3", "type": "blob"}], "truncated": False}
        return fake_api(path)
    r = sb.map_one("marauder", root=root, api=api_partial, raw=fake_raw, today="2026-09-09")
    assert r["errors"] == 1 and r["signals"] >= 1 and not r.get("failed")
    assert (root / "data/firmware/marauder/signals.json").read_text() == before
    assert "data/firmware/marauder/signals.json" not in r["paths"]
    assert any(n.startswith("degraded read (1 unavailable endpoint(s), ") and n.endswith("previous signals kept") for n in r["notes"])


def test_stage_run_returns_a_stage_result_and_charges_each_call_once(root):
    n = {"api": 0, "raw": 0}
    def counting_raw(url):
        n["raw"] += 1
        return None
    b = Budget(max_calls=150, clock=lambda: 0.0)
    c = ctx(root, budget=b, counter=n)
    res = sb.run(c, budget=2, raw=counting_raw)
    assert res.name == "boardmap" and res.admitted >= 3 and res.rejects == {} and not res.needs_human
    assert any(p.startswith("data/recipes/") for p in res.paths) and "data/firmware/marauder/signals.json" in res.paths
    assert "marauder: +" in res.summary
    assert b.calls == n["api"] + n["raw"] and n["api"] >= 3          # wrapped gh + wrapped raw: one charge per call, no post-hoc double


def test_stage_run_stops_when_the_tick_budget_cannot_afford_another_derivation(root):
    c = ctx(root, budget=Budget(max_calls=10, clock=lambda: 0.0))
    res = sb.run(c, budget=2, raw=fake_raw)
    assert res.paths == [] and "tick budget low" in res.summary and c.budget.calls == 0
    c = ctx(root, budget=Budget(max_seconds=30, clock=lambda: 0.0))
    res = sb.run(c, budget=2, raw=fake_raw)
    assert res.paths == [] and "tick budget low" in res.summary and "30s left" in res.summary


def test_stage_run_dry_run_reads_the_network_charged_but_writes_nothing(root):
    n = {"api": 0, "raw": 0}
    b = Budget(clock=lambda: 0.0)
    c = ctx(root, dry_run=True, budget=b, counter=n)
    res = sb.run(c, budget=2, raw=lambda u: (n.__setitem__("raw", n["raw"] + 1), None)[1])
    assert res.paths == [] and "would write" in res.summary
    assert b.calls == n["api"] + n["raw"] >= 3
    assert not list((root / "data/recipes").iterdir()) and not (root / "data/firmware/marauder/signals.json").exists()


def test_stage_run_isolates_one_firmware_failure_and_flags_needs_human(root, monkeypatch):
    (root / "data" / "firmware" / "second").mkdir()
    (root / "data" / "firmware" / "second" / "firmware.md").write_text(FW.replace("id: marauder", "id: second").replace("ESP32Marauder", "Second"))
    real = sb.map_one
    def flaky(fid, **kw):
        if fid == "marauder":
            raise ValueError("frontmatter went sideways")
        return real(fid, **kw)
    monkeypatch.setattr(sb, "map_one", flaky)
    res = sb.run(ctx(root), budget=2, raw=fake_raw)
    assert res.rejects == {"error": 1} and res.needs_human
    assert "marauder: failed ValueError: frontmatter went sideways" in res.summary and "second:" in res.summary
    assert "data/firmware/second/signals.json" in res.paths


def test_stage_run_reports_an_unreadable_firmware_and_continues(root):
    (root / "data" / "firmware" / "second").mkdir()
    (root / "data" / "firmware" / "second" / "firmware.md").write_text(FW.replace("id: marauder", "id: second").replace("ESP32Marauder", "Second"))
    def api(path):
        if "Second" in path:
            raise RuntimeError("HTTP 503 Service Unavailable")
        return fake_api(path)
    res = sb.run(ctx(root, api=api), budget=2, raw=fake_raw)
    assert res.rejects == {"unreadable": 1} and not res.needs_human
    assert "second: read failed (" in res.summary and "marauder: +" in res.summary
    assert not (root / "data/firmware/second/signals.json").exists()


def test_stage_run_keeps_earlier_work_when_the_budget_runs_out_mid_derivation(root, monkeypatch):
    (root / "data" / "firmware" / "second").mkdir()
    (root / "data" / "firmware" / "second" / "firmware.md").write_text(FW.replace("id: marauder", "id: second").replace("ESP32Marauder", "Second"))
    real = sb.map_one
    def out_of_budget(fid, **kw):
        if fid == "second":
            raise BudgetExceeded("time budget exhausted after 361s (raw)")
        return real(fid, **kw)
    monkeypatch.setattr(sb, "map_one", out_of_budget)
    res = sb.run(ctx(root), budget=2, raw=fake_raw)
    assert "stopped during second: time budget exhausted" in res.summary and "marauder: +" in res.summary
    assert "data/firmware/marauder/signals.json" in res.paths and res.admitted >= 3
