"""Tests for jr/board_arduino.py — G3b: the Arduino-ESP32 core `boards.txt` at a pinned release
commit as a THIRD, cited source for `usb_serial`, consulted only when the vendor page and the
PlatformIO manifest both left it missing. download_mode and pinout are out of scope.

NO NETWORK: boards.txt is a committed fixture under jr/fixtures/board_arduino/, served by an
injected fake fetch keyed on the pinned raw.githubusercontent.com URL.
"""
from __future__ import annotations

import re
from pathlib import Path

import board_arduino as ba
import board_backfill as bb
import board_manifest as bm

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BOARDS_TXT = (FIXTURES / "board_arduino" / "boards.txt").read_text()
TODAY = "2026-11-03"
VENDOR_PAGE_NO_USB = "<html><body><h1>Fixture board</h1><p>Getting started.</p></body></html>"


def _pio_raw(name: str) -> str:
    return (FIXTURES / "board_manifest" / f"{name}.json").read_text()


def _write_soc(root: Path, soc: str, usb_type: str) -> None:
    d = root / "socs" / soc
    d.mkdir(parents=True, exist_ok=True)
    (d / "chip.md").write_text(
        f"---\nid: {soc}\ntype: soc\nusb:\n  native: true\n  type: {usb_type}\n---\n\n# {soc}\n")


def _setup(tmp_path, monkeypatch, board_id, key, soc="esp32-s3",
           usb_type="otg-full-speed + serial-jtag", pio_id=None) -> Path:
    _write_soc(tmp_path, soc, usb_type)
    d = tmp_path / "boards" / "espressif" / board_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / "board.md"
    path.write_text(
        f"---\nid: {board_id}\ntype: board\nbrand: espressif\nname: {board_id}\nsoc: {soc}\n"
        "getting_started: https://example.test/gs\n"
        "sources:\n- field: '*'\n  url: https://example.test/x\n  verified: '2026-01-01'\n---\n\n# b\n")
    if key:
        monkeypatch.setitem(ba.ARDUINO_BOARD_KEYS, board_id, key)
    if pio_id:
        monkeypatch.setitem(bm.PIO_BOARD_IDS, board_id, pio_id)
    return path


def _fetcher(pages: dict, log: list | None = None):
    def fetch(url):
        if log is not None:
            log.append(url)
        if url in pages:
            return {"ok": True, "status": 200, "text": pages[url]}
        return {"ok": False, "status": 404, "error": "HTTP 404"}
    return fetch


def _vendor(board_id: str, soc: str = "esp32-s3") -> str:
    return bb.board_user_guide_url(board_id, soc)


# ── the pinned source and the curated table ───────────────────────────────────

def test_boards_txt_url_is_pinned_to_an_immutable_release_commit():
    assert re.fullmatch(r"[0-9a-f]{40}", ba.ARDUINO_PINNED_REF)
    assert ba.BOARDS_TXT_URL == ("https://raw.githubusercontent.com/espressif/arduino-esp32/"
                                 f"{ba.ARDUINO_PINNED_REF}/boards.txt")


def test_curated_table_is_plain_ids_and_never_fuzzy_guessed():
    for board_id, key in ba.ARDUINO_BOARD_KEYS.items():
        assert re.fullmatch(r"[a-z0-9-]+", board_id), board_id
        assert re.fullmatch(r"[A-Za-z0-9_.-]+", key), key
    # a board id that LOOKS like a boards.txt key is still not mapped
    assert ba.board_key("lolin-s3-pro") is None
    assert ba.board_key("unmapped-board") is None


def test_two_usb_port_and_product_family_boards_are_left_out():
    for board_id in ("lolin-s3", "esp32-s3-devkitc-1",            # two USB ports
                     "m5atom-lite", "m5stack-core", "m5stack-core-aws", "m5atoms3-lite",
                     "m5stack-cores3-se", "m5cardputer", "xiao-esp32s3-sense",
                     "lilygo-t-beam", "esp-wrover-kit", "esp32-pico-kit"):  # one key, many products
        assert ba.board_key(board_id) is None, board_id


# ── reading a key's own vid/pid lines ─────────────────────────────────────────

def test_hwids_are_read_only_from_the_keys_own_lines():
    assert ba.hwids_for_key(BOARDS_TXT, "fixture_native_s3") == [("0x303a", "0x1001")]
    # commented-out vid/pid lines are not data
    assert ba.hwids_for_key(BOARDS_TXT, "fixture_ch340") == [("0x1A86", "0x7523")]
    assert ba.hwids_for_key(BOARDS_TXT, "fixture_unknown") == [("0x239A", "0x811B"),
                                                               ("0x239A", "0x011B")]


