"""Tests for jr/board_manifest.py — G3a: the PlatformIO espressif32 board manifest as a SECOND,
cited source for `usb_serial` (and `download_mode` only when the manifest states it explicitly),
plus the per-field skip reasons board_backfill.backfill_board now reports.

NO NETWORK: every manifest is a committed fixture under jr/fixtures/board_manifest/, served by an
injected fake fetch keyed on the pinned raw.githubusercontent.com URL.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import board_backfill as bb
import board_manifest as bm

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "board_manifest"
TODAY = "2026-11-03"


def _manifest(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


def _raw(name: str) -> str:
    return (FIXTURES / f"{name}.json").read_text()


def _write_soc(root: Path, soc: str, usb_type: str, native: bool = True) -> None:
    d = root / "socs" / soc
    d.mkdir(parents=True, exist_ok=True)
    (d / "chip.md").write_text(
        f"---\nid: {soc}\ntype: soc\nusb:\n  native: {str(native).lower()}\n"
        f"  type: {usb_type}\n---\n\n# {soc}\n")


def _write_board(root: Path, board_id: str, soc: str, extra: str = "") -> Path:
    d = root / "boards" / "espressif" / board_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "board.md").write_text(
        f"---\nid: {board_id}\ntype: board\nbrand: espressif\nname: {board_id}\nsoc: {soc}\n{extra}"
        "sources:\n- field: '*'\n  url: https://example.test/x\n  verified: '2026-01-01'\n---\n\n# b\n")
    return d / "board.md"


def _fetcher(pages: dict, log: list | None = None):
    def fetch(url):
        if log is not None:
            log.append(url)
        if url in pages:
            return {"ok": True, "status": 200, "text": pages[url]}
        return {"ok": False, "status": 404, "error": "HTTP 404"}
    return fetch


def _vendor_url(board_id: str, soc: str) -> str:
    return bb.board_user_guide_url(board_id, soc)


VENDOR_PAGE_NO_USB = "<html><body><h1>Fixture board</h1><p>Getting started.</p></body></html>"


# ── the pinned source ─────────────────────────────────────────────────────────

def test_manifest_url_is_pinned_to_an_immutable_commit():
    assert re.fullmatch(r"[0-9a-f]{40}", bm.PIO_PINNED_REF)
    assert bm.manifest_url("m5stack-atoms3") == (
        "https://raw.githubusercontent.com/platformio/platform-espressif32/"
        f"{bm.PIO_PINNED_REF}/boards/m5stack-atoms3.json")


def test_mapping_is_explicit_record_id_first_then_curated_table_never_guessed(monkeypatch):
    monkeypatch.setitem(bm.PIO_BOARD_IDS, "fixture-board", "fixture_from_table")
    assert bm.manifest_id({"platformio": "explicit_id"}, "fixture-board") == "explicit_id"
    assert bm.manifest_id({}, "fixture-board") == "fixture_from_table"
    # a board id that LOOKS like a manifest name is still not mapped: no fuzzy matching
    assert bm.manifest_id({}, "lolin-s3-pro") is None
    assert bm.manifest_id({}, "unmapped-board") is None


def test_curated_table_values_are_plain_manifest_ids():
    for board_id, pio_id in bm.PIO_BOARD_IDS.items():
        assert re.fullmatch(r"[a-z0-9-]+", board_id), board_id
        assert re.fullmatch(r"[A-Za-z0-9_.-]+", pio_id), pio_id


# ── usb_serial from hwids (fixed vendor-id table) ─────────────────────────────

def test_espressif_vid_on_a_serial_jtag_soc_is_native_usb():
    assert bm.usb_serial_from_manifest(_manifest("native_usb_s3"), serial_jtag=True) == (
        "native-usb-serial-jtag", None)


def test_wch_ch340_vid_writes_ch340():
    assert bm.usb_serial_from_manifest(_manifest("ch340_esp32"), serial_jtag=False) == ("ch340", None)


def test_wch_ch9102_product_id_is_not_mislabelled_ch340():
    m = {"build": {"hwids": [["0x1A86", "0x55D4"]]}}
    assert bm.usb_serial_from_manifest(m, serial_jtag=False) == ("ch9102", None)


def test_wch_unknown_product_id_writes_nothing():
    m = {"build": {"hwids": [["0x1A86", "0xFFFF"]]}}
    assert bm.usb_serial_from_manifest(m, serial_jtag=False) == (None, bm.NO_PATTERN_MATCH)


def test_silabs_and_ftdi_vids_map_to_schema_enum_values():
    silabs = {"build": {"hwids": [["0x10C4", "0xEA60"]]}}
    ftdi = {"build": {"hwids": [["0x0403", "0x6001"]]}}
    assert bm.usb_serial_from_manifest(silabs, serial_jtag=False) == ("usb-uart-bridge-unspecified", None)
    assert bm.usb_serial_from_manifest(ftdi, serial_jtag=False) == ("other", None)


def test_unknown_vendor_id_writes_nothing():
    assert bm.usb_serial_from_manifest(_manifest("unknown_vid_s3"), serial_jtag=True) == (
        None, bm.NO_PATTERN_MATCH)


def test_manifest_without_hwids_is_field_absent():
    assert bm.usb_serial_from_manifest(_manifest("no_hwids_esp32"), serial_jtag=False) == (
        None, bm.FIELD_ABSENT)


def test_espressif_vid_on_a_soc_without_serial_jtag_writes_nothing():
    # ESP32-S2 has native USB OTG but NO USB-Serial-JTAG: 0x303A must not become
    # native-usb-serial-jtag there (same rule as scripts/derive_usb_serial.py).
    assert bm.usb_serial_from_manifest(_manifest("native_usb_s3"), serial_jtag=False) == (
        None, bm.NO_PATTERN_MATCH)


def test_mixed_vendor_ids_are_ambiguous_and_write_nothing():
    m = {"build": {"hwids": [["0x2886", "0x0046"], ["0x303A", "0x1001"]]}}
    assert bm.usb_serial_from_manifest(m, serial_jtag=True) == (None, bm.NO_PATTERN_MATCH)


def test_download_mode_is_never_read_from_flash_mode_or_1200bps_touch():
    for name in ("native_usb_s3", "ch340_esp32", "unknown_vid_s3", "no_hwids_esp32"):
        assert bm.download_mode_from_manifest(_manifest(name)) == (None, bm.FIELD_ABSENT)


def test_soc_serial_jtag_is_read_from_the_soc_record(tmp_path):
    _write_soc(tmp_path, "esp32-s3", "otg-full-speed + serial-jtag")
    _write_soc(tmp_path, "esp32-s2", "otg-full-speed")
    assert bm.soc_has_serial_jtag("esp32-s3", tmp_path) is True
    assert bm.soc_has_serial_jtag("esp32-s2", tmp_path) is False
    assert bm.soc_has_serial_jtag("esp32-zz", tmp_path) is False


# ── end to end through backfill_board: vendor first, manifest fills the rest ──

def _setup(tmp_path, monkeypatch, board_id, pio_id, soc="esp32-s3", usb_type="otg-full-speed + serial-jtag"):
    _write_soc(tmp_path, soc, usb_type)
    path = _write_board(tmp_path, board_id, soc,
                        extra="getting_started: https://example.test/gs\n")
    if pio_id:
        monkeypatch.setitem(bm.PIO_BOARD_IDS, board_id, pio_id)
    return path


def test_manifest_0x303a_writes_native_usb_cited_to_the_pinned_manifest(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-native-s3", "fixture_native")
    murl = bm.manifest_url("fixture_native")
    fetch = _fetcher({_vendor_url("fixture-native-s3", "esp32-s3"): VENDOR_PAGE_NO_USB,
                      murl: _raw("native_usb_s3")})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["status"] == "backfilled"
    assert "usb_serial" in entry["written"]
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert {"field": "usb_serial", "url": murl, "verified": TODAY} in fm["sources"]
    # the vendor-grounded field still cites the vendor page, not the manifest
    assert "download_mode" not in fm


def test_manifest_0x1a86_writes_ch340_with_its_citation(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ch340", "fixture_ch340", soc="esp32", usb_type="none")
    murl = bm.manifest_url("fixture_ch340")
    fetch = _fetcher({_vendor_url("fixture-ch340", "esp32"): VENDOR_PAGE_NO_USB,
                      murl: _raw("ch340_esp32")})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert entry["status"] == "backfilled"
    assert fm["usb_serial"] == "ch340"
    assert {"field": "usb_serial", "url": murl, "verified": TODAY} in fm["sources"]


def test_manifest_unknown_vid_writes_nothing_and_says_why(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-tinyusb", "fixture_unknown")
    before = path.read_text()
    fetch = _fetcher({_vendor_url("fixture-tinyusb", "esp32-s3"): VENDOR_PAGE_NO_USB,
                      bm.manifest_url("fixture_unknown"): _raw("unknown_vid_s3")})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["status"] == "skipped"
    assert path.read_text() == before
    assert entry["field_reasons"]["usb_serial"] == {"vendor": bm.FIELD_ABSENT,
                                                    "manifest": bm.NO_PATTERN_MATCH}
    assert entry["field_reasons"]["download_mode"]["manifest"] == bm.FIELD_ABSENT


def test_board_with_no_mapping_is_skipped_no_manifest_without_fetching_it(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-unmapped", None)
    log: list = []
    fetch = _fetcher({_vendor_url("fixture-unmapped", "esp32-s3"): VENDOR_PAGE_NO_USB}, log)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["status"] == "skipped"
    assert entry["field_reasons"]["usb_serial"]["manifest"] == bm.NO_MANIFEST
    assert not any("raw.githubusercontent.com" in u for u in log)


def test_vendor_page_wins_and_the_manifest_is_not_fetched(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-vendor-wins", "fixture_native")
    log: list = []
    page = "<html><body><p>The board carries a CP2102N USB-to-UART bridge.</p></body></html>"
    fetch = _fetcher({_vendor_url("fixture-vendor-wins", "esp32-s3"): page,
                      bm.manifest_url("fixture_native"): _raw("native_usb_s3")}, log)
    bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "cp2102n"
    # download_mode is still missing, but the manifest never states it, so it is not fetched
    assert not any("raw.githubusercontent.com" in u for u in log)


def test_vendor_unreachable_still_lets_the_manifest_fill_usb_serial(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-vendor-404", "fixture_native")
    murl = bm.manifest_url("fixture_native")
    entry = bb.backfill_board(path, tmp_path, _fetcher({murl: _raw("native_usb_s3")}), TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert entry["status"] == "backfilled"
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert entry["field_reasons"]["download_mode"] == {"vendor": bm.DOC_UNREACHABLE,
                                                       "manifest": bm.FIELD_ABSENT}


def test_manifest_fetch_failure_is_doc_unreachable(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-pio-404", "fixture_missing")
    fetch = _fetcher({_vendor_url("fixture-pio-404", "esp32-s3"): VENDOR_PAGE_NO_USB})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["field_reasons"]["usb_serial"]["manifest"] == bm.DOC_UNREACHABLE


# ── per-field vendor reasons: field_absent vs no_pattern_match ────────────────

def test_vendor_reason_separates_a_topic_never_mentioned_from_one_no_pattern_matched(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-reasons", None)
    # mentions USB serial and the BOOT button, but in no form an extractor grounds
    page = ("<html><body><p>Plug the USB serial cable in.</p>"
            "<p>The boot button sits next to the antenna.</p></body></html>")
    fetch = _fetcher({_vendor_url("fixture-reasons", "esp32-s3"): page})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["field_reasons"]["usb_serial"]["vendor"] == bm.NO_PATTERN_MATCH
    assert entry["field_reasons"]["download_mode"]["vendor"] == bm.NO_PATTERN_MATCH

    path2 = _setup(tmp_path, monkeypatch, "fixture-reasons-2", None)
    fetch2 = _fetcher({_vendor_url("fixture-reasons-2", "esp32-s3"): VENDOR_PAGE_NO_USB})
    entry2 = bb.backfill_board(path2, tmp_path, fetch2, TODAY)
    assert entry2["field_reasons"]["usb_serial"]["vendor"] == bm.FIELD_ABSENT
    assert entry2["field_reasons"]["download_mode"]["vendor"] == bm.FIELD_ABSENT


def test_standalone_pr_body_names_the_manifest_citation(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-body", "fixture_native")
    murl = bm.manifest_url("fixture_native")
    fetch = _fetcher({_vendor_url("fixture-body", "esp32-s3"): VENDOR_PAGE_NO_USB,
                      murl: _raw("native_usb_s3")})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    body = bb.pr_body({"backfilled": [entry], "skipped": [], "needs_doc_url": [], "today": TODAY})
    assert f"`usb_serial` via {murl}" in body
    assert "PlatformIO" in body
