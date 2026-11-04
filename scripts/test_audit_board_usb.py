"""Tests for scripts/audit_board_usb.py — the read-only audit of every existing board `usb_serial` /
`download_mode` value (owner mandate G3, 2026-11-04): board-specific evidence, toolchain
corroboration, a conflict, or nothing. It writes nothing. No network: the fetch is injected."""
from __future__ import annotations

import json
from pathlib import Path

import audit_board_usb as audit
import board_arduino as ba
import board_manifest as bm

REPO = Path(__file__).resolve().parent.parent
BOARDS_TXT = (REPO / "jr" / "fixtures" / "board_arduino" / "boards.txt").read_text()
CH340_MANIFEST = (REPO / "jr" / "fixtures" / "board_manifest" / "ch340_esp32.json").read_text()
VENDOR = "https://vendor.example/board"


def _board(root: Path, board_id: str, fields: str, sources: list[tuple[str, str]]) -> Path:
    d = root / "boards" / "fixture" / board_id
    d.mkdir(parents=True, exist_ok=True)
    src = "".join(f"- field: '{f}'\n  url: {u}\n  verified: '2026-11-01'\n" for f, u in sources)
    (d / "board.md").write_text(
        f"---\nid: {board_id}\ntype: board\nbrand: fixture\nname: {board_id}\nsoc: esp32\n{fields}"
        f"sources:\n{src}---\n\n# {board_id}\n")
    return d / "board.md"


def _tree(root: Path, monkeypatch) -> Path:
    soc = root / "socs" / "esp32"
    soc.mkdir(parents=True)
    (soc / "chip.md").write_text("---\nid: esp32\ntype: soc\nusb:\n  native: false\n  type: none\n---\n")
    _board(root, "vendor-board", "usb_serial: ch340\ndownload_mode:\n  mode: manual\n  steps: Hold BOOT\n",
           [("usb_serial", VENDOR), ("download_mode", VENDOR)])
    _board(root, "pio-board", "usb_serial: ch340\n",
           [("usb_serial", bm.manifest_url("fixture_ch340"))])
    _board(root, "conflict-board", "usb_serial: cp2102n\n", [("usb_serial", VENDOR)])
    _board(root, "bridge-cited", "usb_serial: ch340\n", [("usb.bridge", VENDOR)])
    _board(root, "bare-board", "usb_serial: ch340\ndownload_mode:\n  mode: auto\n", [("*", VENDOR)])
    _board(root, "old-arduino", "usb_serial: ch340\n",
           [("usb_serial", "https://raw.githubusercontent.com/espressif/arduino-esp32/"
                           "56a7eb7269a8dd524c72c6752adaaad7814a0766/boards.txt")])
    _board(root, "empty-board", "", [("*", VENDOR)])
    for board_id in ("vendor-board", "pio-board"):
        monkeypatch.setitem(bm.PIO_BOARD_IDS, board_id, "fixture_ch340")
    monkeypatch.setitem(ba.ARDUINO_BOARD_KEYS, "conflict-board", "fixture_ch340")
    return root


def _fetch(log: list | None = None):
    pages = {bm.manifest_url("fixture_ch340"): CH340_MANIFEST, ba.BOARDS_TXT_URL: BOARDS_TXT}

    def fetch(url):
        if log is not None:
            log.append(url)
        if url in pages:
            return {"ok": True, "status": 200, "text": pages[url]}
        return {"ok": False, "status": 404, "error": "HTTP 404"}
    return fetch


def _snapshot(root: Path) -> dict:
    return {str(p): (p.read_bytes(), p.stat().st_mtime_ns) for p in sorted(root.rglob("*")) if p.is_file()}


def _by(report: dict) -> dict:
    return {(e["board"], e["field"]): e for e in report["entries"]}


def test_every_existing_value_is_classified_by_what_supports_it(tmp_path, monkeypatch):
    root = _tree(tmp_path, monkeypatch)
    by = _by(audit.audit(root, fetch=_fetch()))
    assert by[("vendor-board", "usb_serial")]["class"] == audit.BOARD_EVIDENCE
    assert by[("vendor-board", "usb_serial")]["corroborated"] is True
    assert by[("vendor-board", "download_mode")]["class"] == audit.BOARD_EVIDENCE
    assert by[("pio-board", "usb_serial")]["class"] == audit.TOOLCHAIN_CORROBORATION
    assert by[("conflict-board", "usb_serial")]["class"] == audit.CONFLICT
    assert by[("conflict-board", "usb_serial")]["checks"] == [
        {"source": "boards_txt", "url": ba.BOARDS_TXT_URL, "value": "ch340", "verdict": "conflicts"}]
    assert by[("bridge-cited", "usb_serial")]["class"] == audit.BOARD_EVIDENCE
    # a blanket '*' citation is not evidence of the USB connection or the download mode
    assert by[("bare-board", "usb_serial")]["class"] == audit.NONE
    assert by[("bare-board", "download_mode")]["class"] == audit.NONE
    # a toolchain citation at any commit, not only the pinned one, is toolchain-only support
    assert by[("old-arduino", "usb_serial")]["class"] == audit.TOOLCHAIN_CORROBORATION
    assert ("empty-board", "usb_serial") not in by