def test_key_without_vid_lines_has_no_hwids_and_an_absent_key_is_none():
    assert ba.hwids_for_key(BOARDS_TXT, "fixture_no_vid") == []
    assert ba.hwids_for_key(BOARDS_TXT, "fixture_not_there") is None


def test_usb_serial_reuses_the_g3a_vendor_id_table():
    assert ba.usb_serial_from_boards_txt(BOARDS_TXT, "fixture_native_s3", serial_jtag=True) == (
        "native-usb-serial-jtag", None)
    assert ba.usb_serial_from_boards_txt(BOARDS_TXT, "fixture_ch340", serial_jtag=False) == (
        "ch340", None)
    assert ba.usb_serial_from_boards_txt(BOARDS_TXT, "fixture_native_s3_plus", serial_jtag=True) == (
        "ch9102", None)


def test_unknown_vid_mixed_vids_and_wch_without_pid_write_nothing():
    for key in ("fixture_unknown", "fixture_mixed", "fixture_wch_no_pid"):
        assert ba.usb_serial_from_boards_txt(BOARDS_TXT, key, serial_jtag=True) == (
            None, bm.NO_PATTERN_MATCH), key


def test_espressif_vid_on_a_soc_without_serial_jtag_writes_nothing():
    assert ba.usb_serial_from_boards_txt(BOARDS_TXT, "fixture_native_s3", serial_jtag=False) == (
        None, bm.NO_PATTERN_MATCH)


def test_key_without_vid_is_field_absent_and_missing_key_is_no_board_key():
    assert ba.usb_serial_from_boards_txt(BOARDS_TXT, "fixture_no_vid", serial_jtag=True) == (
        None, bm.FIELD_ABSENT)
    assert ba.usb_serial_from_boards_txt(BOARDS_TXT, "fixture_not_there", serial_jtag=True) == (
        None, ba.NO_BOARD_KEY)


# ── end to end through backfill_board: vendor, then PlatformIO, then boards.txt ──

