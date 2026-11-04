"""Tests for jr/board_corroboration.py — owner mandate G3 (2026-11-04): the PlatformIO manifest and
the Arduino-ESP32 boards.txt are corroboration only. They never write `usb_serial` or
`download_mode`; `usb_serial` is written only from board-specific (vendor page) evidence, and a
toolchain value that disagrees with it routes the field to review instead of writing it.

NO NETWORK: the pinned sources are the committed fixtures under jr/fixtures/, served by an injected
fake fetch keyed on the pinned raw.githubusercontent.com URLs.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import board_arduino as ba
import board_backfill as bb
import board_corroboration as bc
import board_cooldown
import board_manifest as bm

FIXTURES = Path(__file__).resolve().parent / "fixtures"
BOARDS_TXT = (FIXTURES / "board_arduino" / "boards.txt").read_text()
TODAY = "2026-11-04"
VENDOR_PAGE_NO_USB = "<html><body><h1>Fixture board</h1><p>Getting started.</p></body></html>"
VENDOR_PAGE_CH340 = "<html><body><p>The board carries a CH340 USB-to-UART bridge.</p></body></html>"
VENDOR_PAGE_CP2102N = "<html><body><p>The board carries a CP2102N USB-to-UART bridge.</p></body></html>"
VENDOR_PAGE_MANUAL_BOOT = ("<html><body><p>Holding down Boot and then pressing Reset initiates "
                           "Firmware Download mode for downloading firmware through the serial "
                           "port.</p></body></html>")


def _pio_raw(name: str) -> str:
    return (FIXTURES / "board_manifest" / f"{name}.json").read_text()


def _write_soc(root: Path, soc: str, usb_type: str, native: bool) -> None:
    d = root / "socs" / soc
    d.mkdir(parents=True, exist_ok=True)
    (d / "chip.md").write_text(
        f"---\nid: {soc}\ntype: soc\nusb:\n  native: {str(native).lower()}\n"
        f"  type: {usb_type}\n---\n\n# {soc}\n")


def _setup(tmp_path, monkeypatch, board_id, soc="esp32", pio_id=None, ard_key=None,
           extra="getting_started: https://example.test/gs\n") -> Path:
    if soc == "esp32":
        _write_soc(tmp_path, soc, "none", native=False)
    else:
        _write_soc(tmp_path, soc, "otg-full-speed + serial-jtag", native=True)
    d = tmp_path / "boards" / "espressif" / board_id
    d.mkdir(parents=True, exist_ok=True)
    path = d / "board.md"
    path.write_text(
        f"---\nid: {board_id}\ntype: board\nbrand: espressif\nname: {board_id}\nsoc: {soc}\n{extra}"
        "sources:\n- field: '*'\n  url: https://example.test/x\n  verified: '2026-01-01'\n---\n\n# b\n")
    if pio_id:
        monkeypatch.setitem(bm.PIO_BOARD_IDS, board_id, pio_id)
    if ard_key:
        monkeypatch.setitem(ba.ARDUINO_BOARD_KEYS, board_id, ard_key)
    return path


def _fetcher(pages: dict, log: list | None = None):
    def fetch(url):
        if log is not None:
            log.append(url)
        if url in pages:
            return {"ok": True, "status": 200, "text": pages[url]}
        return {"ok": False, "status": 404, "error": "HTTP 404"}
    return fetch


def _vendor(board_id: str, soc: str = "esp32") -> str:
    return bb.board_user_guide_url(board_id, soc)


def _cited(fm: dict, url: str) -> bool:
    return any(s.get("url") == url for s in fm.get("sources") or [])


# ── the agreement rule ────────────────────────────────────────────────────────

def test_agreement_is_equality_plus_the_two_unnamed_bridge_forms():
    assert bc.agrees("ch340", "ch340")
    assert not bc.agrees("cp2102n", "ch340")
    # 0x10C4 covers CP2102/CP2102N/CP2104, so the toolchain reports the bridge unnamed
    assert bc.agrees("cp2102n", "usb-uart-bridge-unspecified")
    assert bc.agrees("cp2102", "usb-uart-bridge-unspecified")
    assert not bc.agrees("ch340", "usb-uart-bridge-unspecified")
    # the vendor page says "a USB-to-UART bridge chip": any named bridge agrees, native USB does not
    assert bc.agrees("usb-uart-bridge-unspecified", "ch9102")
    assert not bc.agrees("usb-uart-bridge-unspecified", "native-usb-serial-jtag")
    assert not bc.agrees("native-usb-serial-jtag", "usb-uart-bridge-unspecified")


# ── toolchain alone never writes ──────────────────────────────────────────────

def test_platformio_only_usb_serial_is_not_written_and_is_corroboration_only(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-pio-only", pio_id="fixture_ch340")
    before = path.read_text()
    murl = bm.manifest_url("fixture_ch340")
    fetch = _fetcher({_vendor("fixture-pio-only"): VENDOR_PAGE_NO_USB, murl: _pio_raw("ch340_esp32")})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert path.read_text() == before
    assert entry["status"] == "skipped" and not entry["modified"]
    assert entry["field_reasons"]["usb_serial"] == {"vendor": bm.FIELD_ABSENT,
                                                    "manifest": bc.CORROBORATION_ONLY,
                                                    "boards_txt": ba.NO_BOARD_KEY}
    assert entry["corroboration"]["usb_serial"] == {
        "verdict": bc.CORROBORATION_ONLY, "board_value": None,
        "checks": [{"source": "manifest", "url": murl, "value": "ch340",
                    "verdict": bc.CORROBORATION_ONLY}]}


def test_arduino_only_usb_serial_is_not_written(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-ard-only", ard_key="fixture_ch340")
    before = path.read_text()
    fetch = _fetcher({_vendor("fixture-ard-only"): VENDOR_PAGE_NO_USB, ba.BOARDS_TXT_URL: BOARDS_TXT})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert path.read_text() == before
    assert entry["status"] == "skipped"
    assert entry["field_reasons"]["usb_serial"]["boards_txt"] == bc.CORROBORATION_ONLY
    check = entry["corroboration"]["usb_serial"]["checks"][0]
    assert check == {"source": "boards_txt", "url": ba.BOARDS_TXT_URL, "value": "ch340",
                     "verdict": bc.CORROBORATION_ONLY}


def test_both_toolchains_agreeing_still_write_nothing(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-both", pio_id="fixture_ch340",
                  ard_key="fixture_ch340")
    before = path.read_text()
    fetch = _fetcher({_vendor("fixture-both"): VENDOR_PAGE_NO_USB,
                      bm.manifest_url("fixture_ch340"): _pio_raw("ch340_esp32"),
                      ba.BOARDS_TXT_URL: BOARDS_TXT})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert path.read_text() == before
    assert entry["corroboration"]["usb_serial"]["verdict"] == bc.CORROBORATION_ONLY
    assert [c["source"] for c in entry["corroboration"]["usb_serial"]["checks"]] == ["manifest",
                                                                                     "boards_txt"]


def test_vendor_unreachable_leaves_toolchain_values_unwritten(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-vendor-404", pio_id="fixture_ch340")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path,
                              _fetcher({bm.manifest_url("fixture_ch340"): _pio_raw("ch340_esp32")}),
                              TODAY)
    assert path.read_text() == before
    assert entry["status"] == "skipped" and entry["reason"] == "doc-unreachable"
    assert entry["field_reasons"]["usb_serial"]["manifest"] == bc.CORROBORATION_ONLY


# ── vendor evidence decides; the toolchain corroborates or routes to review ───

def test_vendor_evidence_with_agreeing_platformio_is_written_corroborated(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-agree", pio_id="fixture_ch340")
    vurl, murl = _vendor("fixture-agree"), bm.manifest_url("fixture_ch340")
    log: list = []
    fetch = _fetcher({vurl: VENDOR_PAGE_CH340, murl: _pio_raw("ch340_esp32")}, log)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert murl in log                        # consulted for corroboration even though vendor grounded
    assert entry["status"] == "backfilled" and "usb_serial" in entry["written"]
    assert fm["usb_serial"] == "ch340"
    assert {"field": "usb_serial", "url": vurl, "verified": TODAY} in fm["sources"]
    assert not _cited(fm, murl)               # the toolchain is never the written citation
    assert entry["citations"]["usb_serial"] == vurl
    assert entry["corroboration"]["usb_serial"] == {
        "verdict": bc.CORROBORATED, "board_value": "ch340",
        "checks": [{"source": "manifest", "url": murl, "value": "ch340",
                    "verdict": bc.CORROBORATES}]}
    assert not entry.get("needs_review")


def test_vendor_evidence_without_any_toolchain_value_is_written_uncorroborated(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-alone")
    entry = bb.backfill_board(path, tmp_path,
                              _fetcher({_vendor("fixture-alone"): VENDOR_PAGE_CH340}), TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "ch340"
    assert entry["corroboration"]["usb_serial"] == {"verdict": bc.UNCORROBORATED,
                                                    "board_value": "ch340", "checks": []}


def test_vendor_cp2102n_and_a_silabs_toolchain_id_corroborate(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-silabs", pio_id="fixture_silabs")
    murl = bm.manifest_url("fixture_silabs")
    silabs = '{"build": {"hwids": [["0x10C4", "0xEA60"]]}}'
    fetch = _fetcher({_vendor("fixture-silabs"): VENDOR_PAGE_CP2102N, murl: silabs})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "cp2102n"
    assert entry["corroboration"]["usb_serial"]["verdict"] == bc.CORROBORATED


def test_vendor_evidence_with_conflicting_arduino_is_not_written_and_needs_review(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-conflict", ard_key="fixture_ch340")
    before = path.read_text()
    fetch = _fetcher({_vendor("fixture-conflict"): VENDOR_PAGE_CP2102N, ba.BOARDS_TXT_URL: BOARDS_TXT})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert path.read_text() == before
    assert entry["status"] == "skipped" and entry["reason"] == "needs-review"
    assert entry["needs_review"] == ["usb_serial"]
    assert entry["corroboration"]["usb_serial"] == {
        "verdict": bc.NEEDS_REVIEW, "board_value": "cp2102n",
        "checks": [{"source": "boards_txt", "url": ba.BOARDS_TXT_URL, "value": "ch340",
                    "verdict": bc.CONFLICTS}]}
    assert entry["field_reasons"]["usb_serial"] == {"vendor": bc.NEEDS_REVIEW,
                                                    "manifest": bm.NO_MANIFEST,
                                                    "boards_txt": bc.CONFLICTS}


def test_a_conflict_withholds_only_usb_serial_and_other_vendor_fields_still_land(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-conflict-gs", ard_key="fixture_ch340", extra="")
    vurl = _vendor("fixture-conflict-gs")
    fetch = _fetcher({vurl: VENDOR_PAGE_CP2102N, ba.BOARDS_TXT_URL: BOARDS_TXT})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert entry["status"] == "backfilled" and entry["written"] == ["getting_started"]
    assert entry["needs_review"] == ["usb_serial"]
    assert "usb_serial" in entry["omitted"] and "usb_serial" not in fm
    assert "usb_serial" not in entry["citations"]
    assert fm["getting_started"] == vurl


def test_one_agreeing_and_one_conflicting_toolchain_still_needs_review(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-split", pio_id="fixture_ch340",
                  ard_key="fixture_split_silabs")
    silabs_txt = BOARDS_TXT + "\nfixture_split_silabs.vid.0=0x10C4\nfixture_split_silabs.pid.0=0xEA60\n"
    fetch = _fetcher({_vendor("fixture-split"): VENDOR_PAGE_CH340,
                      bm.manifest_url("fixture_ch340"): _pio_raw("ch340_esp32"),
                      ba.BOARDS_TXT_URL: silabs_txt})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert "usb_serial" not in fm
    verdicts = {c["source"]: c["verdict"] for c in entry["corroboration"]["usb_serial"]["checks"]}
    assert verdicts == {"manifest": bc.CORROBORATES, "boards_txt": bc.CONFLICTS}
    assert entry["corroboration"]["usb_serial"]["verdict"] == bc.NEEDS_REVIEW


# ── download_mode is never inferred from the chip ─────────────────────────────

def test_download_mode_is_never_set_from_a_native_usb_chip_alone(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-native", soc="esp32-s3",
                  pio_id="fixture_native", ard_key="fixture_native_s3")
    before = path.read_text()
    fetch = _fetcher({_vendor("fixture-native", "esp32-s3"): VENDOR_PAGE_NO_USB,
                      bm.manifest_url("fixture_native"): _pio_raw("native_usb_s3"),
                      ba.BOARDS_TXT_URL: BOARDS_TXT})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    assert path.read_text() == before
    assert "download_mode" not in entry.get("written", [])
    assert "download_mode" not in entry["corroboration"]
    assert entry["field_reasons"]["download_mode"]["manifest"] == bm.FIELD_ABSENT


def test_manual_boot_reset_from_the_board_page_is_kept_on_a_native_usb_chip(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-manual", soc="esp32-s3", pio_id="fixture_native")
    vurl = _vendor("fixture-manual", "esp32-s3")
    fetch = _fetcher({vurl: VENDOR_PAGE_MANUAL_BOOT,
                      bm.manifest_url("fixture_native"): _pio_raw("native_usb_s3")})
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)
    fm, _ = bb.parse_frontmatter(path)
    assert fm["download_mode"]["mode"] == "manual"
    assert "Holding down Boot" in fm["download_mode"]["steps"]
    assert {"field": "download_mode", "url": vurl, "verified": TODAY} in fm["sources"]
    assert "usb_serial" not in fm            # the native-USB manifest alone writes nothing
    assert entry["corroboration"]["usb_serial"]["verdict"] == bc.CORROBORATION_ONLY


# ── existing values are untouched ─────────────────────────────────────────────

def test_existing_usb_serial_and_download_mode_are_untouched_and_not_cross_checked(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-filled", pio_id="fixture_ch340",
                  ard_key="fixture_ch340",
                  extra=("getting_started: https://example.test/gs\nusb_serial: cp2102n\n"
                         "download_mode:\n  mode: manual\n  steps: Hold BOOT, press RESET\n"
                         "images:\n  photo: https://example.test/p.png\n"))
    before = path.read_text()
    log: list = []
    entry = bb.backfill_board(path, tmp_path, _fetcher({}, log), TODAY)
    assert path.read_text() == before
    assert entry["status"] == "complete" and log == []


# ── the tick stage routes a conflict to a human ───────────────────────────────

class _Budget:
    def wrap(self, fn, _kind):
        return fn

    def remaining_calls(self):
        return 100

    def remaining_seconds(self):
        return 1000.0


class _Ctx:
    def __init__(self, root: Path):
        self.root = root
        self.now = datetime(2026, 11, 4, 12, tzinfo=timezone.utc)
        self.budget = _Budget()


def test_stage_flags_needs_human_cools_the_board_and_cites_the_conflict(tmp_path, monkeypatch):
    import stage_backfill
    data = tmp_path / "data"
    _setup(data, monkeypatch, "fixture-stage", ard_key="fixture_ch340")
    fetch = _fetcher({_vendor("fixture-stage"): VENDOR_PAGE_CP2102N, ba.BOARDS_TXT_URL: BOARDS_TXT})
    res = stage_backfill.run(_Ctx(tmp_path), budget=4, fetch=fetch)
    assert res.needs_human
    assert board_cooldown.RELPATH in res.paths
    assert "usb_serial needs_review" in res.summary
    assert f"boards_txt ch340 conflicts {ba.BOARDS_TXT_URL}" in res.summary


def test_stage_reports_corroboration_only_without_flagging_a_human(tmp_path, monkeypatch):
    import stage_backfill
    data = tmp_path / "data"
    _setup(data, monkeypatch, "fixture-stage-pio", pio_id="fixture_ch340")
    murl = bm.manifest_url("fixture_ch340")
    fetch = _fetcher({_vendor("fixture-stage-pio"): VENDOR_PAGE_NO_USB, murl: _pio_raw("ch340_esp32")})
    res = stage_backfill.run(_Ctx(tmp_path), budget=4, fetch=fetch)
    assert not res.needs_human
    assert f"manifest ch340 corroboration_only {murl}" in res.summary
    assert not any(p.endswith("board.md") for p in res.paths)


# ── the standalone PR body ────────────────────────────────────────────────────

def test_pr_body_lists_corroboration_and_never_cites_a_toolchain_as_the_written_source(tmp_path, monkeypatch):
    path = _setup(tmp_path, monkeypatch, "fixture-body", pio_id="fixture_ch340")
    vurl, murl = _vendor("fixture-body"), bm.manifest_url("fixture_ch340")
    entry = bb.backfill_board(path, tmp_path,
                              _fetcher({vurl: VENDOR_PAGE_CH340, murl: _pio_raw("ch340_esp32")}),
                              TODAY)
    body = bb.pr_body({"backfilled": [entry], "skipped": [], "needs_doc_url": [], "today": TODAY})
    assert f"`usb_serial` via {murl}" not in body
    assert f"manifest ch340 corroborates {murl}" in body
    assert "corroboration only" in body


def test_standalone_lane_names_a_conflict_even_when_nothing_was_backfilled(tmp_path, monkeypatch, capsys):
    path = _setup(tmp_path, monkeypatch, "fixture-main", ard_key="fixture_ch340")
    fetch = _fetcher({_vendor("fixture-main"): VENDOR_PAGE_CP2102N, ba.BOARDS_TXT_URL: BOARDS_TXT})
    out = bb.main(data_root=tmp_path, fetch=fetch, today=TODAY)
    assert out["pr"] is None
    printed = capsys.readouterr().out
    assert "1 needing review" in printed
    assert f"fixture-main: usb_serial needs_review (board cp2102n; boards_txt ch340 conflicts {ba.BOARDS_TXT_URL})" in printed
    assert path.read_text().count("usb_serial") == 0