def test_counts_cover_every_value_per_field_and_class(tmp_path, monkeypatch):
    report = audit.audit(_tree(tmp_path, monkeypatch), fetch=_fetch())
    assert report["counts"]["usb_serial"] == {audit.BOARD_EVIDENCE: 2, audit.TOOLCHAIN_CORROBORATION: 2,
                                              audit.CONFLICT: 1, audit.NONE: 1}
    assert report["counts"]["download_mode"] == {audit.BOARD_EVIDENCE: 1, audit.TOOLCHAIN_CORROBORATION: 0,
                                                 audit.CONFLICT: 0, audit.NONE: 1}


def test_download_mode_is_never_checked_against_a_toolchain(tmp_path, monkeypatch):
    by = _by(audit.audit(_tree(tmp_path, monkeypatch), fetch=_fetch()))
    assert by[("vendor-board", "download_mode")]["checks"] == []


def test_each_pinned_source_is_fetched_once_for_the_whole_run(tmp_path, monkeypatch):
    log: list = []
    audit.audit(_tree(tmp_path, monkeypatch), fetch=_fetch(log))
    assert log.count(ba.BOARDS_TXT_URL) == 1
    assert log.count(bm.manifest_url("fixture_ch340")) == 1


def test_offline_classifies_from_citations_only_and_fetches_nothing(tmp_path, monkeypatch):
    report = audit.audit(_tree(tmp_path, monkeypatch), fetch=None)
    by = _by(report)
    assert by[("conflict-board", "usb_serial")]["class"] == audit.BOARD_EVIDENCE
    assert by[("pio-board", "usb_serial")]["class"] == audit.TOOLCHAIN_CORROBORATION
    assert all(e["checks"] == [] for e in report["entries"])


def test_the_audit_writes_nothing(tmp_path, monkeypatch, capsys):
    root = _tree(tmp_path / "data", monkeypatch)
    before = _snapshot(tmp_path)
    audit.audit(root, fetch=_fetch())
    audit.main(["--data-dir", str(root)], fetch=_fetch())
    audit.main(["--data-dir", str(root), "--json"], fetch=_fetch())
    capsys.readouterr()
    assert _snapshot(tmp_path) == before


def test_main_lists_every_value_and_prints_the_counts(tmp_path, monkeypatch, capsys):
    root = _tree(tmp_path, monkeypatch)
    assert audit.main(["--data-dir", str(root)], fetch=_fetch()) == 0
    out = capsys.readouterr().out
    assert "conflict  fixture/conflict-board  usb_serial=cp2102n" in out
    assert f"boards_txt ch340 conflicts {ba.BOARDS_TXT_URL}" in out
    assert "usb_serial: board_evidence 2, toolchain_corroboration 2, conflict 1, none 1" in out
    assert "download_mode: board_evidence 1, toolchain_corroboration 0, conflict 0, none 1" in out


def test_main_json_is_the_report(tmp_path, monkeypatch, capsys):
    root = _tree(tmp_path, monkeypatch)
    audit.main(["--data-dir", str(root), "--json"], fetch=_fetch())
    data = json.loads(capsys.readouterr().out)
    assert data["counts"]["usb_serial"][audit.CONFLICT] == 1
    assert len(data["entries"]) == 8


def test_a_board_with_unreadable_frontmatter_is_listed_not_fatal(tmp_path, monkeypatch, capsys):
    root = _tree(tmp_path, monkeypatch)
    broken = root / "boards" / "fixture" / "broken-board"
    broken.mkdir()
    (broken / "board.md").write_text("no frontmatter here\n")
    report = audit.audit(root, fetch=None)
    assert report["unreadable"] == [str(broken / "board.md")]
    assert audit.main(["--data-dir", str(root), "--offline"]) == 0
    assert "unreadable" in capsys.readouterr().out


def test_a_board_without_a_soc_is_classified_from_citations_alone(tmp_path, monkeypatch):
    root = _tree(tmp_path, monkeypatch)
    path = root / "boards" / "fixture" / "pio-board" / "board.md"
    path.write_text(path.read_text().replace("soc: esp32\n", ""))
    by = _by(audit.audit(root, fetch=_fetch()))
    assert by[("pio-board", "usb_serial")]["checks"] == []
    assert by[("pio-board", "usb_serial")]["class"] == audit.TOOLCHAIN_CORROBORATION
