"""Tests for scripts/device_evidence_audit.py — the read-only list of catalogued firmware with no
device-build signal (review finding 3). No network: the check is injected."""
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
    "rebelthor/warble": {"ok": False, "kind": None, "url": None, "notes": []},
    "z/sketchy": {"ok": True, "kind": "arduino_sketch", "url": "https://github.com/z/sketchy/blob/HEAD/a.ino", "notes": []},
    "z/flaky": {"ok": None, "kind": None, "url": None, "notes": ["api unavailable: HTTP 502"]},
}


def _data(tmp_path):
    for fid, url in (("warble", "https://github.com/rebelthor/warble"), ("sketchy", "https://github.com/z/sketchy"),
                     ("flaky", "https://github.com/z/flaky"), ("offsite", "https://example.org/fw")):
        d = tmp_path / "firmware" / fid
        d.mkdir(parents=True)
        (d / "firmware.md").write_text(FW.format(id=fid, url=url))
    return tmp_path


def _snapshot(root):
    return {p: p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_lists_firmware_with_no_device_build_signal_and_writes_nothing(tmp_path):
    root = _data(tmp_path)
    before = _snapshot(root)
    checked = []
    report = audit.audit(root, check=lambda repo: checked.append(repo) or RESULTS[repo])
    assert [e["id"] for e in report["no_signal"]] == ["warble"]
    assert [e["id"] for e in report["unknown"]] == ["flaky"]
    assert [e["id"] for e in report["not_github"]] == ["offsite"]
    sketchy = next(e for e in report["entries"] if e["id"] == "sketchy")
    assert sketchy["kind"] == "arduino_sketch" and sketchy["evidence"].endswith("a.ino")
    assert sorted(checked) == sorted(RESULTS)                 # a non-GitHub url is never fetched
    assert _snapshot(root) == before                          # read-only


def test_only_limits_the_checked_ids(tmp_path):
    root = _data(tmp_path)
    report = audit.audit(root, check=lambda repo: RESULTS[repo], only={"warble"})
    assert [e["id"] for e in report["entries"]] == ["warble"]


def test_report_prints_the_review_list(tmp_path, capsys):
    report = audit.audit(_data(tmp_path), check=lambda repo: RESULTS[repo])
    audit.print_report(report)
    out = capsys.readouterr().out
    assert "1 with NO signal" in out and "    warble  (rebelthor/warble)" in out
    assert "flaky" in out and "HTTP 502" in out and "offsite" in out
