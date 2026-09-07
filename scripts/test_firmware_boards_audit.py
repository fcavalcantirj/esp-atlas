"""Tests for scripts/firmware_boards_audit.py — the offline G1 audit over persisted signals."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import firmware_boards_audit as fba  # noqa: E402


def _tree(tmp_path):
    d = tmp_path / "data"
    for fid in ("bruce", "wled", "quiet", "broken"):
        (d / "firmware" / fid).mkdir(parents=True)
        (d / "firmware" / fid / "firmware.md").write_text(f"---\nid: {fid}\n---\n")
    (d / "firmware" / "bruce" / "signals.json").write_text(json.dumps(
        {"fetched": "2026-09-07", "resolved": {"boards": ["m5cardputer", "m5stick-cplus2", "lilygo-t-deck"], "socs": ["esp32-s3"], "unresolved": ["cyd-2432s028", "foo"]}}))
    (d / "firmware" / "wled" / "signals.json").write_text(json.dumps(
        {"fetched": "2026-09-06", "resolved": {"boards": ["esp32-s3-devkitc-1"], "socs": [], "unresolved": []}}))
    (d / "firmware" / "broken" / "signals.json").write_text("{not json")
    (d / "firmware" / "unread").mkdir()
    (d / "firmware" / "unread" / "firmware.md").write_text("---\nid: unread\n---\n")
    (d / "firmware" / "unread" / "signals.json").write_text(json.dumps(          # a failed read is not a measurement
        {"fetched": "2026-09-07", "signals": [], "errors": 3, "resolved": {"boards": [], "socs": [], "unresolved": []}}))
    for rid in ("m5cardputer__bruce", "m5atom-lite__bruce", "esp32-s3-devkitc-1__wled"):
        (d / "recipes" / rid).mkdir(parents=True)
    return d


def test_audit_measures_missing_extra_and_unmeasured(tmp_path):
    rep = fba.audit(_tree(tmp_path))
    by = {m["id"]: m for m in rep["measured"]}
    assert set(by) == {"bruce", "wled"} and rep["unmeasured"] == ["broken", "quiet", "unread"]
    assert by["bruce"]["missing"] == ["lilygo-t-deck", "m5stick-cplus2"]
    assert by["bruce"]["extra"] == ["m5atom-lite"] and by["bruce"]["unresolved"] == 2
    assert by["wled"]["missing"] == [] and by["wled"]["recipes"] == ["esp32-s3-devkitc-1"]


def test_render_ci_warnings_and_summary(tmp_path):
    lines = fba.render(fba.audit(_tree(tmp_path)), ci=True)
    assert any(l.startswith("::warning file=data/firmware/bruce/firmware.md::G1 under-mapped: 2") for l in lines)
    assert not any("wled" in l and "::warning" in l for l in lines)
    assert lines[-1] == "SUMMARY: 2 measured, 1 under-mapped, 2 missing recipe(s), 3 unmeasured (no signals.json)"


def test_main_warn_mode_exits_zero_and_strict_exits_one(tmp_path, capsys):
    d = _tree(tmp_path)
    assert fba.main(["--data-dir", str(d), "--ci"]) == 0
    assert fba.main(["--data-dir", str(d), "--ci", "--strict"]) == 1
    out = capsys.readouterr().out
    assert "UNDER-MAPPED" in out and "SUMMARY" in out


def test_real_tree_runs_offline_and_reports_every_firmware(capsys):
    rc = fba.main(["--ci"])
    out = capsys.readouterr().out
    assert rc == 0 and out.strip().splitlines()[-1].startswith("SUMMARY:")
    assert "unmeasured" in out          # today no firmware carries signals.json yet