def test_0x303a_key_writes_native_usb_cited_to_the_pinned_boards_txt(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-native", "fixture_native_s3")
    log: list = []
    fetch = _fetcher({_vendor("fixture-ard-native"): VENDOR_PAGE_NO_USB,
                      ba.BOARDS_TXT_URL: BOARDS_TXT}, log)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["status"] == "backfilled"
    assert entry["written"] == ["usb_serial"]
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert {"field": "usb_serial", "url": ba.BOARDS_TXT_URL, "verified": TODAY} in fm["sources"]
    assert entry["citations"]["usb_serial"] == ba.BOARDS_TXT_URL
    assert "download_mode" not in fm
    # boards.txt never reports on download_mode: it is out of this source's scope
    assert "boards_txt" not in entry["field_reasons"]["download_mode"]


def test_0x1a86_key_writes_the_wch_chip_with_its_citation(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-ch340", "fixture_ch340",
                  soc="esp32", usb_type="none")
    fetch = _fetcher({_vendor("fixture-ard-ch340", "esp32"): VENDOR_PAGE_NO_USB,
                      ba.BOARDS_TXT_URL: BOARDS_TXT})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert entry["status"] == "backfilled"
    assert fm["usb_serial"] == "ch340"
    assert {"field": "usb_serial", "url": ba.BOARDS_TXT_URL, "verified": TODAY} in fm["sources"]


def test_boards_txt_fills_what_the_manifest_could_not(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-after-pio", "fixture_native_s3",
                  pio_id="fixture_unknown")
    log: list = []
    vurl, murl = _vendor("fixture-ard-after-pio"), bm.manifest_url("fixture_unknown")
    fetch = _fetcher({vurl: VENDOR_PAGE_NO_USB, murl: _pio_raw("unknown_vid_s3"),
                      ba.BOARDS_TXT_URL: BOARDS_TXT}, log)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert log == [vurl, murl, ba.BOARDS_TXT_URL]   # vendor, then PlatformIO, then boards.txt
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert {"field": "usb_serial", "url": ba.BOARDS_TXT_URL, "verified": TODAY} in fm["sources"]


def test_unknown_vid_writes_nothing_and_says_why_per_source(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-unknown", "fixture_unknown")
    before = path.read_text()
    fetch = _fetcher({_vendor("fixture-ard-unknown"): VENDOR_PAGE_NO_USB,
                      ba.BOARDS_TXT_URL: BOARDS_TXT})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["status"] == "skipped"
    assert path.read_text() == before
    assert entry["field_reasons"]["usb_serial"] == {"vendor": bm.FIELD_ABSENT,
                                                    "manifest": bm.NO_MANIFEST,
                                                    "boards_txt": bm.NO_PATTERN_MATCH}


def test_board_filled_by_the_manifest_is_not_overwritten_nor_boards_txt_fetched(tmp_path, monkeypatch):
    # boards.txt would say ch340; the PlatformIO manifest says native USB and wins
    path = _setup(tmp_path, monkeypatch, "fixture-ard-pio-wins", "fixture_ch340",
                  pio_id="fixture_native")
    log: list = []
    murl = bm.manifest_url("fixture_native")
    fetch = _fetcher({_vendor("fixture-ard-pio-wins"): VENDOR_PAGE_NO_USB,
                      murl: _pio_raw("native_usb_s3"), ba.BOARDS_TXT_URL: BOARDS_TXT}, log)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert {"field": "usb_serial", "url": murl, "verified": TODAY} in fm["sources"]
    assert not any(s["url"] == ba.BOARDS_TXT_URL for s in fm["sources"])
    assert ba.BOARDS_TXT_URL not in log
    assert entry["citations"]["usb_serial"] == murl


def test_record_already_carrying_usb_serial_is_never_touched(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-filled", "fixture_ch340")
    text = path.read_text().replace("getting_started:", "usb_serial: cp2102n\ngetting_started:")
    path.write_text(text)
    log: list = []
    fetch = _fetcher({_vendor("fixture-ard-filled"): VENDOR_PAGE_NO_USB,
                      ba.BOARDS_TXT_URL: BOARDS_TXT}, log)
    bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "cp2102n"
    assert ba.BOARDS_TXT_URL not in log


def test_unmapped_board_is_skipped_with_a_per_field_reason_without_fetching(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-unmapped", None)
    log: list = []
    fetch = _fetcher({_vendor("fixture-ard-unmapped"): VENDOR_PAGE_NO_USB,
                      ba.BOARDS_TXT_URL: BOARDS_TXT}, log)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["status"] == "skipped"
    assert entry["field_reasons"]["usb_serial"]["boards_txt"] == ba.NO_BOARD_KEY
    assert ba.BOARDS_TXT_URL not in log


def test_boards_txt_fetch_failure_is_doc_unreachable(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-404", "fixture_native_s3")
    fetch = _fetcher({_vendor("fixture-ard-404"): VENDOR_PAGE_NO_USB})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["field_reasons"]["usb_serial"]["boards_txt"] == bm.DOC_UNREACHABLE


def test_mapped_key_missing_from_the_file_is_no_board_key(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-drift", "fixture_not_there")
    fetch = _fetcher({_vendor("fixture-ard-drift"): VENDOR_PAGE_NO_USB,
                      ba.BOARDS_TXT_URL: BOARDS_TXT})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert entry["field_reasons"]["usb_serial"]["boards_txt"] == ba.NO_BOARD_KEY


def test_standalone_pr_body_names_the_boards_txt_citation(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-body", "fixture_native_s3")
    fetch = _fetcher({_vendor("fixture-ard-body"): VENDOR_PAGE_NO_USB,
                      ba.BOARDS_TXT_URL: BOARDS_TXT})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    body = bb.pr_body({"backfilled": [entry], "skipped": [], "needs_doc_url": [], "today": TODAY})
    assert f"`usb_serial` via {ba.BOARDS_TXT_URL}" in body
    assert "Arduino-ESP32" in body


# ── the real fetch must hold the whole file, never a silently truncated one ───

class _FakeResponse:
    def __init__(self, payload: bytes):
        self._payload = payload
        self.status = 200
        self.headers = self

    def get_content_charset(self):
        return "utf-8"

    def read(self, n=-1):
        return self._payload if n is None or n < 0 else self._payload[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_default_fetch_holds_a_boards_txt_sized_file(monkeypatch):
    payload = b"x" * 3_000_000   # the pinned boards.txt is ~2.97 MB
    monkeypatch.setattr(bb.urllib.request, "urlopen", lambda req, timeout=None: _FakeResponse(payload))
    res = bb.default_fetch(ba.BOARDS_TXT_URL)
    assert res["ok"] is True
    assert len(res["text"]) == len(payload)


def test_default_fetch_refuses_a_body_over_the_cap_instead_of_truncating(monkeypatch):
    payload = b"x" * (bb.FETCH_MAX_BYTES + 1)
    monkeypatch.setattr(bb.urllib.request, "urlopen", lambda req, timeout=None: _FakeResponse(payload))
    res = bb.default_fetch(ba.BOARDS_TXT_URL)
    assert res["ok"] is False
    assert "too large" in res["error"]
