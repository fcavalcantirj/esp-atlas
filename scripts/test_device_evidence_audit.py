"""Tests for scripts/device_evidence_audit.py — the read-only audit of catalogued firmware in the
device-build gate's three classes: esp_target, not_device_firmware, needs_review (review finding
3). No network: the check is injected."""
from __future__ import annotations

import device_evidence_audit as audit

FW = """---
id: {id}
type: firmware
name: {id}
url: {url}
category: multi
socs:
- esp32-s3
sources:
- field: '*'
  url: {url}
  verified: '2026-11-03'
---

Body.
"""

RESULTS = {
    "rebelthor/warble": {"ok": False, "verdict": "not_device_firmware", "kind": None, "url": None, "notes": [], "ambiguous": []},
    "z/sketchy": {"ok": True, "verdict": "esp_target", "kind": "arduino_sketch",
                  "url": "https://github.com/z/sketchy/blob/HEAD/sketch.yaml#L1", "notes": [], "ambiguous": []},
    "z/bare": {"ok": False, "verdict": "needs_review", "kind": "arduino_sketch", "url": "https://github.com/z/bare/blob/HEAD/b.ino",
               "notes": [], "ambiguous": [{"kind": "arduino_sketch", "url": "https://github.com/z/bare/blob/HEAD/b.ino",
                                           "why": "a .ino but no ESP board named"}]},
    "z/flaky": {"ok": None, "verdict": None, "kind": None, "url": None, "notes": ["api unavailable: HTTP 502"], "ambiguous": []},
}


def _data(tmp_path):
    for fid, url in (("warble", "https://github.com/rebelthor/warble"), ("sketchy", "https://github.com/z/sketchy"),
                     ("bare", "https://github.com/z/bare"), ("flaky", "https://github.com/z/flaky"),
                     ("offsite", "https://example.org/fw")):
        d = tmp_path / "firmware" / fid
        d.mkdir(parents=True)
        (d / "firmware.md").write_text(FW.format(id=fid, url=url))
    return tmp_path


def _snapshot(root):
    return {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_sorts_firmware_into_the_three_classes_and_writes_nothing(tmp_path):
    root = _data(tmp_path)
    before = _snapshot(root)
    checked = []
    report = audit.audit(root, check=lambda repo: checked.append(repo) or RESULTS[repo])
    assert [e["id"] for e in report["esp_target"]] == ["sketchy"]
    assert [e["id"] for e in report["not_device_firmware"]] == ["warble"]
    assert [e["id"] for e in report["needs_review"]] == ["bare"]
    assert report["needs_review"][0]["why"] == "a .ino but no ESP board named"
    assert [e["id"] for e in report["unknown"]] == ["flaky"]
    assert [e["id"] for e in report["not_github"]] == ["offsite"]
    sketchy = next(e for e in report["entries"] if e["id"] == "sketchy")
    assert sketchy["kind"] == "arduino_sketch" and sketchy["evidence"].endswith("sketch.yaml#L1")
    assert sorted(checked) == sorted(RESULTS)                 # a non-GitHub url is never fetched
    assert _snapshot(root) == before                          # read-only


def test_only_limits_the_checked_ids(tmp_path):
    root = _data(tmp_path)
    report = audit.audit(root, check=lambda repo: RESULTS[repo], only={"warble"})
    assert [e["id"] for e in report["entries"]] == ["warble"]


def test_report_prints_the_three_classes(tmp_path, capsys):
    report = audit.audit(_data(tmp_path), check=lambda repo: RESULTS[repo])
    audit.print_report(report)
    out = capsys.readouterr().out
    assert "1 esp_target · 1 not_device_firmware · 1 needs_review · 1 unknown · 1 not a GitHub repo" in out
    assert "ESP TARGET" in out and "    sketchy  (z/sketchy): arduino_sketch https://github.com/z/sketchy/blob/HEAD/sketch.yaml#L1" in out
    assert "NOT DEVICE FIRMWARE" in out and "    warble  (rebelthor/warble)" in out
    assert "NEEDS REVIEW" in out and "    bare  (z/bare): arduino_sketch https://github.com/z/bare/blob/HEAD/b.ino — a .ino but no ESP board named" in out
    assert out.index("ESP TARGET") < out.index("NOT DEVICE FIRMWARE") < out.index("NEEDS REVIEW") < out.index("UNKNOWN")
    assert "flaky" in out and "HTTP 502" in out and "offsite" in out
