"""Tests for jr/board_backfill.py — Track A of SPEC-data-completion.md.

DETERMINISTIC, GROUNDED, cite-or-omit backfill of the finite board ground: fills
missing board fields (download_mode, usb_serial, getting_started) from each board's
OFFICIAL Espressif user-guide doc, quoting-and-citing — and OMITS anything it can't
ground. This is safety-critical (a wrong download-mode step can leave a user unable to
flash), so it NEVER guesses.

NO NETWORK here: every test injects a fake fetcher returning fixture HTML, and the
git/gh orchestration is driven by injected recorder fakes (same pattern as
test_drain_pr.py). No LLM, no API key anywhere.

Covered (per the spec's TDD list):
  (a) a doc with the manual download-mode sentence -> download_mode=manual with the
      EXACT quoted steps + a citation, and getting_started=the resolved URL.
  (b) a doc lacking that phrase -> download_mode OMITTED, board reported PARTIAL.
  (c) a doc naming CP2102N -> usb_serial=cp2102n, cited.
  (d) a fetch failure -> board SKIPPED (doc-unreachable) and NOT modified.
  (e) an already-cited field is NEVER overwritten.

Run: cd jr && python3 -m pytest test_board_backfill.py -q
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import board_backfill as bb

TODAY = "2026-09-01"
NOW = datetime(2026, 9, 1, 8, 46, 0, tzinfo=timezone.utc)

# ── fixture docs (coding-domain example Espressif boards) ─────────────────────
# Realistic Espressif user-guide phrasing wrapped in HTML so the tag-stripping is
# exercised too. Each names its own soc so URL construction needs no module lookup.

MANUAL_SENTENCE = ("Press and hold the Boot button, then press the Reset button, "
                   "then release Boot to enter Firmware Download mode")

DOC_WITH_MANUAL = f"""<html><body>
<h1>ESP32-S3-DevKit-Coder-1 User Guide</h1>
<p>This board carries a CP2102N USB-to-UART bridge and a native USB-Serial-JTAG port.</p>
<p>{MANUAL_SENTENCE}. After flashing, press Reset to run the application.</p>
<img src="../_images/esp32-s3-devkit-coder-1-pinout.png">
</body></html>"""

DOC_NO_DOWNLOAD_PHRASE = """<html><body>
<h1>ESP32-C3-DevKit-Coder-2 User Guide</h1>
<p>This board uses a CH340 USB-to-UART bridge.</p>
<p>Connect the board to your computer and start developing right away.</p>
</body></html>"""

DOC_WITH_CP2102N = """<html><body>
<h1>ESP32-S2-DevKit-Coder-3 User Guide</h1>
<p>The onboard CP2102N bridge exposes the chip's UART for flashing.</p>
</body></html>"""

DOC_WITH_CH340 = """<html><body>
<h1>ESP32-C6-DevKit-Coder-4 User Guide</h1>
<p>This revision ships with a CH340 USB-to-UART bridge.</p>
</body></html>"""


def _fetcher(pages):
    """Fake fetcher: 200 with the fixture HTML for a known URL, else a 404-style miss."""
    def fetch(url):
        if url in pages:
            return {"ok": True, "status": 200, "text": pages[url]}
        return {"ok": False, "status": 404, "error": "HTTP 404"}
    return fetch


def _write_board(root, board_id, soc, *, extra_fields="", brand="espressif"):
    """Create data/boards/<brand>/<id>/board.md under a temp data root."""
    d = root / "boards" / brand / board_id
    d.mkdir(parents=True, exist_ok=True)
    fm = (f"id: {board_id}\ntype: board\nbrand: {brand}\n"
          f"name: {board_id}\nsoc: {soc}\n{extra_fields}"
          "sources:\n- field: '*'\n  url: https://example.test/{bid}\n  verified: '2026-01-01'\n"
          ).replace("{bid}", board_id)
    (d / "board.md").write_text(f"---\n{fm}---\n\n# {board_id}\n")
    return d / "board.md"


def _url(board_id, soc):
    return bb.board_user_guide_url(board_id, soc)


# ── URL construction + extraction unit rules ──────────────────────────────────

def test_chip_seg_strips_hyphens():
    assert bb.chip_seg("esp32-c5") == "esp32c5"
    assert bb.chip_seg("esp32-s3") == "esp32s3"
    assert bb.chip_seg("esp32") == "esp32"


def test_url_construction():
    assert bb.board_user_guide_url("esp32-s3-devkitc-1", "esp32-s3") == (
        "https://docs.espressif.com/projects/esp-dev-kits/en/latest/"
        "esp32s3/esp32-s3-devkitc-1/user_guide.html"
    )


def test_extract_download_mode_manual_quotes_exact_sentence():
    dm = bb.extract_download_mode(bb._visible_text(DOC_WITH_MANUAL))
    assert dm == {"mode": "manual", "steps": MANUAL_SENTENCE}


def test_extract_download_mode_omitted_when_no_phrase():
    assert bb.extract_download_mode(bb._visible_text(DOC_NO_DOWNLOAD_PHRASE)) is None


def test_extract_usb_serial_prefers_cp2102n_over_cp2102():
    assert bb.extract_usb_serial(bb._visible_text(DOC_WITH_CP2102N)) == "cp2102n"


def test_extract_usb_serial_native_jtag():
    assert bb.extract_usb_serial("uses the native USB-Serial-JTAG peripheral") == "native-usb-serial-jtag"


def test_extract_usb_serial_omitted_when_unnamed():
    assert bb.extract_usb_serial("a generic USB-to-UART bridge") is None


# ── (a) manual sentence -> download_mode=manual + steps + citation; getting_started=url ──

def test_backfill_manual_download_mode_and_getting_started(tmp_path):
    soc = "esp32-s3"
    bid = "esp32-s3-devkit-coder-1"
    path = _write_board(tmp_path, bid, soc)
    url = _url(bid, soc)
    entry = bb.backfill_board(path, tmp_path, _fetcher({url: DOC_WITH_MANUAL}), TODAY)

    assert entry["status"] == "backfilled"
    assert entry["partial"] is False
    fm, _ = bb.parse_frontmatter(path)
    assert fm["download_mode"] == {"mode": "manual", "steps": MANUAL_SENTENCE}
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "cp2102n"  # the fixture also names the bridge
    # every written field carries its own {field,url,verified} citation
    cited = {s["field"]: s for s in fm["sources"]}
    for field in ("download_mode", "usb_serial", "getting_started"):
        assert cited[field]["url"] == url
        assert cited[field]["verified"] == TODAY


# ── (b) no phrase -> download_mode omitted, board reported partial ─────────────

def test_backfill_partial_when_download_mode_ungroundable(tmp_path):
    soc = "esp32-c3"
    bid = "esp32-c3-devkit-coder-2"
    path = _write_board(tmp_path, bid, soc)
    url = _url(bid, soc)
    entry = bb.backfill_board(path, tmp_path, _fetcher({url: DOC_NO_DOWNLOAD_PHRASE}), TODAY)

    assert entry["status"] == "backfilled"
    assert entry["partial"] is True
    assert "download_mode" in entry["omitted"]
    fm, _ = bb.parse_frontmatter(path)
    assert "download_mode" not in fm            # OMITTED, never guessed
    assert fm["getting_started"] == url         # doc resolved -> link is real
    assert fm["usb_serial"] == "ch340"


# ── (c) doc names CP2102N -> usb_serial=cp2102n cited ─────────────────────────

def test_backfill_usb_serial_cp2102n_cited(tmp_path):
    soc = "esp32-s2"
    bid = "esp32-s2-devkit-coder-3"
    path = _write_board(tmp_path, bid, soc)
    url = _url(bid, soc)
    bb.backfill_board(path, tmp_path, _fetcher({url: DOC_WITH_CP2102N}), TODAY)

    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "cp2102n"
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["usb_serial"]["url"] == url and cited["usb_serial"]["verified"] == TODAY


# ── (d) fetch failure -> board skipped, not modified ──────────────────────────

def test_fetch_failure_skips_and_does_not_modify(tmp_path):
    soc = "esp32-c6"
    bid = "esp32-c6-devkit-coder-4"
    path = _write_board(tmp_path, bid, soc)
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # empty -> every url 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before  # byte-for-byte untouched


# ── (e) existing cited field is never overwritten ─────────────────────────────

def test_existing_cited_field_not_overwritten(tmp_path):
    soc = "esp32-c6"
    bid = "esp32-c6-devkit-coder-5"
    # board already carries a cited usb_serial: cp2102 (different from the doc's ch340)
    extra = ("usb_serial: cp2102\n")
    path = _write_board(tmp_path, bid, soc, extra_fields=extra)
    url = _url(bid, soc)
    bb.backfill_board(path, tmp_path, _fetcher({url: DOC_WITH_CH340}), TODAY)

    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "cp2102"  # NOT overwritten with ch340
    # no second usb_serial citation was appended for the doc url
    usb_sources = [s for s in fm["sources"] if s["field"] == "usb_serial"]
    assert all(s["url"] != url for s in usb_sources)
    # but getting_started (which was missing) was still filled
    assert fm["getting_started"] == url


# ── run(): espressif-only worklist, non-espressif listed but never touched ─────

def test_run_only_touches_espressif_and_lists_others(tmp_path):
    p_esp = _write_board(tmp_path, "esp32-s3-devkit-coder-6", "esp32-s3")
    p_other = _write_board(tmp_path, "coder-board-x", "esp32-s3", brand="acme")
    before_other = p_other.read_text()
    url = _url("esp32-s3-devkit-coder-6", "esp32-s3")

    report = bb.run(data_root=tmp_path, fetch=_fetcher({url: DOC_WITH_MANUAL}), today=TODAY)

    ids = [e["board_id"] for e in report["backfilled"]]
    assert "esp32-s3-devkit-coder-6" in ids
    assert "coder-board-x" not in ids
    assert "acme/coder-board-x" in report["needs_doc_url"]
    assert p_other.read_text() == before_other  # non-espressif never modified


# ── orchestration: branch -> commit changed board.md only -> PR (injected fakes) ──

class FakeProc(SimpleNamespace):
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def _recorder(**ret):
    calls = []

    def fn(*args):
        calls.append(args)
        return FakeProc(**ret)

    fn.calls = calls
    return fn


def _fake_report():
    p1 = bb.REPO / "data/boards/espressif/esp32-s3-devkit-coder-1/board.md"
    p2 = bb.REPO / "data/boards/espressif/esp32-c3-devkit-coder-2/board.md"
    return {
        "backfilled": [
            {"board_id": "esp32-s3-devkit-coder-1", "brand": "espressif", "path": p1,
             "url": "https://docs.espressif.com/x/1", "written": ["download_mode", "getting_started"],
             "omitted": [], "partial": False, "status": "backfilled", "modified": True},
            {"board_id": "esp32-c3-devkit-coder-2", "brand": "espressif", "path": p2,
             "url": "https://docs.espressif.com/x/2", "written": ["getting_started"],
             "omitted": ["download_mode"], "partial": True, "status": "backfilled", "modified": True},
        ],
        "skipped": [
            {"board_id": "esp32-h2-devkit-coder-9", "brand": "espressif",
             "reason": "doc-unreachable", "url": "https://docs.espressif.com/x/9",
             "status": "skipped", "modified": False},
        ],
        "needs_doc_url": ["acme/coder-board-x"],
        "today": TODAY,
    }


def test_open_pr_branch_commit_only_changed_boards_and_body():
    git, gh = _recorder(), _recorder(stdout="https://github.com/x/y/pull/7\n")
    report = _fake_report()

    result = bb.open_backfill_pr(report, git=git, gh=gh, now=NOW)

    checkout = git.calls[0]
    assert checkout[:2] == ("checkout", "-B")
    assert checkout[2] == "jr-board-backfill-20260901-0846"

    add_call = next(c for c in git.calls if c[0] == "add")
    staged = set(add_call[1:])
    assert staged == {
        "data/boards/espressif/esp32-s3-devkit-coder-1/board.md",
        "data/boards/espressif/esp32-c3-devkit-coder-2/board.md",
    }

    pr_call = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    assert pr_call[pr_call.index("--base") + 1] == "main"
    body = pr_call[pr_call.index("--body") + 1]
    assert "esp32-s3-devkit-coder-1" in body and "download_mode" in body
    assert "esp32-c3-devkit-coder-2" in body and "partial" in body.lower()
    assert "doc-unreachable" in body  # skipped boards surfaced
    assert result["pr_ok"] is True


def test_no_git_call_references_main():
    git, gh = _recorder(), _recorder(stdout="https://github.com/x/y/pull/7\n")
    bb.open_backfill_pr(_fake_report(), git=git, gh=gh, now=NOW)
    for call in git.calls:
        assert "main" not in call, f"git call referenced main: {call}"


def test_main_no_backfilled_touches_no_git(capsys):
    git, gh = _recorder(), _recorder()
    empty = {"backfilled": [], "skipped": [], "needs_doc_url": [], "today": TODAY}

    result = bb.main(run=lambda **_: empty, git=git, gh=gh, now=NOW)

    assert git.calls == [] and gh.calls == []
    assert result["pr"] is None
    out = capsys.readouterr().out.lower()
    assert "no board" in out or "nothing" in out


def test_branch_name_format():
    assert bb.branch_name(NOW) == "jr-board-backfill-20260901-0846"


# ══════════════════════════════════════════════════════════════════════════════
# RECOVERY of previously-SKIPPED boards, on REAL-HTML fixtures (SPEC Phase 2).
#
# Two failure modes are recovered here, all OFFLINE against verbatim slices of the boards'
# real Espressif docs saved under jr/fixtures/board_backfill/ (fetched & verified 2026-09-10):
#   A. doc-unreachable — 4 boards the single template mis-URL'd (audio → esp-adf tree;
#      version-suffixed filenames). Multi-tree resolution now finds the working 200 doc.
#   B. nothing-groundable — ~12 boards whose 200 doc yielded None: the extractors are hardened
#      to the ACTUAL page phrasing ("...pressing EN...", "Integrated USB-UART Bridge Chip",
#      "firmware upload mode") while staying cite-or-omit + schema-enum-valid.
# Critically, a page that does NOT state a field still returns None (no false positive).
# ══════════════════════════════════════════════════════════════════════════════

FIX = Path(__file__).resolve().parent / "fixtures" / "board_backfill"


def _fixture(name: str) -> str:
    return (FIX / f"{name}.html").read_text()


# The URL each fixture was fetched from — the doc resolution MUST land on exactly this URL.
_B = bb.USER_GUIDE_BASE
FIXTURE_URLS = {
    "esp32-devkitc": f"{_B}/esp32/esp32-devkitc/user_guide.html",                     # -v4 stripped
    "esp32-s2-saola-1": f"{_B}/esp32s2/esp32-s2-saola-1/user_guide_v1.2.html",        # override
    "esp32-s3-devkitc-1": f"{_B}/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html",    # override
    "esp32-lyrat": ("https://docs.espressif.com/projects/esp-adf/en/latest/"
                    "multimedia-boards/dev-boards/get-started-esp32-lyrat.html"),     # esp-adf tree
    "esp32-c3-devkitc-02": f"{_B}/esp32c3/esp32-c3-devkitc-02/user_guide.html",       # default 200
    "esp-wrover-kit": f"{_B}/esp32/esp-wrover-kit/user_guide.html",                   # default 200
    "esp32-ethernet-kit": f"{_B}/esp32/esp32-ethernet-kit/user_guide.html",          # default 200
}


# ── A. doc-URL resolution for the 4 previously doc-unreachable boards ───────────

def test_lyrat_resolves_to_esp_adf_tree_first():
    # audio board — docs live under esp-adf, not esp-dev-kits; override is tried first.
    assert bb.doc_url_candidates("esp32-lyrat", "esp32")[0] == FIXTURE_URLS["esp32-lyrat"]


def test_saola_and_s3_devkitc_resolve_to_version_suffixed_guide():
    assert bb.doc_url_candidates("esp32-s2-saola-1", "esp32-s2")[0] == FIXTURE_URLS["esp32-s2-saola-1"]
    assert bb.doc_url_candidates("esp32-s3-devkitc-1", "esp32-s3")[0] == FIXTURE_URLS["esp32-s3-devkitc-1"]


def test_devkitc_v4_resolves_via_stripped_slug():
    # no override needed: -v4 strip lands on the working esp32-devkitc/user_guide.html.
    assert FIXTURE_URLS["esp32-devkitc"] in bb.doc_url_candidates("esp32-devkitc-v4", "esp32")


# ── extraction on the real-HTML fixtures ───────────────────────────────────────

@pytest.mark.parametrize("name,expected", [
    ("esp32-devkitc", "usb-uart-bridge-unspecified"),      # "Single USB-to-UART bridge chip..."
    ("esp32-s2-saola-1", "usb-uart-bridge-unspecified"),
    ("esp32-s3-devkitc-1", "usb-uart-bridge-unspecified"),
    ("esp32-c3-devkitc-02", "usb-uart-bridge-unspecified"),
    ("esp32-lyrat", "usb-uart-bridge-unspecified"),        # "Integrated USB-UART Bridge Chip"
    ("esp-wrover-kit", "other"),                            # FTDI FT2232HL
    ("esp32-ethernet-kit", "other"),                        # FTDI FT2232H
])
def test_usb_serial_extracts_correct_enum_from_real_pages(name, expected):
    import json
    enum = set(json.load(open(bb.REPO / "schema" / "board.schema.json"))
               ["properties"]["usb_serial"]["enum"])
    val = bb.extract_usb_serial(bb._visible_text(_fixture(name)))
    assert val == expected
    assert val in enum  # never emit a value outside the schema enum (would abort the tick)


@pytest.mark.parametrize("name,contains", [
    ("esp32-devkitc", "pressing EN initiates Firmware Download mode"),
    ("esp-wrover-kit", "pressing EN initiates Firmware Download mode"),
    ("esp32-ethernet-kit", "pressing EN initiates Firmware Download mode"),
    ("esp32-s2-saola-1", "pressing Reset initiates Firmware Download mode"),
    ("esp32-s3-devkitc-1", "pressing Reset initiates Firmware Download mode"),
    ("esp32-lyrat", "initiates the firmware upload mode"),   # esp-adf phrasing
])
def test_download_mode_manual_extracts_with_exact_cited_steps(name, contains):
    dm = bb.extract_download_mode(bb._visible_text(_fixture(name)))
    assert dm is not None and dm["mode"] == "manual"
    assert contains in dm["steps"]  # the exact sentence quoted from the doc


# ── m5stack-family manual download-mode (no "Boot" sequence) grounds the exact,
#    actionable instruction sentence — cite-or-omit, NEVER the LED-confirmation line ──
_M5_DOWNLOAD_MODE_STEPS = {
    "m5stack-papers3": ("Download Mode Connect the device to a computer via USB cable, long "
                        "press the power button on the M5PaperS3, when the back status light "
                        "flashes red, it indicates the device has entered download mode"),
    "m5stick-s3": ("Download Mode Connect the device with a USB cable and press and hold the "
                   "reset button on the side of the device"),
}


@pytest.mark.parametrize("name", ["m5stack-papers3", "m5stick-s3"])
def test_m5stack_download_mode_grounds_exact_actionable_sentence(name):
    # PaperS3 and StickS3 state a COMPLETE, self-contained, actionable instruction in one
    # sentence → grounded verbatim (cite-or-omit satisfied).
    dm = bb.extract_download_mode(bb._visible_text(_fixture(name)))
    assert dm == {"mode": "manual", "steps": _M5_DOWNLOAD_MODE_STEPS[name]}


def test_m5cardputer_download_mode_omitted_misleading_fragment():
    # FLASH-SAFETY cite-or-omit: m5cardputer's real procedure is two clauses — "...press and
    # hold the G0 button before powering on. After supplying power to the device, release the
    # button, and the device will enter download mode." The critical hold-G0 precondition
    # survives ONLY inside a flattened >_M5_STEPS_MAX spec-table blob (correctly skipped). The
    # only in-sentence-groundable tail is "...release the button, and the device will enter
    # download mode" — a HALF-instruction telling the user to release a button they were never
    # told to hold. A user following ONLY that quote cannot enter download mode, so grounding
    # it would be worse than omitting. It must OMIT (bare "release" is not an engage action).
    assert bb.extract_download_mode(bb._visible_text(_fixture("m5cardputer"))) is None


def test_release_only_sentence_never_grounds_download_mode():
    # Regression guard against re-introducing the cardputer fragment bug: a sentence whose
    # ONLY action verb is "release" is not a complete entry instruction (release presupposes a
    # prior hold) → must NOT ground.
    assert bb.extract_download_mode(
        "After powering on, release the button and the device will enter download mode.") is None


def test_m5stick_s3_download_mode_is_instruction_not_led_confirmation():
    # StickS3's page has TWO "download mode" sentences: the actionable instruction and a
    # SEPARATE "When the internal green LED flashes, the device has successfully entered
    # download mode." confirmation. We MUST cite the instruction, never the confirmation.
    dm = bb.extract_download_mode(bb._visible_text(_fixture("m5stick-s3")))
    assert "press and hold the reset button" in dm["steps"]
    assert "green LED" not in dm["steps"] and "successfully entered" not in dm["steps"]


# ── Seeed XIAO family: the wiki calls the identical ESP32 ROM-download state "bootloader
#    mode" (entered via the BOOT button). It is semantically the SAME as download mode, so a
#    sentence naming it AND carrying an imperative BOOT-button action grounds as manual —
#    cite-or-omit, the exact complete instruction sentence only. ──
_XIAO_DOWNLOAD_MODE_STEPS = {
    "xiao-esp32c3": ("If that does not work, hold the BOOT BUTTON , connect the board to your "
                     "PC while holding the BOOT button, and then release it to enter "
                     "bootloader mode"),
    "xiao-esp32c6": ("When you press and hold the BOOT key while powering up and then press the "
                     "Reset key once, you can also enter BootLoader mode"),
    "xiao-esp32s3": ("When you press and hold the BOOT key while powering up and then press the "
                     "Reset key once, you can also enter BootLoader mode"),
}


@pytest.mark.parametrize("name", ["xiao-esp32c3", "xiao-esp32c6", "xiao-esp32s3"])
def test_xiao_bootloader_mode_grounds_exact_actionable_sentence(name):
    # Each XIAO page states a COMPLETE, self-contained, actionable BOOT-button instruction in
    # one sentence naming "bootloader mode" → grounded verbatim as manual (cite-or-omit).
    dm = bb.extract_download_mode(bb._visible_text(_fixture(name)))
    assert dm == {"mode": "manual", "steps": _XIAO_DOWNLOAD_MODE_STEPS[name]}


@pytest.mark.parametrize("sentence", [
    # FLASH-SAFETY: descriptive / non-actionable "bootloader mode" sentences MUST NOT ground —
    # grounding a fragment on a flash-critical field can leave a user unable to flash.
    "There is also a small reset button and a bootloader mode button on the board.",
    ("you can try to put XIAO into BootLoader mode, which can solve most of the problems of "
     "unrecognized devices and failed uploads."),
    # UF2 flow is a SEPARATE mechanism (USB drive), not the esptool ROM-download entry:
    "Step 3 : Enter UF2 BootLoader Mode Connect the XIAO to your computer and run the boot_uf2.bat script.",
    ("Step 5 : Re-enter UF2 BootLoader Mode If you need to re-enter UF2 BootLoader mode to "
     "upload another UF2 file, quickly press the Reset button followed by the Boot button."),
    "The XIAO will appear on your computer as a USB drive, indicating it has successfully entered UF2 BootLoader mode.",
])
def test_descriptive_or_uf2_bootloader_sentence_never_grounds(sentence):
    assert bb.extract_download_mode(sentence) is None


def test_download_mode_no_regression_on_established_boards():
    # CRITICAL: adding the XIAO "bootloader mode" branch must not perturb any established
    # board's grounded value. These are the byte-exact expectations before the change.
    espressif = bb.extract_download_mode(bb._visible_text(_fixture("esp32-devkitc")))
    assert espressif == {"mode": "manual", "steps": (
        "Holding down Boot and then pressing EN initiates Firmware Download mode for "
        "downloading firmware through the serial port")}
    assert bb.extract_download_mode(
        bb._visible_text(_fixture("adafruit-feather-esp32-v2"))) == {"mode": "auto"}
    assert bb.extract_download_mode(bb._visible_text(_fixture("m5stack-papers3"))) == {
        "mode": "manual", "steps": _M5_DOWNLOAD_MODE_STEPS["m5stack-papers3"]}
    assert bb.extract_download_mode(bb._visible_text(_fixture("m5stick-s3"))) == {
        "mode": "manual", "steps": _M5_DOWNLOAD_MODE_STEPS["m5stick-s3"]}
    assert bb.extract_download_mode(bb._visible_text(_fixture("m5cardputer"))) is None
    assert bb.extract_download_mode(bb._visible_text(_fixture("m5stack-core2"))) is None


def test_images_extract_where_the_page_links_them():
    # newer devkit: isometric photo + pinout diagram, absolute URLs on espressif.com
    imgs = bb.extract_images(_fixture("esp32-s2-saola-1"), FIXTURE_URLS["esp32-s2-saola-1"])
    assert imgs["pinout"].endswith("esp32-s2_saola1-pinout.jpg")
    assert imgs["photo"].endswith("esp32-s2-saola-1-v1.2-isometric.png")
    assert imgs["pinout"].startswith("https://docs.espressif.com/")
    # older board with no pinout diagram: photo grounded (layout-front), pinout OMITTED
    wrover = bb.extract_images(_fixture("esp-wrover-kit"), FIXTURE_URLS["esp-wrover-kit"])
    assert wrover["photo"].endswith("esp-wrover-kit-v4.1-layout-front.png")
    assert "pinout" not in wrover  # cite-or-omit: the page links no pinout diagram
    # ethernet-kit: labelled board overview photo, no pinout diagram
    eth = bb.extract_images(_fixture("esp32-ethernet-kit"), FIXTURE_URLS["esp32-ethernet-kit"])
    assert eth["photo"].endswith("esp32-ethernet-kit-v1.2-overview.png")
    assert "pinout" not in eth


# ── CRITICAL cite-or-omit: a page that states NONE of the fields yields None ────

_DOC_STATES_NOTHING = """<html><body>
<h1>ACME-DevKit User Guide</h1>
<p>A compact development board. Most of the I/O pins are broken out to pin headers on both
sides for easy interfacing on a breadboard.</p>
<p>Connect the board to your computer and start developing right away.</p>
<img src="../_static/logo.svg">
</body></html>"""


def test_cite_or_omit_preserved_when_page_states_nothing():
    text = bb._visible_text(_DOC_STATES_NOTHING)
    assert bb.extract_usb_serial(text) is None       # no bridge chip / jtag stated
    assert bb.extract_download_mode(text) is None     # no boot/reset sequence stated
    assert bb.extract_images(_DOC_STATES_NOTHING, "https://x/y.html") is None


def test_bare_usb_uart_bridge_without_chip_is_not_grounded():
    # a passing "USB-to-UART bridge" mention (no "chip") must NOT be promoted to unspecified:
    # only an explicit "...bridge chip" is a citeable hardware claim. (flash-critical strictness)
    assert bb.extract_usb_serial("routed through a USB-to-UART bridge") is None


# ── end-to-end: a recovered board resolves + backfills off the fixture ──────────

# ══════════════════════════════════════════════════════════════════════════════
# SLICE 1 — vendor-doc RESOLVER REGISTRY (SPEC-board-backfill-vendors.md).
#
# Pure structural refactor: Espressif's doc-URL logic becomes the "espressif" entry in
# VENDOR_DOC_RESOLVERS; backfill_board() selects the resolver by the board's `brand`;
# run() iterates every brand dir that HAS a registered resolver (today only espressif).
# These tests pin the guarantee that Espressif behaviour is byte-identical and that an
# unregistered vendor (m5stack) is skipped "no-resolver" and never modified.
# ══════════════════════════════════════════════════════════════════════════════

def test_registry_has_espressif_resolver_matching_doc_url_candidates():
    # (a) the registry exists, is keyed by brand, and its espressif resolver returns the
    # SAME ordered candidate URLs the standalone doc_url_candidates() did — for real esp32
    # board ids across the resolver's three code paths (default template, -v<N> strip,
    # per-board override).
    assert "espressif" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["espressif"]
    for board_id, soc in [
        ("esp32-c5-devkitc-1", "esp32-c5"),      # default template
        ("esp32-devkitc-v4", "esp32"),           # -v4 stripped fallback slug
        ("esp32-lyrat", "esp32"),                # per-board override (esp-adf tree)
        ("esp32-s2-saola-1", "esp32-s2"),        # version-suffixed override
    ]:
        assert resolver(board_id, soc) == bb.doc_url_candidates(board_id, soc)


def test_unregistered_brand_skipped_no_resolver_and_file_unchanged(tmp_path):
    # (b) a brand with NO registered resolver (a fictional placeholder brand — every real vendor
    # now has a resolver after Slice 13, so an invented one is used to exercise the no-resolver
    # path) is skipped with reason "no-resolver" and left byte-for-byte unmodified — the guarantee
    # that a brand without a resolver is never touched.
    bid, soc = "noresolver-vendor-esp32-s3-touch", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="noresolver-vendor")
    before = path.read_text()

    entry = bb.backfill_board(path, tmp_path, _fetcher({_url(bid, soc): DOC_WITH_MANUAL}), TODAY)

    assert entry["status"] == "skipped"
    assert entry["reason"] == "no-resolver"
    assert entry["modified"] is False
    assert path.read_text() == before  # byte-for-byte untouched


def test_run_is_registry_driven_processing_only_resolvable_brands(tmp_path):
    # (c) run() processes exactly the brands with a registered resolver, NOT other vendors —
    # driven off VENDOR_DOC_RESOLVERS keys, not a hardcoded brand. A fictional placeholder brand
    # (every real vendor now has a resolver after Slice 13) has no resolver → only LISTED, never
    # processed.
    p_esp = _write_board(tmp_path, "esp32-c5-devkitc-1", "esp32-c5")
    p_m5 = _write_board(tmp_path, "m5stack-core2", "esp32", brand="m5stack")
    p_ws = _write_board(tmp_path, "noresolver-vendor-board", "esp32-s3", brand="noresolver-vendor")
    before_m5, before_ws = p_m5.read_text(), p_ws.read_text()
    url = _url("esp32-c5-devkitc-1", "esp32-c5")

    # fetcher serves only the espressif URL → m5stack-core2's docs.m5stack.com URL 404s, so it
    # is PROCESSED (registered) but skipped doc-unreachable — proving run() reaches m5stack now.
    report = bb.run(data_root=tmp_path, fetch=_fetcher({url: DOC_WITH_MANUAL}), today=TODAY)

    processed = {e["board_id"] for e in report["backfilled"]} | {e["board_id"] for e in report["skipped"]}
    assert "esp32-c5-devkitc-1" in processed
    assert "m5stack-core2" in processed              # m5stack is registered after Slice 2
    assert "noresolver-vendor-board" not in processed
    # a registered brand is NOT on the needs_doc_url list; only the unregistered one is
    assert "m5stack/m5stack-core2" not in report["needs_doc_url"]
    assert "noresolver-vendor/noresolver-vendor-board" in report["needs_doc_url"]
    assert p_m5.read_text() == before_m5             # skipped (404) → unmodified
    assert p_ws.read_text() == before_ws             # no resolver → unmodified


def test_lyrat_end_to_end_recovers_from_esp_adf_fixture(tmp_path):
    # Fetcher serves the fixture ONLY at the esp-adf override URL — if resolution picks any
    # other candidate it 404s and the board stays skipped, so this proves the URL fix too.
    bid, soc = "esp32-lyrat", "esp32"
    path = _write_board(tmp_path, bid, soc)
    url = FIXTURE_URLS["esp32-lyrat"]
    entry = bb.backfill_board(path, tmp_path, _fetcher({url: _fixture("esp32-lyrat")}), TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "usb-uart-bridge-unspecified"
    assert fm["download_mode"]["mode"] == "manual"
    assert "firmware upload mode" in fm["download_mode"]["steps"]
    assert fm["getting_started"] == url
    assert fm["images"]["photo"].endswith("esp32-lyrat-v4.3-layout-overview-with-wrover-e-module.jpg")
    cited = {s["field"]: s for s in fm["sources"]}
    for field in ("download_mode", "usb_serial", "getting_started", "images"):
        assert cited[field]["url"] == url and cited[field]["verified"] == TODAY


# ══════════════════════════════════════════════════════════════════════════════
# SLICE 2 — m5stack vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 2).
#
# Registers the "m5stack" resolver on docs.m5stack.com so board_backfill reaches the 13
# m5stack boards. The real doc-URL pattern was CONFIRMED by a live fetch during the build:
# every m5stack product page lives at `docs.m5stack.com/en/core/<ProductName>`, where the
# product-name path is board-specific (m5stack-core2 → core2, m5atom-lite → ATOM%20Lite),
# so the resolver carries a per-board map — a human-verified URL per board, never guessed.
#
# EMPIRICAL grounding (measured on the REAL fetched pages saved under fixtures/):
#   * getting_started — grounds for ALL 13 (the resolved 200 URL IS the field).
#   * usb_serial      — grounds where the page NAMES a bridge/JTAG: core2 states "CH9102"
#                       → ch9102; Cardputer states "USB Serial/JTAG" → native-usb-serial-jtag.
#                       StickS3 names neither → OMITTED (cite-or-omit).
#   * download_mode   — NOT groundable on m5stack yet: the pages use "long-press Reset to
#                       enter download mode" (no Boot-button sequence), so the Espressif-tuned
#                       manual heuristic (which requires a Boot button) correctly does NOT
#                       fire. Left OMITTED — a later slice can generalize it. NEVER forced.
#   * images          — grounded by HTML CONTEXT (Slice 1, SPEC-vendor-image-grounding.md),
#                       NOT by filename (m5stack CDN names are opaque). photo = the first
#                       carousel `<img alt="Preview">` hero (grounds on ALL fixtures). pinout =
#                       an <img> embedded under the explicit `<h2 id="pinmap">PinMap</h2>`
#                       section ONLY — grounds core2 (its PinMap embeds a GPIO diagram); the
#                       stick-s3 / cardputer / papers3 PinMaps are TABLES with no image →
#                       pinout OMITTED (high-confidence-or-omit; never guess a wiring diagram).
# ══════════════════════════════════════════════════════════════════════════════

# The three URLs confirmed 200 by a live fetch on 2026-09-10 (their HTML is the fixtures).
M5STACK_VERIFIED_URLS = {
    "m5stick-s3": "https://docs.m5stack.com/en/core/StickS3",
    "m5cardputer": "https://docs.m5stack.com/en/core/Cardputer",
    "m5stack-core2": "https://docs.m5stack.com/en/core/core2",
}

# All 13 m5stack board ids the resolver must cover (the data/boards/m5stack/* dirs).
M5STACK_ALL_BOARDS = [
    "m5cardputer", "m5stack-core2", "m5stack-cores3", "m5stick-s3", "m5stick-cplus2",
    "m5dial", "m5atom-lite", "m5atoms3", "m5atoms3-lite", "m5nanoc6", "m5stamp-c3",
    "m5stamp-s3", "m5stack-papers3",
]


def test_m5stack_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained an "m5stack" entry, and it returns the EXACT live-verified
    # docs.m5stack.com product URL (best-first) for the three boards fetched during the build.
    assert "m5stack" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["m5stack"]
    for bid, url in M5STACK_VERIFIED_URLS.items():
        cands = resolver(bid, "esp32-s3")
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_m5stack_resolver_covers_all_13_boards_on_docs_domain():
    # (b) every one of the 13 m5stack boards resolves to a docs.m5stack.com/en/core/ URL —
    # no board falls through uncovered (the whole point of the slice: 0 → 13 boards).
    resolver = bb.VENDOR_DOC_RESOLVERS["m5stack"]
    for bid in M5STACK_ALL_BOARDS:
        cands = resolver(bid, "esp32")
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://docs.m5stack.com/en/core/"), cands[0]


def _m5_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the m5stack resolver's URL for
    `bid` — any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["m5stack"](bid, "esp32-s3")[0]
    return url, _fetcher({url: _fixture(fixture_name)})


def test_m5stack_core2_grounds_getting_started_usb_serial_and_images(tmp_path):
    # (c) core2's REAL page names CH9102 → usb_serial grounds; getting_started = the URL;
    # its carousel hero grounds images.photo AND its PinMap section embeds a GPIO diagram →
    # images.pinout grounds too (Slice 1 image grounding). download_mode is still OMITTED
    # (no Boot-button sequence on the page) → still partial.
    bid, soc = "m5stack-core2", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="m5stack")
    url, fetch = _m5_fetcher_for(bid, "m5stack-core2")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url
    assert set(entry["written"]) == {"usb_serial", "getting_started", "images"}
    assert set(entry["omitted"]) == {"download_mode"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "ch9102"          # the page explicitly names CH9102
    assert fm["getting_started"] == url
    assert "download_mode" not in fm             # OMITTED — never forced
    # images grounded by HTML context: hero photo + the PinMap-section GPIO diagram.
    assert fm["images"]["photo"].endswith("core2_01.jpg")
    assert fm["images"]["pinout"].endswith("M5StackM5Core2GPIO.png")
    cited = {s["field"]: s for s in fm["sources"]}
    for field in ("usb_serial", "getting_started", "images"):
        assert cited[field]["url"] == url and cited[field]["verified"] == TODAY


def test_m5stack_cardputer_grounds_native_jtag(tmp_path):
    # (d) Cardputer's REAL page states "USB Serial/JTAG" → native-usb-serial-jtag grounds.
    # download_mode is OMITTED (flash-safety): its only in-sentence-groundable text is a
    # misleading "release the button" tail fragment missing the hold-G0 precondition, which
    # survives only inside a flattened spec table — cite-or-omit → never written.
    bid, soc = "m5cardputer", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="m5stack")
    url, fetch = _m5_fetcher_for(bid, "m5cardputer")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert "download_mode" in entry["omitted"]
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert fm["getting_started"] == url
    assert "download_mode" not in fm  # OMITTED — never grounded from a half-instruction


def test_m5stack_stick_s3_grounds_getting_started_photo_and_manual_download_mode(tmp_path):
    # (e) StickS3's REAL page names NO bridge chip and no JTAG → usb_serial OMITTED. Its
    # carousel hero grounds images.photo, but its PinMap section is TABLES-ONLY (no diagram
    # image) → images.pinout correctly OMITTED (high-confidence-or-omit). getting_started
    # grounds off the resolved URL. download_mode now grounds via the m5stack manual branch
    # (the actionable "...press and hold the reset button..." sentence, cited to the URL).
    bid, soc = "m5stick-s3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="m5stack")
    url, fetch = _m5_fetcher_for(bid, "m5stick-s3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["download_mode", "getting_started", "images"]
    assert set(entry["omitted"]) == {"usb_serial"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert "usb_serial" not in fm
    assert fm["download_mode"]["mode"] == "manual"
    assert "press and hold the reset button" in fm["download_mode"]["steps"]
    # every written field carries its own citation to the resolved URL.
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["download_mode"]["url"] == url and cited["download_mode"]["verified"] == TODAY
    # photo grounded; pinout OMITTED (no diagram image under PinMap — pins are tabular).
    assert fm["images"]["photo"].endswith("K150-stickS3_main-products_01.webp")
    assert "pinout" not in fm["images"]


def test_m5stack_usb_serial_values_are_schema_enum_valid():
    # every usb_serial the m5stack pages ground MUST be in the board schema's enum, or the
    # guard rejects the board and the tick aborts.
    import json
    enum = set(json.load(open(bb.REPO / "schema" / "board.schema.json"))
               ["properties"]["usb_serial"]["enum"])
    for name in ("m5stack-core2", "m5cardputer"):
        val = bb.extract_usb_serial(bb._visible_text(_fixture(name)))
        assert val in enum


def test_m5stack_download_mode_core2_omitted_and_espressif_img_heuristic_finds_nothing():
    # CRITICAL cite-or-omit: core2's page states NO download mode at all, so download_mode
    # MUST stay None (the new m5stack manual branch does not over-match). And on ALL four
    # m5stack pages the ESPRESSIF filename image heuristic (the registry default) still finds
    # NOTHING on m5stack's opaque CDN — m5stack images only ground via the dedicated context
    # extractor (extract_images_m5stack), never the filename fallback.
    assert bb.extract_download_mode(bb._visible_text(_fixture("m5stack-core2"))) is None
    for name in ("m5stack-core2", "m5cardputer", "m5stick-s3", "m5stack-papers3"):
        raw = _fixture(name)
        assert bb.extract_images(raw, "https://docs.m5stack.com/en/core/X") is None


# ══════════════════════════════════════════════════════════════════════════════
# SLICE 1 (SPEC-vendor-image-grounding.md) — per-vendor image extractor registry.
#
# IMAGE_EXTRACTORS is keyed by brand: the "espressif" entry IS the unchanged filename
# heuristic (extract_images); the "m5stack" entry grounds photo + pinout by HTML CONTEXT
# on docs.m5stack.com. backfill_board selects the extractor by brand, falling back to the
# Espressif heuristic for brands with no entry (finds nothing on their CDN → omit).
# ══════════════════════════════════════════════════════════════════════════════

# The m5stack fixtures and the docs URL each was fetched at (their HTML is the fixture).
M5STACK_IMAGE_FIXTURES = {
    "m5stick-s3": "https://docs.m5stack.com/en/core/StickS3",
    "m5stack-core2": "https://docs.m5stack.com/en/core/core2",
    "m5cardputer": "https://docs.m5stack.com/en/core/Cardputer",
    "m5stack-papers3": "https://docs.m5stack.com/en/core/papers3",
}


def test_image_extractor_registry_wires_espressif_default_and_m5stack():
    # the registry exists, its espressif entry is the UNCHANGED filename heuristic (same
    # function object), and m5stack has its own context extractor.
    assert bb.IMAGE_EXTRACTORS["espressif"] is bb.extract_images
    assert bb.IMAGE_EXTRACTORS["m5stack"] is bb.extract_images_m5stack
    assert callable(bb.IMAGE_EXTRACTORS.get("m5stack"))


def test_espressif_image_extractor_unchanged_regression():
    # the default (espressif) extractor still grounds Espressif docs by filename — pins the
    # "no Espressif regression" guarantee (mirrors test_images_extract_where_the_page_links_them
    # but asserted through the registry default path).
    default = bb.IMAGE_EXTRACTORS.get("espressif", bb.extract_images)
    imgs = default(_fixture("esp32-s2-saola-1"), FIXTURE_URLS["esp32-s2-saola-1"])
    assert imgs["pinout"].endswith("esp32-s2_saola1-pinout.jpg")
    assert imgs["photo"].endswith("esp32-s2-saola-1-v1.2-isometric.png")
    # a brand with no registry entry falls back to the espressif heuristic (finds nothing
    # on a non-espressif CDN → None, no regression, no bad data).
    fallback = bb.IMAGE_EXTRACTORS.get("waveshare", bb.extract_images)
    assert fallback is bb.extract_images
    assert fallback(_fixture("m5stick-s3"), M5STACK_IMAGE_FIXTURES["m5stick-s3"]) is None


def test_m5stack_photo_grounds_from_carousel_hero_on_every_fixture():
    # photo = the first carousel `<img alt="Preview">` hero shot, an absolute CDN URL,
    # per-board distinct. Grounds on ALL four real fixtures.
    expected = {
        "m5stick-s3": "K150-stickS3_main-products_01.webp",
        "m5stack-core2": "core2_01.jpg",
        "m5cardputer": "K132-main-pictures_01.jpg",
        "m5stack-papers3": "PaperS3/4.webp",
    }
    for name, url in M5STACK_IMAGE_FIXTURES.items():
        imgs = bb.extract_images_m5stack(_fixture(name), url)
        assert imgs is not None and "photo" in imgs, name
        assert imgs["photo"].startswith("https://"), name
        assert imgs["photo"].endswith(expected[name]), (name, imgs["photo"])


def test_m5stack_pinout_grounds_only_when_pinmap_section_embeds_a_diagram():
    # core2's PinMap section embeds a GPIO diagram → pinout grounded to that exact absolute
    # URL. High-confidence-or-omit: the image sits under the explicit `<h2 id="pinmap">`.
    imgs = bb.extract_images_m5stack(_fixture("m5stack-core2"),
                                     M5STACK_IMAGE_FIXTURES["m5stack-core2"])
    assert imgs["pinout"] == "https://www.gwendesign.com/kb/m5stack/img/M5StackM5Core2GPIO.png"


def test_m5stack_pinout_omitted_when_pinmap_is_tabular_no_diagram():
    # SAFETY: stick-s3 / cardputer / papers3 have a PinMap section AND many product/gallery
    # images, but render the pin map as HTML TABLES (no diagram image). A random product
    # image is NEVER promoted to pinout → pinout OMITTED (a wrong wiring diagram can fry a
    # board). photo still grounds; only pinout is withheld.
    for name in ("m5stick-s3", "m5cardputer", "m5stack-papers3"):
        imgs = bb.extract_images_m5stack(_fixture(name), M5STACK_IMAGE_FIXTURES[name])
        assert imgs is not None and "photo" in imgs, name
        assert "pinout" not in imgs, (name, imgs.get("pinout"))


def test_m5stack_image_extractor_returns_none_on_pageless_html():
    # no carousel + no PinMap section → nothing grounded → None (cite-or-omit).
    assert bb.extract_images_m5stack("<html><body><p>nothing here</p></body></html>",
                                     "https://docs.m5stack.com/en/core/X") is None
    assert bb.extract_images_m5stack("", "https://docs.m5stack.com/en/core/X") is None


def test_m5stack_papers3_automatic_port_recognition_is_not_auto_download():
    # CRITICAL cite-or-omit regression: the PaperS3 page says "automatic port recognition"
    # (the OS auto-detecting the serial PORT) — that is NOT an auto-DOWNLOAD/auto-reset flash
    # claim. The auto-download exclusion MUST stay intact: the auto regex must not match, and
    # download_mode must NOT ground as "auto". (PaperS3 DOES ground as manual, but from its
    # real "Download Mode ... long press the power button ..." instruction — the auto branch
    # is never reached and never fooled.) usb_serial still grounds (the page names CH9102).
    raw = _fixture("m5stack-papers3")
    text = bb._visible_text(raw)
    assert bb._AUTO_DOWNLOAD_RE.search(text.lower()) is None  # "automatic port recognition" ≠ auto
    assert bb._AUTO_DOWNLOAD_RE.search("automatic port recognition") is None
    dm = bb.extract_download_mode(text)
    assert dm["mode"] == "manual"                    # grounded from the real instruction, NOT auto
    assert "long press the power button" in dm["steps"]
    assert bb.extract_usb_serial(text) == "ch9102"


@pytest.mark.parametrize("sentence", [
    "The board features an auto-reset circuit for hands-free flashing.",
    "After connecting, the board automatically enters download mode.",
    "The bootloader is triggered automatically on upload.",
])
def test_auto_download_still_grounds_on_genuine_phrasing(sentence):
    # The tightening must not throw out the baby: a real auto-download/auto-reset statement
    # still grounds to {"mode": "auto"} (no Espressif regression — its fixtures are all manual,
    # but the auto path must keep working for genuinely auto-reset boards).
    assert bb.extract_download_mode(sentence) == {"mode": "auto"}


def test_m5stack_board_404_skipped_cleanly(tmp_path):
    # (f) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid, soc = "m5stack-core2", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="m5stack")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ══════════════════════════════════════════════════════════════════════════════
# SLICE 3 — adafruit vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 3).
#
# Registers the "adafruit" resolver on learn.adafruit.com so board_backfill reaches the
# adafruit boards. The real doc-URL pattern was CONFIRMED by a live fetch during the build:
# every adafruit board has a Learn guide at `learn.adafruit.com/<guide-slug>` (200, no
# redirect), where the guide slug is board-specific (adafruit-feather-esp32-v2 →
# adafruit-esp32-feather-v2, adafruit-qt-py-esp32-c3 → adafruit-qt-py-esp32-c3-wifi-dev-board)
# and NOT derivable from the board id — so the resolver carries a per-board map of the slug
# already cited in each board's `sources`, reconfirmed live. If adafruit renames a guide and
# one 404s, that board stays SKIPPED (doc-unreachable), never invented.
#
# EMPIRICAL grounding (measured on the REAL fetched Learn overview pages under fixtures/):
#   * getting_started — grounds for ALL mapped boards (the resolved 200 URL IS the field).
#   * usb_serial      — grounds where the overview page NAMES the bridge: Feather V2 states
#                       "CP2102N chipset" → cp2102n; QT Py ESP32-C3 lists the chip's
#                       "USB Serial/JTAG controller" → native-usb-serial-jtag. MatrixPortal S3
#                       names neither → OMITTED (cite-or-omit).
#   * download_mode   — grounds AUTO where the page states an auto-reset flashing circuit:
#                       Feather V2 "High speed upload with auto-reset", ItsyBitsy "auto-reset
#                       circuit works perfectly with any ESP32 uploading tool", HUZZAH32
#                       "automatic bootloader reset". (This is a real adafruit win m5stack
#                       lacked.) Boards without that phrasing → OMITTED. NEVER forced.
#   * images          — NOT groundable on the overview page: adafruit's pinout diagrams live
#                       on the separate /pinouts page and use opaque cdn-learn image filenames
#                       matching none of the pinout/photo keyword patterns. Left OMITTED.
#
# NOT mapped: adafruit-feather-esp32-s2 (10 of 11). Its Learn overview page cross-links an
# unrelated "CircuitPython Libraries on any Computer with FT232H" guide, on which the shared
# usb_serial extractor FALSE-POSITIVES to "other" — but the S2 Feather is a native-USB board
# (no FTDI bridge). Mapping it would write a WRONG flash-critical field, so it is left
# unmapped (skipped doc-unreachable, honest) pending extractor tuning — a documented follow-up.
# ══════════════════════════════════════════════════════════════════════════════

# The three URLs confirmed 200 by a live fetch on 2026-09-10 (their HTML is the fixtures).
ADAFRUIT_VERIFIED_URLS = {
    "adafruit-feather-esp32-v2": "https://learn.adafruit.com/adafruit-esp32-feather-v2",
    "adafruit-qt-py-esp32-c3": "https://learn.adafruit.com/adafruit-qt-py-esp32-c3-wifi-dev-board",
    "adafruit-matrixportal-s3": "https://learn.adafruit.com/adafruit-matrixportal-s3",
}

# The 10 adafruit board ids the resolver maps (all 11 data/boards/adafruit/* dirs EXCEPT
# adafruit-feather-esp32-s2 — see the FT232H false-positive note above).
ADAFRUIT_MAPPED_BOARDS = [
    "adafruit-feather-esp32-s3", "adafruit-feather-esp32-s3-reverse-tft",
    "adafruit-feather-esp32-v2", "adafruit-huzzah32-esp32-feather",
    "adafruit-itsybitsy-esp32", "adafruit-matrixportal-s3", "adafruit-metro-esp32-s3",
    "adafruit-qt-py-esp32-c3", "adafruit-qt-py-esp32-s2", "adafruit-qt-py-esp32-s3",
]


def test_adafruit_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained an "adafruit" entry, and it returns the EXACT live-verified
    # learn.adafruit.com guide URL (best-first) for the three boards fetched during the build.
    assert "adafruit" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["adafruit"]
    for bid, url in ADAFRUIT_VERIFIED_URLS.items():
        cands = resolver(bid, "esp32-s3")
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_adafruit_resolver_covers_10_boards_on_learn_domain():
    # (b) every mapped adafruit board resolves to a learn.adafruit.com URL — no mapped board
    # falls through uncovered (0 → 10 boards this slice).
    resolver = bb.VENDOR_DOC_RESOLVERS["adafruit"]
    for bid in ADAFRUIT_MAPPED_BOARDS:
        cands = resolver(bid, "esp32")
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://learn.adafruit.com/"), cands[0]


def test_adafruit_feather_s2_is_not_mapped_ft232h_false_positive():
    # (c) the S2 Feather is deliberately UNMAPPED (its overview page trips the shared
    # usb_serial extractor on an unrelated FT232H cross-link → "other", but the board is
    # native-USB). The resolver returns [] for it, so backfill_board SKIPS it doc-unreachable
    # and never writes the wrong value. Guards the cite-or-omit decision to leave it out.
    assert bb.VENDOR_DOC_RESOLVERS["adafruit"]("adafruit-feather-esp32-s2", "esp32-s2") == []


def _ada_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the adafruit resolver's URL for
    `bid` — any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["adafruit"](bid, "esp32-s3")[0]
    return url, _fetcher({url: _fixture(fixture_name)})


def test_adafruit_feather_v2_grounds_usb_serial_download_mode_and_photo(tmp_path):
    # (d) Feather V2's REAL page names "CP2102N chipset" → usb_serial=cp2102n, AND states an
    # "auto-reset" upload circuit → download_mode=auto; getting_started = the URL. Since Slice 2
    # of the image-grounding spec, images.photo ALSO grounds from the Learn og:image hero (pinout
    # still OMITTED — it lives on /pinouts). All four missing fields fill → NOT partial.
    bid, soc = "adafruit-feather-esp32-v2", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="adafruit")
    url, fetch = _ada_fetcher_for(bid, "adafruit-feather-esp32-v2")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url
    assert set(entry["written"]) == {"download_mode", "usb_serial", "getting_started", "images"}
    assert entry["omitted"] == []
    assert entry["partial"] is False

    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "cp2102n"
    assert fm["download_mode"]["mode"] == "auto"
    assert fm["getting_started"] == url
    assert fm["images"] == {
        "photo": "https://cdn-learn.adafruit.com/guides/images/000/003/544/medium800/FV2_top_angle.jpg"}
    assert "pinout" not in fm["images"]  # deferred to the /pinouts sub-page
    cited = {s["field"]: s for s in fm["sources"]}
    for field in ("download_mode", "usb_serial", "getting_started", "images"):
        assert cited[field]["url"] == url and cited[field]["verified"] == TODAY


def test_adafruit_qt_py_c3_grounds_native_jtag(tmp_path):
    # (e) QT Py ESP32-C3's REAL page states "USB Serial/JTAG controller" → native-usb-serial-jtag.
    bid, soc = "adafruit-qt-py-esp32-c3", "esp32-c3"
    path = _write_board(tmp_path, bid, soc, brand="adafruit")
    url, fetch = _ada_fetcher_for(bid, "adafruit-qt-py-esp32-c3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert fm["getting_started"] == url


def test_adafruit_matrixportal_grounds_getting_started_and_photo(tmp_path):
    # (f) MatrixPortal S3's REAL page names no bridge, no JTAG, no auto-reset phrasing → neither
    # usb_serial nor download_mode grounds. getting_started grounds, and (Slice 2) images.photo
    # grounds from the og:image hero. pinout stays OMITTED (on /pinouts). Still cite-or-omit.
    bid, soc = "adafruit-matrixportal-s3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="adafruit")
    url, fetch = _ada_fetcher_for(bid, "adafruit-matrixportal-s3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["getting_started", "images"]  # BACKFILL_FIELDS order
    assert set(entry["omitted"]) == {"download_mode", "usb_serial"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["images"] == {
        "photo": "https://cdn-learn.adafruit.com/guides/images/000/003/849/medium800thumb/5778-06.gif"}
    assert "pinout" not in fm["images"]
    assert "usb_serial" not in fm
    assert "download_mode" not in fm


def test_adafruit_usb_serial_values_are_schema_enum_valid():
    # every usb_serial the adafruit pages ground MUST be in the board schema's enum, or the
    # guard rejects the board and the tick aborts.
    import json
    enum = set(json.load(open(bb.REPO / "schema" / "board.schema.json"))
               ["properties"]["usb_serial"]["enum"])
    for name in ("adafruit-feather-esp32-v2", "adafruit-qt-py-esp32-c3"):
        val = bb.extract_usb_serial(bb._visible_text(_fixture(name)))
        assert val in enum


def test_adafruit_filename_fallback_finds_nothing_motivates_context_extractor():
    # WHY adafruit needs a dedicated context extractor: on the REAL adafruit overview pages the
    # Espressif FILENAME heuristic (bb.extract_images) returns None — cdn-learn image names match
    # none of the pinout/photo keyword patterns. So without a context rule the images field would
    # stay omitted. The dedicated adafruit extractor (below) grounds photo from the Learn hero.
    for name in ("adafruit-feather-esp32-v2", "adafruit-qt-py-esp32-c3", "adafruit-matrixportal-s3"):
        raw = _fixture(name)
        assert bb.extract_images(raw, "https://learn.adafruit.com/x") is None


# ─── SLICE 2 (SPEC-vendor-image-grounding.md) — adafruit image grounding ──────────
# adafruit Learn overview pages (the committed fixtures) carry per-board hero shots ONLY via the
# Open Graph tag `<meta property="og:image" content="…cdn-learn.adafruit.com/guides/images/…">`.
# The page body's <img> tags are a RELATED-GUIDES carousel (they name OTHER boards) — never the
# subject board — so og:image is the sole reliable, per-board identifying photo. Pinout DIAGRAMS
# live on a SEPARATE `/pinouts` sub-page: each overview only carries a `<a href="…/pinouts">`
# TOC LINK (not an image), so pinout is OMITTED here — reaching /pinouts is a documented follow-up.
ADAFRUIT_IMAGE_FIXTURES = {
    "adafruit-feather-esp32-v2": (
        "https://learn.adafruit.com/adafruit-esp32-feather-v2/overview",
        "https://cdn-learn.adafruit.com/guides/images/000/003/544/medium800/FV2_top_angle.jpg",
    ),
    "adafruit-qt-py-esp32-c3": (
        "https://learn.adafruit.com/adafruit-qt-py-esp32-c3-wifi-dev-board/overview",
        "https://cdn-learn.adafruit.com/guides/images/000/003/547/medium800/Screenshot_1.png",
    ),
    "adafruit-matrixportal-s3": (
        "https://learn.adafruit.com/adafruit-matrixportal-s3/overview",
        "https://cdn-learn.adafruit.com/guides/images/000/003/849/medium800thumb/5778-06.gif",
    ),
}


def test_image_extractor_registry_wires_adafruit():
    # the registry gained an "adafruit" entry = its own context extractor; espressif + m5stack
    # entries are untouched (same function objects).
    assert bb.IMAGE_EXTRACTORS["adafruit"] is bb.extract_images_adafruit
    assert bb.IMAGE_EXTRACTORS["espressif"] is bb.extract_images
    assert bb.IMAGE_EXTRACTORS["m5stack"] is bb.extract_images_m5stack


def test_adafruit_photo_grounds_from_learn_hero_og_image():
    # photo = the guide's Open Graph hero image (the identifying board shot), an absolute
    # cdn-learn.adafruit.com URL, per-board distinct. Grounds on ALL three real fixtures.
    for name, (url, expected_photo) in ADAFRUIT_IMAGE_FIXTURES.items():
        imgs = bb.extract_images_adafruit(_fixture(name), url)
        assert imgs is not None and "photo" in imgs, name
        assert imgs["photo"] == expected_photo, (name, imgs["photo"])
        assert imgs["photo"].startswith("https://cdn-learn.adafruit.com/"), name


def test_adafruit_pinout_omitted_on_overview_pages_pinouts_is_followup():
    # SAFETY (high-confidence-or-omit): the overview fixtures embed NO pinout diagram — the
    # pinout guide lives on a separate `/pinouts` sub-page (only a TOC LINK to it appears here).
    # The extractor must NEVER promote the hero photo or a related-guides carousel image to
    # pinout, and must NOT mistake the `/pinouts` <a href> LINK for an image. Reaching the
    # /pinouts sub-page is a documented follow-up (out of scope for this offline slice).
    for name, (url, _photo) in ADAFRUIT_IMAGE_FIXTURES.items():
        imgs = bb.extract_images_adafruit(_fixture(name), url)
        assert imgs is not None, name
        assert "pinout" not in imgs, (name, imgs.get("pinout"))
        # sanity: the /pinouts link genuinely exists in the fixture (so the omission is real,
        # not because the page lacks any pinout reference at all).
        assert "/pinouts" in _fixture(name), name


def test_adafruit_image_extractor_omits_photo_when_no_og_image():
    # cite-or-omit: a page with no og:image grounds no photo → None (never invents one). Also
    # guards that a bare `/pinouts` link with no og:image does not fabricate any image.
    assert bb.extract_images_adafruit(
        '<html><body><a href="/x/pinouts">Pinouts</a><p>no hero</p></body></html>',
        "https://learn.adafruit.com/x/overview") is None
    assert bb.extract_images_adafruit("", "https://learn.adafruit.com/x/overview") is None


def test_adafruit_extractor_ignores_non_adafruit_og_image():
    # SAFETY: only an og:image on adafruit's own CDN is grounded — a foreign og:image (e.g. an
    # embedded third-party widget) is NOT taken as the board photo.
    raw = ('<meta property="og:image" '
           'content="https://evil.example.com/not-a-board.jpg" />')
    assert bb.extract_images_adafruit(raw, "https://learn.adafruit.com/x/overview") is None


def test_adafruit_board_404_skipped_cleanly(tmp_path):
    # (g) a board whose Learn guide 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid, soc = "adafruit-qt-py-esp32-c3", "esp32-c3"
    path = _write_board(tmp_path, bid, soc, brand="adafruit")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ══════════════════════════════════════════════════════════════════════════════
# SLICE 4 — lilygo vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 4).
#
# Registers the "lilygo" resolver on lilygo.cc so board_backfill reaches the 10 lilygo boards.
# The real doc-URL pattern was CONFIRMED by a live fetch during the build: every lilygo board
# has a product page at `lilygo.cc/products/<slug>` (200, no redirect with the bot UA; note
# www.lilygo.cc 301-redirects to the bare lilygo.cc host, so the resolver uses the canonical
# no-www host). The <slug> is board-specific and NOT derivable from the board id
# (lilygo-t5-epaper-s3-pro → t5-e-paper-s3-pro), so the resolver carries a per-board map of the
# slug already cited in each board's `sources` (reconfirmed live). All 10 slugs were also
# og:title-confirmed to name the right product. If lilygo renames a page and one 404s, that
# board stays SKIPPED (doc-unreachable), never invented.
#
# EMPIRICAL grounding (measured on the REAL fetched product pages under fixtures/):
#   * getting_started — grounds for ALL 10 (the resolved 200 URL IS the field). The win.
#   * usb_serial      — GATED OFF for lilygo (VENDOR_UNGROUNDABLE_FIELDS). Every lilygo.cc
#                       product page carries an IDENTICAL site-wide "Driver of CH9102" nav link
#                       (in the header, on T-QT-Pro, T-Display, T-Beam, ... all pages), so the
#                       shared usb_serial extractor FALSE-POSITIVES to "ch9102" off site chrome
#                       — NOT the product's actual bridge (many lilygo boards are not CH9102).
#                       This is the adafruit-feather-s2/FT232H trap at SITE scale: writing it
#                       would set a WRONG flash-critical field, so usb_serial is left out
#                       (cite-or-omit) and pinned below. A future slice can strip site chrome.
#   * download_mode   — NOT groundable: the Shopify product pages carry no Boot/Reset flashing
#                       sequence and no auto-reset phrasing, so the extractor returns None.
#   * images          — the Espressif FILENAME heuristic finds nothing (opaque Shopify CDN
#                       names), but the dedicated lilygo image extractor (SPEC-vendor-image-
#                       grounding.md, Slice 3) grounds images.PHOTO by HTML CONTEXT — the first
#                       `product__media-item is-active` gallery slide's <img> on lilygo's own
#                       CDN. PINOUT stays OMITTED (no marked diagram; safety high-conf-or-omit).
#                       See the SPEC-vendor-image-grounding Slice-3 tests at the end of this file.
# ══════════════════════════════════════════════════════════════════════════════

# The URLs confirmed 200 (no redirect) by a live fetch on 2026-09-10 (their HTML is fixtures).
LILYGO_VERIFIED_URLS = {
    "lilygo-t-display-s3": "https://lilygo.cc/products/t-display-s3",
    "lilygo-t-beam": "https://lilygo.cc/products/t-beam",
    "lilygo-t-qt-pro": "https://lilygo.cc/products/t-qt-pro",
}

# All 10 lilygo board ids the resolver must cover (the data/boards/lilygo/* dirs).
LILYGO_ALL_BOARDS = [
    "lilygo-t-beam", "lilygo-t-deck", "lilygo-t-display", "lilygo-t-display-s3",
    "lilygo-t-display-s3-amoled", "lilygo-t-dongle-s3", "lilygo-t-embed",
    "lilygo-t-qt-pro", "lilygo-t-watch-s3", "lilygo-t5-epaper-s3-pro",
]


def test_lilygo_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained a "lilygo" entry, and it returns the EXACT live-verified
    # lilygo.cc product URL (best-first) for boards fetched during the build.
    assert "lilygo" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["lilygo"]
    for bid, url in LILYGO_VERIFIED_URLS.items():
        cands = resolver(bid, "esp32-s3")
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_lilygo_resolver_covers_all_10_boards_on_lilygo_domain():
    # (b) every one of the 10 lilygo boards resolves to a lilygo.cc/products/ URL — no board
    # falls through uncovered (0 → 10 boards this slice).
    resolver = bb.VENDOR_DOC_RESOLVERS["lilygo"]
    for bid in LILYGO_ALL_BOARDS:
        cands = resolver(bid, "esp32")
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://lilygo.cc/products/"), cands[0]


def _lily_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the lilygo resolver's URL for `bid` —
    any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["lilygo"](bid, "esp32-s3")[0]
    return url, _fetcher({url: _fixture(fixture_name)})


def test_lilygo_grounds_getting_started_and_photo(tmp_path):
    # (c) T-QT-Pro's REAL page grounds getting_started = the URL AND images.photo (the active
    # gallery slide's hero on lilygo's own CDN — SPEC-vendor-image-grounding Slice 3). usb_serial
    # is GATED (chrome false-positive, below); download_mode + images.pinout are not groundable.
    bid, soc = "lilygo-t-qt-pro", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="lilygo")
    url, fetch = _lily_fetcher_for(bid, "lilygo-t-qt-pro")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url
    assert entry["written"] == ["getting_started", "images"]
    assert set(entry["omitted"]) == {"download_mode", "usb_serial"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["images"] == {"photo": "https://lilygo.cc/cdn/shop/products/H579-T-QT-Pro_2.jpg"}
    assert "pinout" not in fm["images"]           # high-confidence-or-omit: no marked diagram
    assert "usb_serial" not in fm                 # GATED — never written
    assert "download_mode" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url and cited["getting_started"]["verified"] == TODAY
    assert cited["images"]["url"] == url and cited["images"]["verified"] == TODAY


def test_lilygo_usb_serial_chrome_false_positive_is_gated_not_written(tmp_path):
    # (d) CRITICAL cite-or-omit: the raw usb_serial extractor DOES false-positive to "ch9102"
    # on the real page (the site-wide "Driver of CH9102" nav chrome present on every lilygo.cc
    # product page), so usb_serial is declared UNGROUNDABLE for lilygo and gated off — proven
    # here: the extractor reads ch9102 off the fixture, but backfill must NOT write it.
    assert bb.extract_usb_serial(bb._visible_text(_fixture("lilygo-t-qt-pro"))) == "ch9102"
    assert "usb_serial" in bb.VENDOR_UNGROUNDABLE_FIELDS["lilygo"]

    bid, soc = "lilygo-t-qt-pro", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="lilygo")
    url, fetch = _lily_fetcher_for(bid, "lilygo-t-qt-pro")
    bb.backfill_board(path, tmp_path, fetch, TODAY)

    fm, _ = bb.parse_frontmatter(path)
    assert "usb_serial" not in fm                 # gated → chrome false-positive never written
    usb_sources = [s for s in fm.get("sources", []) if s["field"] == "usb_serial"]
    assert usb_sources == []                       # and no bogus usb_serial citation appended


def test_lilygo_download_mode_and_images_not_grounded_on_real_pages():
    # CRITICAL cite-or-omit: on the REAL lilygo product pages the download_mode and image
    # heuristics correctly return None (no false positives), so those fields stay omitted.
    for name in ("lilygo-t-qt-pro", "lilygo-t5-epaper-s3-pro"):
        raw = _fixture(name)
        assert bb.extract_download_mode(bb._visible_text(raw)) is None
        assert bb.extract_images(raw, "https://lilygo.cc/products/x") is None


def test_lilygo_t5_epaper_grounds_getting_started(tmp_path):
    # (e) the T5 e-paper board's lilygo.cc slug (t5-e-paper-s3-pro) is NOT cited in its sources
    # (which cite only GitHub) but was live-verified 200 and og:title-confirmed "T5 E-Paper S3
    # Pro" — so it is a verified URL, not an invented one; getting_started grounds.
    bid, soc = "lilygo-t5-epaper-s3-pro", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="lilygo")
    url, fetch = _lily_fetcher_for(bid, "lilygo-t5-epaper-s3-pro")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == "https://lilygo.cc/products/t5-e-paper-s3-pro"
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url


def test_lilygo_board_404_skipped_cleanly(tmp_path):
    # (f) a board whose product page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid, soc = "lilygo-t-qt-pro", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="lilygo")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ══════════════════════════════════════════════════════════════════════════════
# SLICE 3 (SPEC-vendor-image-grounding.md) — lilygo image extractor + module split.
#
# The per-vendor image extractors now live in jr/board_image_extractors.py; board_backfill
# re-exports them (bb.extract_images / _m5stack / _adafruit / _lilygo) and IMAGE_EXTRACTORS,
# so every existing image test above is behaviour-preserving through the same bb.* names.
#
# lilygo product pages are Shopify (Dawn theme). They carry NO og:image and NO JSON-LD; the
# board hero is the FIRST product-gallery slide, marked
#   `<li class="product__media-item … is-active …">…<img src="//lilygo.cc/cdn/shop/…">`.
# We ground images.PHOTO from that active slide's <img>, ONLY when it resolves to lilygo's own
# domain (…lilygo.cc). PINOUT is OMITTED for lilygo: the only pinout-ish signal is a loose
# `<p><strong>1. Pin Diagram</strong></p>` bold label inside the marketing description blob of
# T-QT-Pro (no semantic section/anchor, empty-alt image, a product-shot filename), and the T5
# fixture has no pinout marker at all — below the high-confidence-or-omit safety bar, so we
# NEVER promote any image to pinout (a wrong wiring diagram can fry a board).
# ══════════════════════════════════════════════════════════════════════════════

# Each lilygo fixture and the lilygo.cc product URL it was fetched at, plus its expected hero.
LILYGO_IMAGE_FIXTURES = {
    "lilygo-t-qt-pro": (
        "https://lilygo.cc/products/t-qt-pro",
        "https://lilygo.cc/cdn/shop/products/H579-T-QT-Pro_2.jpg",
    ),
    "lilygo-t5-epaper-s3-pro": (
        "https://lilygo.cc/products/t5-e-paper-s3-pro",
        "https://lilygo.cc/cdn/shop/files/T5-4_7.jpg",
    ),
}


def test_image_extractor_registry_wires_lilygo():
    # the registry gained a "lilygo" entry = its own context extractor; espressif + m5stack +
    # adafruit entries are untouched (same function objects — the split preserves identity).
    assert bb.IMAGE_EXTRACTORS["lilygo"] is bb.extract_images_lilygo
    assert bb.IMAGE_EXTRACTORS["espressif"] is bb.extract_images
    assert bb.IMAGE_EXTRACTORS["m5stack"] is bb.extract_images_m5stack
    assert bb.IMAGE_EXTRACTORS["adafruit"] is bb.extract_images_adafruit


def test_lilygo_photo_grounds_from_active_media_slide_own_cdn():
    # photo = the first `product__media-item is-active` gallery slide's <img>, resolved to an
    # absolute lilygo.cc CDN URL (query params stripped to the canonical image). Grounds on BOTH
    # real fixtures, per-board distinct.
    for name, (url, expected_photo) in LILYGO_IMAGE_FIXTURES.items():
        imgs = bb.extract_images_lilygo(_fixture(name), url)
        assert imgs is not None and "photo" in imgs, name
        assert imgs["photo"] == expected_photo, (name, imgs["photo"])
        assert imgs["photo"].startswith("https://lilygo.cc/cdn/shop/"), name


def test_lilygo_pinout_always_omitted_no_marked_diagram():
    # SAFETY (high-confidence-or-omit): even though T-QT-Pro's marketing blob contains a bold
    # "1. Pin Diagram" label AND many product images, there is no semantically-marked pinout
    # diagram → pinout is NEVER grounded. A random/plausible image is never promoted to pinout
    # (a wrong wiring diagram can fry a board). photo still grounds; only pinout is withheld.
    assert "1. Pin Diagram" in _fixture("lilygo-t-qt-pro")   # the loose label really is present
    for name, (url, _photo) in LILYGO_IMAGE_FIXTURES.items():
        imgs = bb.extract_images_lilygo(_fixture(name), url)
        assert imgs is not None, name
        assert "pinout" not in imgs, (name, imgs.get("pinout"))


def test_lilygo_image_extractor_grounds_photo_only_from_lilygo_domain():
    # SAFETY: a hero <img> in the active slide that points at a FOREIGN domain is NOT grounded
    # (mirrors adafruit's own-CDN gate) — only lilygo.cc's own images become the board photo.
    foreign = ('<li class="product__media-item grid__item slider__slide is-active">'
               '<div class="product__media media">'
               '<img src="https://cdn.evil.example.com/not-a-board.jpg" alt=""></div></li>')
    assert bb.extract_images_lilygo(foreign, "https://lilygo.cc/products/x") is None
    # a genuine lilygo.cc active-slide image IS grounded (control).
    own = ('<li class="product__media-item grid__item slider__slide is-active">'
           '<div class="product__media media">'
           '<img src="//lilygo.cc/cdn/shop/products/Board_1.jpg?v=1&amp;width=1946" alt=""></div></li>')
    imgs = bb.extract_images_lilygo(own, "https://lilygo.cc/products/x")
    assert imgs == {"photo": "https://lilygo.cc/cdn/shop/products/Board_1.jpg"}


def test_lilygo_image_extractor_returns_none_on_pageless_html():
    # no active gallery slide → nothing grounded → None (cite-or-omit).
    assert bb.extract_images_lilygo("<html><body><p>nothing here</p></body></html>",
                                    "https://lilygo.cc/products/x") is None
    assert bb.extract_images_lilygo("", "https://lilygo.cc/products/x") is None


def test_lilygo_t5_epaper_grounds_photo_end_to_end(tmp_path):
    # end-to-end: the T5 e-paper board grounds getting_started AND images.photo (its own-CDN
    # hero), with pinout omitted — through backfill_board / IMAGE_EXTRACTORS registry.
    bid, soc = "lilygo-t5-epaper-s3-pro", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="lilygo")
    url, fetch = _lily_fetcher_for(bid, "lilygo-t5-epaper-s3-pro")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert "images" in entry["written"]
    fm, _ = bb.parse_frontmatter(path)
    assert fm["images"] == {"photo": "https://lilygo.cc/cdn/shop/files/T5-4_7.jpg"}


# ══════════════════════════════════════════════════════════════════════════════
# SLICE 5 — heltec vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 5).
# ──────────────────────────────────────────────────────────────────────────────
# Registers the "heltec" resolver on docs.heltec.org so board_backfill reaches the 5 heltec
# boards. UNLIKE the m5stack/adafruit/lilygo per-board maps, heltec's doc URL is a clean,
# DETERMINISTIC rule (verified live to yield all 5 real doc pages, 200): strip the `heltec-`
# prefix, strip a trailing `-v3`, replace `-` with `_`, then
# `https://docs.heltec.org/en/node/esp32/<that>/index.html`. All 5 board ids fit the rule
# exactly, so no board is hardcoded (if one ever didn't fit, it would go in a small override
# map rather than forcing the rule). Each URL below was fetched & verified 200 on 2026-09-11,
# and the page confirmed to describe the correct V3/ESP32-S3 board; the HTML is saved as the
# Slice-5 fixtures.
#
# EMPIRICAL grounding (measured on the REAL fetched doc pages under fixtures/):
#   * getting_started — grounds for ALL 5 (the resolved 200 doc page IS the link).
#   * usb_serial      — grounds ONLY where the page NAMES the bridge: wifi-kit-32-v3 and
#                       wifi-lora-32-v3 both state "Integrated CP2102 USB to serial port chip"
#                       → cp2102. wireless-stick-v3 / wireless-tracker / wireless-paper do NOT
#                       name a bridge on their doc page (the only "Bridge"/"Boot" tokens are
#                       site-nav chrome — "Wireless Bridge", "Heltec WirelessBoot"), so
#                       usb_serial stays OMITTED there (cite-or-omit). NOTE: in the real
#                       data/boards/heltec/* files usb_serial is already filled (from other
#                       sources), so a real run never rewrites it — but the extractor grounding
#                       is proven here on the page text directly.
#   * download_mode   — NOT groundable on any heltec page: none carries a Boot+Reset "Firmware
#                       Download mode" sentence, and the nav-chrome "Boot" token does NOT
#                       false-positive the extractor. Omitted (cite-or-omit).
#   * images          — NOT groundable: the doc pages carry NO og:image and the espressif
#                       filename heuristic (the registry default for heltec — no dedicated
#                       heltec image extractor this slice) finds nothing. Omitted.
# So on the real (usb_serial-already-filled) boards this slice grounds getting_started only —
# an honest 0→1 per board, with download_mode + images explicitly omitted.

# The 5 URLs confirmed 200 by a live fetch on 2026-09-11 (their HTML is the fixtures).
HELTEC_VERIFIED_URLS = {
    "heltec-wifi-kit-32-v3": "https://docs.heltec.org/en/node/esp32/wifi_kit_32/index.html",
    "heltec-wifi-lora-32-v3": "https://docs.heltec.org/en/node/esp32/wifi_lora_32/index.html",
    "heltec-wireless-stick-v3": "https://docs.heltec.org/en/node/esp32/wireless_stick/index.html",
    "heltec-wireless-tracker": "https://docs.heltec.org/en/node/esp32/wireless_tracker/index.html",
    "heltec-wireless-paper": "https://docs.heltec.org/en/node/esp32/wireless_paper/index.html",
}

# All 5 heltec board ids the resolver must cover (the data/boards/heltec/* dirs).
HELTEC_ALL_BOARDS = list(HELTEC_VERIFIED_URLS)


def test_heltec_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained a "heltec" entry, and its deterministic rule returns the EXACT
    # live-verified docs.heltec.org URL (best-first) for every one of the 5 boards.
    assert "heltec" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["heltec"]
    for bid, url in HELTEC_VERIFIED_URLS.items():
        cands = resolver(bid, "esp32-s3")
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_heltec_resolver_covers_all_5_boards_on_docs_domain():
    # (b) every one of the 5 heltec boards resolves to a docs.heltec.org URL — no board falls
    # through uncovered (0 → 5 boards this slice).
    resolver = bb.VENDOR_DOC_RESOLVERS["heltec"]
    for bid in HELTEC_ALL_BOARDS:
        cands = resolver(bid, "esp32-s3")
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://docs.heltec.org/en/node/esp32/"), cands[0]
        assert cands[0].endswith("/index.html"), cands[0]


def test_heltec_resolver_non_heltec_id_returns_empty():
    # (c) the resolver only claims heltec-prefixed ids; an id it doesn't own yields [] (→ that
    # board would be skipped doc-unreachable, never sent to a guessed heltec URL).
    resolver = bb.VENDOR_DOC_RESOLVERS["heltec"]
    assert resolver("esp32-devkitc", "esp32") == []
    assert resolver("m5stack-core2", "esp32") == []


def _heltec_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the heltec resolver's URL for `bid` —
    any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["heltec"](bid, "esp32-s3")[0]
    return url, _fetcher({url: _fixture(fixture_name)})


@pytest.mark.parametrize("name", ["heltec-wifi-kit-32-v3", "heltec-wifi-lora-32-v3"])
def test_heltec_usb_serial_grounds_cp2102_where_page_names_it(name):
    # (d) the two boards whose doc page states "Integrated CP2102 ... serial port chip" ground
    # usb_serial=cp2102 (a schema-valid enum value). This is grounded off the page text.
    val = bb.extract_usb_serial(bb._visible_text(_fixture(name)))
    assert val == "cp2102", f"{name} → {val!r}"


@pytest.mark.parametrize("name", ["heltec-wireless-stick-v3", "heltec-wireless-tracker",
                                  "heltec-wireless-paper"])
def test_heltec_usb_serial_omitted_when_page_names_no_bridge(name):
    # (e) CRITICAL cite-or-omit: the stick/tracker/paper doc pages do NOT name a bridge chip —
    # the only "Bridge"/"Boot" tokens are site-nav chrome ("Wireless Bridge", "Heltec
    # WirelessBoot"), which must NOT false-positive the extractor. usb_serial stays None.
    assert bb.extract_usb_serial(bb._visible_text(_fixture(name))) is None


@pytest.mark.parametrize("name", list(HELTEC_VERIFIED_URLS))
def test_heltec_download_mode_and_images_omitted_on_real_pages(name):
    # (f) CRITICAL cite-or-omit: on ALL 5 REAL heltec pages the download_mode and image
    # heuristics correctly return None (nav-chrome "Boot" does not ground a flash-critical
    # download-mode step; no og:image / no groundable filename), so those fields stay omitted.
    raw = _fixture(name)
    assert bb.extract_download_mode(bb._visible_text(raw)) is None
    assert bb.extract_images(raw, "https://docs.heltec.org/x") is None


def test_heltec_wifi_kit_grounds_getting_started_and_usb_serial(tmp_path):
    # (g) end-to-end on a bare board: wifi-kit-32-v3's page grounds getting_started = the URL
    # AND usb_serial=cp2102 (the page names it); download_mode + images are OMITTED.
    bid, soc = "heltec-wifi-kit-32-v3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="heltec")
    url, fetch = _heltec_fetcher_for(bid, "heltec-wifi-kit-32-v3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url
    assert entry["written"] == ["usb_serial", "getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "cp2102"
    assert "download_mode" not in fm
    assert "images" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url and cited["getting_started"]["verified"] == TODAY
    assert cited["usb_serial"]["url"] == url and cited["usb_serial"]["verified"] == TODAY


def test_heltec_wireless_tracker_grounds_getting_started_only(tmp_path):
    # (h) end-to-end on a bare board: wireless-tracker's page names no bridge → usb_serial is
    # OMITTED alongside download_mode + images; only getting_started grounds (honest 0→1).
    bid, soc = "heltec-wireless-tracker", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="heltec")
    url, fetch = _heltec_fetcher_for(bid, "heltec-wireless-tracker")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "usb_serial", "images"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert "usb_serial" not in fm


def test_heltec_grounds_getting_started_when_usb_serial_already_filled(tmp_path):
    # (i) mirrors the REAL data (usb_serial already present from other sources): backfill writes
    # ONLY getting_started, never touching the pre-filled usb_serial. This is the true per-board
    # coverage delta on a real run (0→1: getting_started; download_mode + images omitted).
    bid, soc = "heltec-wifi-lora-32-v3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="heltec", extra_fields="usb_serial: cp2102\n")
    url, fetch = _heltec_fetcher_for(bid, "heltec-wifi-lora-32-v3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "images"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "cp2102"           # pre-filled, untouched
    usb_sources = [s for s in fm["sources"] if s["field"] == "usb_serial"]
    assert usb_sources == []                       # no new citation appended for a filled field


def test_heltec_board_404_skipped_cleanly(tmp_path):
    # (j) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid, soc = "heltec-wifi-kit-32-v3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="heltec")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ──────────────────────────────────────────────────────────────────────────────
# SLICE 6 — seeed vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 6).
# ──────────────────────────────────────────────────────────────────────────────
# Registers the "seeed" resolver on wiki.seeedstudio.com so board_backfill reaches the 3 Seeed
# XIAO ESP32 boards. UNLIKE heltec's clean deterministic rule, the Seeed wiki slugs are NOT
# case-uniform: the C3 page is CamelCase (`XIAO_ESP32C3_Getting_Started`) while the C6 and S3
# pages are lowercase (`xiao_esp32c6_getting_started`). A single naive rule can't yield all
# three, so — like the m5stack/adafruit/lilygo maps — this resolver is a small EXPLICIT per-board
# map of the three URLs each fetched & verified 200 on 2026-09-11 (each page's main content
# describes the matching chip; the HTML is saved as the Slice-6 fixtures). Only confirmed URLs
# are ever emitted (never a guessed case variant). The resolver only claims the three XIAO ids;
# any other id yields [] (→ skipped doc-unreachable, never a guessed URL).
#
# EMPIRICAL grounding (measured on the REAL fetched wiki pages under fixtures/):
#   * getting_started — grounds for ALL 3 (the resolved 200 doc page IS the link).
#   * usb_serial      — OMITTED on all 3: the getting-started wiki pages do NOT name a
#                       USB-UART bridge in a form the extractor grounds (cite-or-omit).
#   * download_mode   — OMITTED on all 3: no Boot+Reset "Firmware Download mode" sentence.
#   * images          — OMITTED on all 3: no groundable og:image / filename (no dedicated seeed
#                       image extractor this slice → espressif filename heuristic finds nothing).
# So this slice grounds getting_started only — an honest 0→1 per board, with download_mode +
# usb_serial + images explicitly omitted.

# The 3 URLs confirmed 200 by a live fetch on 2026-09-11 (their HTML is the fixtures). NOTE the
# deliberate casing split: C3 CamelCase, C6/S3 lowercase — copied verbatim from the live pages.
SEEED_VERIFIED_URLS = {
    "xiao-esp32c3": "https://wiki.seeedstudio.com/XIAO_ESP32C3_Getting_Started/",
    "xiao-esp32c6": "https://wiki.seeedstudio.com/xiao_esp32c6_getting_started/",
    "xiao-esp32s3": "https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/",
}

# All 3 seeed board ids the resolver must cover (the data/boards/seeed/* dirs).
SEEED_ALL_BOARDS = list(SEEED_VERIFIED_URLS)
SEEED_SOC = {"xiao-esp32c3": "esp32-c3", "xiao-esp32c6": "esp32-c6", "xiao-esp32s3": "esp32-s3"}


def test_seeed_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained a "seeed" entry, and it returns the EXACT live-verified
    # wiki.seeedstudio.com URL (best-first) for every one of the 3 boards — including the
    # deliberate C3-CamelCase / C6-S3-lowercase split (never a guessed case variant).
    assert "seeed" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["seeed"]
    for bid, url in SEEED_VERIFIED_URLS.items():
        cands = resolver(bid, SEEED_SOC[bid])
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_seeed_resolver_covers_all_3_boards_on_wiki_domain():
    # (b) every one of the 3 seeed boards resolves to a wiki.seeedstudio.com URL — no board
    # falls through uncovered (0 → 3 boards this slice).
    resolver = bb.VENDOR_DOC_RESOLVERS["seeed"]
    for bid in SEEED_ALL_BOARDS:
        cands = resolver(bid, SEEED_SOC[bid])
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://wiki.seeedstudio.com/"), cands[0]


def test_seeed_resolver_non_seeed_id_returns_empty():
    # (c) the resolver only claims the 3 XIAO ids; an id it doesn't own yields [] (→ that board
    # would be skipped doc-unreachable, never sent to a guessed seeed URL).
    resolver = bb.VENDOR_DOC_RESOLVERS["seeed"]
    assert resolver("esp32-devkitc", "esp32") == []
    assert resolver("heltec-wifi-kit-32-v3", "esp32-s3") == []
    assert resolver("xiao-esp32c2", "esp32-c2") == []  # a plausible-but-unmapped XIAO id


def _seeed_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the seeed resolver's URL for `bid` —
    any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["seeed"](bid, SEEED_SOC[bid])[0]
    return url, _fetcher({url: _fixture(fixture_name)})


@pytest.mark.parametrize("name", list(SEEED_VERIFIED_URLS))
def test_seeed_download_mode_grounds_usb_serial_and_images_omitted_on_real_pages(name):
    # (d) CRITICAL cite-or-omit: on ALL 3 REAL seeed wiki pages download_mode NOW grounds as
    # manual from the XIAO "bootloader mode" BOOT-button instruction (semantically identical to
    # download mode), while usb_serial and image heuristics correctly return None — those two
    # fields stay OMITTED, never a guessed/false-positive flash-critical write.
    raw = _fixture(name)
    text = bb._visible_text(raw)
    assert bb.extract_download_mode(text) == {
        "mode": "manual", "steps": _XIAO_DOWNLOAD_MODE_STEPS[name]}
    assert bb.extract_usb_serial(text) is None
    assert bb.extract_images(raw, "https://wiki.seeedstudio.com/x") is None


@pytest.mark.parametrize("name", list(SEEED_VERIFIED_URLS))
def test_seeed_grounds_getting_started_and_download_mode(name, tmp_path):
    # (e) end-to-end on a bare board: each XIAO page grounds getting_started = the resolved URL
    # AND download_mode (manual, from the "bootloader mode" BOOT-button instruction); usb_serial
    # and images stay OMITTED. Honest 0→2 per board.
    path = _write_board(tmp_path, name, SEEED_SOC[name], brand="seeed")
    url, fetch = _seeed_fetcher_for(name, name)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url == SEEED_VERIFIED_URLS[name]
    assert entry["written"] == ["download_mode", "getting_started"]
    assert set(entry["omitted"]) == {"usb_serial", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["download_mode"] == {"mode": "manual", "steps": _XIAO_DOWNLOAD_MODE_STEPS[name]}
    assert "usb_serial" not in fm
    assert "images" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url
    assert cited["getting_started"]["verified"] == TODAY
    assert cited["download_mode"]["url"] == url
    assert cited["download_mode"]["verified"] == TODAY


def test_seeed_board_404_skipped_cleanly(tmp_path):
    # (f) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid, soc = "xiao-esp32c3", "esp32-c3"
    path = _write_board(tmp_path, bid, soc, brand="seeed")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ──────────────────────────────────────────────────────────────────────────────
# SLICE 7 — lolin (wemos) vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 7).
# ──────────────────────────────────────────────────────────────────────────────
# Registers the "lolin" resolver on www.wemos.cc so board_backfill reaches the 6 LOLIN (wemos)
# boards. LIKE heltec, lolin's doc URL is a clean DETERMINISTIC rule (verified live to yield all
# 6 real doc pages, 200): strip the `lolin-` prefix, replace `-` with `_` → `<name>`; the family
# folder is `<name>.split("_")[0]`; then `https://www.wemos.cc/en/latest/<family>/<name>.html`.
# All 6 board ids fit the rule exactly, so no board is hardcoded (if one ever didn't fit, it
# would go in a small override map rather than forcing the rule). Each URL below was fetched &
# verified 200 on 2026-09-11, and the page confirmed to describe the correct chip; the HTML is
# saved as the Slice-7 fixtures.
#
# EMPIRICAL grounding (measured on the REAL fetched doc pages under fixtures/):
#   * getting_started — grounds for ALL 6 (the resolved 200 doc page IS the link).
#   * usb_serial      — grounds ONLY where the page NAMES the bridge: d32 and d32-pro both state
#                       "CH340" → ch340. c3-mini / s2-mini / s3 / s3-mini do NOT name a bridge on
#                       their doc page, so usb_serial stays OMITTED there (cite-or-omit). NOTE: in
#                       the real data/boards/lolin/* files d32 / d32-pro already carry
#                       usb_serial: ch340 (and s3-mini native-usb-serial-jtag) from other
#                       sources, so a real run never rewrites them — but the extractor grounding
#                       is proven here on the page text directly.
#   * download_mode   — NOT groundable on any lolin page: none carries a Boot+Reset "Firmware
#                       Download mode" sentence. Omitted (cite-or-omit).
#   * images          — NOT groundable: the doc pages carry no groundable og:image and the
#                       espressif filename heuristic (the registry default for lolin — no
#                       dedicated lolin image extractor this slice) finds nothing. Omitted.

# The 6 URLs confirmed 200 by a live fetch on 2026-09-11 (their HTML is the fixtures).
LOLIN_VERIFIED_URLS = {
    "lolin-c3-mini": "https://www.wemos.cc/en/latest/c3/c3_mini.html",
    "lolin-d32": "https://www.wemos.cc/en/latest/d32/d32.html",
    "lolin-d32-pro": "https://www.wemos.cc/en/latest/d32/d32_pro.html",
    "lolin-s2-mini": "https://www.wemos.cc/en/latest/s2/s2_mini.html",
    "lolin-s3": "https://www.wemos.cc/en/latest/s3/s3.html",
    "lolin-s3-mini": "https://www.wemos.cc/en/latest/s3/s3_mini.html",
}

# All 6 lolin board ids the resolver must cover (the data/boards/lolin/* dirs).
LOLIN_ALL_BOARDS = list(LOLIN_VERIFIED_URLS)
LOLIN_SOC = {
    "lolin-c3-mini": "esp32-c3", "lolin-d32": "esp32", "lolin-d32-pro": "esp32",
    "lolin-s2-mini": "esp32-s2", "lolin-s3": "esp32-s3", "lolin-s3-mini": "esp32-s3",
}


def test_lolin_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained a "lolin" entry, and its deterministic rule returns the EXACT
    # live-verified www.wemos.cc URL (best-first) for every one of the 6 boards.
    assert "lolin" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["lolin"]
    for bid, url in LOLIN_VERIFIED_URLS.items():
        cands = resolver(bid, LOLIN_SOC[bid])
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_lolin_resolver_covers_all_6_boards_on_wemos_domain():
    # (b) every one of the 6 lolin boards resolves to a www.wemos.cc URL — no board falls
    # through uncovered (0 → 6 boards this slice).
    resolver = bb.VENDOR_DOC_RESOLVERS["lolin"]
    for bid in LOLIN_ALL_BOARDS:
        cands = resolver(bid, LOLIN_SOC[bid])
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://www.wemos.cc/en/latest/"), cands[0]
        assert cands[0].endswith(".html"), cands[0]


def test_lolin_resolver_non_lolin_id_returns_empty():
    # (c) the resolver only claims lolin-prefixed ids; an id it doesn't own yields [] (→ that
    # board would be skipped doc-unreachable, never sent to a guessed wemos URL).
    resolver = bb.VENDOR_DOC_RESOLVERS["lolin"]
    assert resolver("esp32-devkitc", "esp32") == []
    assert resolver("heltec-wifi-kit-32-v3", "esp32-s3") == []
    assert resolver("xiao-esp32c3", "esp32-c3") == []


def _lolin_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the lolin resolver's URL for `bid` —
    any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["lolin"](bid, LOLIN_SOC[bid])[0]
    return url, _fetcher({url: _fixture(fixture_name)})


@pytest.mark.parametrize("name", ["lolin-d32", "lolin-d32-pro"])
def test_lolin_usb_serial_grounds_ch340_where_page_names_it(name):
    # (d) the two boards whose doc page states "CH340" ground usb_serial=ch340 (a schema-valid
    # enum value). This is grounded off the page text.
    val = bb.extract_usb_serial(bb._visible_text(_fixture(name)))
    assert val == "ch340", f"{name} → {val!r}"


@pytest.mark.parametrize("name", ["lolin-c3-mini", "lolin-s2-mini", "lolin-s3", "lolin-s3-mini"])
def test_lolin_usb_serial_omitted_when_page_names_no_bridge(name):
    # (e) CRITICAL cite-or-omit: these doc pages do NOT name a bridge chip, so usb_serial must
    # stay None — never a guessed flash-critical write.
    assert bb.extract_usb_serial(bb._visible_text(_fixture(name))) is None


@pytest.mark.parametrize("name", list(LOLIN_VERIFIED_URLS))
def test_lolin_download_mode_and_images_omitted_on_real_pages(name):
    # (f) CRITICAL cite-or-omit: on ALL 6 REAL lolin pages the download_mode and image
    # heuristics correctly return None (no Boot+Reset firmware-download sentence; no groundable
    # og:image / filename), so those fields stay omitted.
    raw = _fixture(name)
    assert bb.extract_download_mode(bb._visible_text(raw)) is None
    assert bb.extract_images(raw, "https://www.wemos.cc/x") is None


def test_lolin_d32_grounds_getting_started_and_usb_serial(tmp_path):
    # (g) end-to-end on a BARE board: d32's page grounds getting_started = the URL AND
    # usb_serial=ch340 (the page names it); download_mode + images are OMITTED.
    bid, soc = "lolin-d32", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="lolin")
    url, fetch = _lolin_fetcher_for(bid, "lolin-d32")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url
    assert entry["written"] == ["usb_serial", "getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "ch340"
    assert "download_mode" not in fm
    assert "images" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url and cited["getting_started"]["verified"] == TODAY
    assert cited["usb_serial"]["url"] == url and cited["usb_serial"]["verified"] == TODAY


def test_lolin_s3_grounds_getting_started_only(tmp_path):
    # (h) end-to-end on a BARE board: s3's page names no bridge → usb_serial is OMITTED alongside
    # download_mode + images; only getting_started grounds (honest 0→1).
    bid, soc = "lolin-s3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="lolin")
    url, fetch = _lolin_fetcher_for(bid, "lolin-s3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "usb_serial", "images"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert "usb_serial" not in fm


def test_lolin_grounds_getting_started_when_usb_serial_already_filled(tmp_path):
    # (i) mirrors the REAL data (d32 usb_serial already present from other sources): backfill
    # writes ONLY getting_started, never touching the pre-filled usb_serial. This is the true
    # per-board coverage delta on a real run (0→1: getting_started; download_mode + images
    # omitted).
    bid, soc = "lolin-d32", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="lolin", extra_fields="usb_serial: ch340\n")
    url, fetch = _lolin_fetcher_for(bid, "lolin-d32")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "images"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "ch340"            # pre-filled, untouched
    usb_sources = [s for s in fm["sources"] if s["field"] == "usb_serial"]
    assert usb_sources == []                       # no new citation appended for a filled field


def test_lolin_board_404_skipped_cleanly(tmp_path):
    # (j) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid, soc = "lolin-c3-mini", "esp32-c3"
    path = _write_board(tmp_path, bid, soc, brand="lolin")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ──────────────────────────────────────────────────────────────────────────────
# SLICE 8 — unexpected-maker vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 8).
# ──────────────────────────────────────────────────────────────────────────────
# Registers the "unexpected-maker" resolver on esp32s3.com so board_backfill reaches the 4
# Unexpected Maker ESP32-S3 boards (um-tinys3, um-pros3, um-nanos3, um-feathers3). LIKE heltec /
# lolin, the doc URL is a clean DETERMINISTIC rule (verified live 2026-09-11 to yield all 4 real
# doc pages, 200, each describing the correct ESP32-S3 board with a USB-C connector): strip the
# `um-` prefix → `<name>`, then `https://esp32s3.com/<name>.html`. All 4 ids fit the rule exactly,
# so no board is hardcoded (a future non-fitting board would go in a small verified override map,
# never forced onto the rule). The resolver only claims `um-`-prefixed ids; any other id yields []
# (→ skipped doc-unreachable, never a guessed URL). The HTML is saved as the Slice-8 fixtures.
#
# NOTE the frontmatter `brand` for these boards is exactly `unexpected-maker` (confirmed on the
# real data/boards/unexpected-maker/* files), so the registry key is `unexpected-maker`.
#
# EMPIRICAL grounding (measured on the REAL fetched doc pages under fixtures/):
#   * getting_started — grounds for ALL 4 (the resolved 200 doc page IS the link).
#   * usb_serial      — grounds for ALL 4: every page states "Native USB + USB Serial JTAG" →
#                       native-usb-serial-jtag (a schema-valid enum value, grounded off the page
#                       text). NOTE the pages also mention USB-C, but usb_connector is not a
#                       BACKFILL_FIELDS field, so it is never written here.
#   * download_mode   — OMITTED on all 4: no Boot+Reset "Firmware Download mode" sentence.
#   * images          — GATED OFF for the whole vendor (VENDOR_UNGROUNDABLE_FIELDS). The default
#                       espressif filename heuristic is UNRELIABLE on esp32s3.com: the per-board
#                       pinout diagrams are `images/pins_<board>.jpg` (which the heuristic's
#                       pinout regex does NOT match), while a cross-linked generic
#                       `images/tiny_pinout_matrix.jpg` DOES match — and the nanos3 page carries
#                       BOTH its own nanos3_pinout_matrix.jpg AND tiny_pinout_matrix.jpg, so the
#                       heuristic grounds the WRONG (tinys3) pinout first in DOM order. A wrong
#                       wiring diagram can fry a board, so images is excluded from extraction for
#                       unexpected-maker and honestly reported OMITTED (never written).
# Honest per-board delta on a real run: usb_serial + getting_started grounded, download_mode +
# images explicitly omitted.

# The 4 URLs confirmed 200 by a live fetch on 2026-09-11 (their HTML is the Slice-8 fixtures).
UM_VERIFIED_URLS = {
    "um-tinys3": "https://esp32s3.com/tinys3.html",
    "um-pros3": "https://esp32s3.com/pros3.html",
    "um-nanos3": "https://esp32s3.com/nanos3.html",
    "um-feathers3": "https://esp32s3.com/feathers3.html",
}

# All 4 unexpected-maker board ids the resolver must cover (data/boards/unexpected-maker/* dirs).
UM_ALL_BOARDS = list(UM_VERIFIED_URLS)
UM_SOC = {bid: "esp32-s3" for bid in UM_VERIFIED_URLS}   # all four are ESP32-S3


def test_um_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained an "unexpected-maker" entry (the exact frontmatter brand), and its
    # deterministic rule returns the EXACT live-verified esp32s3.com URL (best-first) for all 4.
    assert "unexpected-maker" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["unexpected-maker"]
    for bid, url in UM_VERIFIED_URLS.items():
        cands = resolver(bid, UM_SOC[bid])
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_um_resolver_covers_all_4_boards_on_esp32s3_domain():
    # (b) every one of the 4 unexpected-maker boards resolves to an esp32s3.com URL — no board
    # falls through uncovered (0 → 4 boards this slice).
    resolver = bb.VENDOR_DOC_RESOLVERS["unexpected-maker"]
    for bid in UM_ALL_BOARDS:
        cands = resolver(bid, UM_SOC[bid])
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://esp32s3.com/"), cands[0]
        assert cands[0].endswith(".html"), cands[0]


def test_um_resolver_non_um_id_returns_empty():
    # (c) the resolver only claims um-prefixed ids; an id it doesn't own yields [] (→ that board
    # would be skipped doc-unreachable, never sent to a guessed esp32s3.com URL).
    resolver = bb.VENDOR_DOC_RESOLVERS["unexpected-maker"]
    assert resolver("esp32-devkitc", "esp32") == []
    assert resolver("heltec-wifi-kit-32-v3", "esp32-s3") == []
    assert resolver("lolin-s3", "esp32-s3") == []


def _um_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the unexpected-maker resolver's URL for
    `bid` — any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["unexpected-maker"](bid, UM_SOC[bid])[0]
    return url, _fetcher({url: _fixture(fixture_name)})


@pytest.mark.parametrize("name", list(UM_VERIFIED_URLS))
def test_um_usb_serial_grounds_native_jtag_on_every_page(name):
    # (d) every real esp32s3.com page states "Native USB + USB Serial JTAG", so usb_serial
    # grounds to native-usb-serial-jtag (a schema-valid enum value), grounded off the page text.
    val = bb.extract_usb_serial(bb._visible_text(_fixture(name)))
    assert val == "native-usb-serial-jtag", f"{name} → {val!r}"


@pytest.mark.parametrize("name", list(UM_VERIFIED_URLS))
def test_um_download_mode_omitted_on_real_pages(name):
    # (e) CRITICAL cite-or-omit: on ALL 4 REAL pages the download_mode heuristic returns None
    # (no Boot+Reset "Firmware Download mode" sentence), so download_mode stays omitted.
    assert bb.extract_download_mode(bb._visible_text(_fixture(name))) is None


def test_um_images_gated_off_because_espressif_heuristic_misgrounds():
    # (f) CRITICAL wiring-safety: the default espressif filename heuristic is UNRELIABLE on
    # esp32s3.com. The nanos3 page carries BOTH its own nanos3_pinout_matrix.jpg AND a
    # cross-linked tiny_pinout_matrix.jpg; the heuristic grounds the WRONG (tinys3) pinout first
    # in DOM order. A wrong wiring diagram can fry a board, so images is gated OFF for the whole
    # vendor. Proven here: the raw heuristic mis-grounds AND the gate is registered.
    wrong = bb.extract_images(_fixture("um-nanos3"), "https://esp32s3.com/nanos3.html")
    assert wrong is not None and "tiny_pinout_matrix" in wrong.get("pinout", "")   # the trap
    assert "images" in bb.VENDOR_UNGROUNDABLE_FIELDS["unexpected-maker"]


def test_um_tinys3_grounds_usb_serial_and_getting_started(tmp_path):
    # (g) end-to-end on a BARE board: tinys3's page grounds usb_serial=native-usb-serial-jtag AND
    # getting_started = the URL; download_mode + images are OMITTED (images gated off).
    bid, soc = "um-tinys3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="unexpected-maker")
    url, fetch = _um_fetcher_for(bid, "um-tinys3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url
    assert entry["written"] == ["usb_serial", "getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert "download_mode" not in fm
    assert "images" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url and cited["getting_started"]["verified"] == TODAY
    assert cited["usb_serial"]["url"] == url and cited["usb_serial"]["verified"] == TODAY


def test_um_nanos3_never_writes_the_wrong_pinout(tmp_path):
    # (h) end-to-end on the trap board: nanos3 must NEVER get the mis-grounded tinys3 pinout.
    # The vendor gate excludes images from extraction, so it is OMITTED (not written), while
    # usb_serial + getting_started still ground honestly.
    bid, soc = "um-nanos3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="unexpected-maker")
    url, fetch = _um_fetcher_for(bid, "um-nanos3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["usb_serial", "getting_started"]
    assert "images" in entry["omitted"]
    fm, _ = bb.parse_frontmatter(path)
    assert "images" not in fm
    assert fm["usb_serial"] == "native-usb-serial-jtag"


def test_um_grounds_getting_started_when_usb_serial_already_filled(tmp_path):
    # (i) mirrors a real run where usb_serial is already present: backfill writes ONLY
    # getting_started, never touching the pre-filled usb_serial; download_mode + images omitted.
    bid, soc = "um-feathers3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="unexpected-maker",
                        extra_fields="usb_serial: native-usb-serial-jtag\n")
    url, fetch = _um_fetcher_for(bid, "um-feathers3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "images"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "native-usb-serial-jtag"    # pre-filled, untouched
    usb_sources = [s for s in fm["sources"] if s["field"] == "usb_serial"]
    assert usb_sources == []                                # no new citation for a filled field


def test_um_board_404_skipped_cleanly(tmp_path):
    # (j) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid, soc = "um-pros3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="unexpected-maker")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ──────────────────────────────────────────────────────────────────────────────
# SLICE 9 — dfrobot vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 9).
# ──────────────────────────────────────────────────────────────────────────────
# Registers the "dfrobot" resolver on wiki.dfrobot.com so board_backfill reaches the 6 DFRobot
# ESP32 boards. Each board's official wiki page is wiki.dfrobot.com/dfrXXXX, where dfrXXXX is
# the product SKU. UNLIKE heltec/lolin's deterministic rule, the SKU is NOT derivable from the
# board id (beetle-esp32-c3 → dfr0868, beetle-esp32-c6 → dfr1117 — adjacent boards, non-adjacent
# SKUs), so — exactly like the seeed SEEED_DOC_URLS map — this resolver is a small EXPLICIT
# per-board map. Only URLs CONFIRMED live=200 on 2026-09-11 (each page's <title> content-matches
# OUR board record — dfr0975 is the S3 N16R8 16MB/8MB-PSRAM variant, NOT dfr1145 the N4 4MB
# variant; dfr0478 is the original FireBeetle ESP32, not a "FireBeetle 2") are ever emitted —
# never an invented/guessed SKU. The resolver claims only the 6 mapped ids; any other id yields
# [] (→ skipped doc-unreachable, never a guessed URL). The frontmatter `brand` for these boards
# is exactly `dfrobot`. The HTML is saved as the Slice-9 fixtures.
#
# EMPIRICAL grounding (measured on the REAL fetched wiki pages under fixtures/):
#   * getting_started — grounds for ALL 6 (the resolved 200 doc page IS the link).
#   * usb_serial      — grounds ch340 only where the page NAMES the bridge in product prose
#                       (firebeetle-2-esp32-e "uses the CH340 serial chip"; firebeetle-esp32
#                       "installing the CH340 driver ... for FireBeetle ESP32"). The other four
#                       (beetle C3/C6, firebeetle-2 C6/S3) name NO bridge in a groundable form —
#                       their pinout tables label a JTAG *debug pin*, not the USB-Serial-JTAG
#                       flashing peripheral — so usb_serial is OMITTED (cite-or-omit). NOTE the
#                       real data/boards/dfrobot/firebeetle-esp32 file already carries
#                       usb_serial: ch340, so on a real run only getting_started is written for it.
#   * download_mode   — OMITTED on all 6: no Boot+Reset "Firmware Download mode" sentence.
#   * images          — OMITTED on all 6: the espressif filename heuristic (the registry default
#                       for dfrobot — no dedicated dfrobot image extractor this slice) finds
#                       nothing, so no gate is needed (unlike lilygo/unexpected-maker).
# So this slice grounds getting_started for all 6 (+ usb_serial=ch340 for the 2 that name it) —
# an honest 0→1 (or 0→2) per board.

# The 6 URLs confirmed 200 (no redirect) by a live fetch on 2026-09-11 (their HTML is fixtures).
# The SKU per board id is NOT derivable — an explicit human-verified map, like seeed.
DFROBOT_VERIFIED_URLS = {
    "beetle-esp32-c3": "https://wiki.dfrobot.com/dfr0868",
    "beetle-esp32-c6": "https://wiki.dfrobot.com/dfr1117",
    "firebeetle-2-esp32-c6": "https://wiki.dfrobot.com/dfr1075",
    "firebeetle-2-esp32-e": "https://wiki.dfrobot.com/dfr0654",
    "firebeetle-2-esp32-s3": "https://wiki.dfrobot.com/dfr0975",
    "firebeetle-esp32": "https://wiki.dfrobot.com/dfr0478",
}

# All 6 dfrobot board ids the resolver must cover (the data/boards/dfrobot/* dirs).
DFROBOT_ALL_BOARDS = list(DFROBOT_VERIFIED_URLS)
DFROBOT_SOC = {
    "beetle-esp32-c3": "esp32-c3", "beetle-esp32-c6": "esp32-c6",
    "firebeetle-2-esp32-c6": "esp32-c6", "firebeetle-2-esp32-e": "esp32",
    "firebeetle-2-esp32-s3": "esp32-s3", "firebeetle-esp32": "esp32",
}
# Boards whose wiki page NAMES the ch340 bridge in product prose (usb_serial grounds).
DFROBOT_CH340_BOARDS = ["firebeetle-2-esp32-e", "firebeetle-esp32"]
# Boards whose page names no groundable bridge (usb_serial OMITTED).
DFROBOT_NO_BRIDGE_BOARDS = ["beetle-esp32-c3", "beetle-esp32-c6",
                            "firebeetle-2-esp32-c6", "firebeetle-2-esp32-s3"]


def test_dfrobot_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained a "dfrobot" entry, and it returns the EXACT live-verified
    # wiki.dfrobot.com/dfrXXXX URL (best-first) for every one of the 6 boards — from the
    # explicit SKU map (the SKU is not derivable from the board id, never a guessed variant).
    assert "dfrobot" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["dfrobot"]
    for bid, url in DFROBOT_VERIFIED_URLS.items():
        cands = resolver(bid, DFROBOT_SOC[bid])
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_dfrobot_resolver_covers_all_6_boards_on_wiki_domain():
    # (b) every one of the 6 dfrobot boards resolves to a wiki.dfrobot.com URL — no board
    # falls through uncovered (0 → 6 boards this slice).
    resolver = bb.VENDOR_DOC_RESOLVERS["dfrobot"]
    for bid in DFROBOT_ALL_BOARDS:
        cands = resolver(bid, DFROBOT_SOC[bid])
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://wiki.dfrobot.com/"), cands[0]


def test_dfrobot_resolver_unmapped_id_returns_empty():
    # (c) the resolver only claims the 6 mapped ids; an id it doesn't own — including a
    # plausible-but-unmapped dfrobot id — yields [] (→ skipped doc-unreachable, never a
    # guessed SKU URL). SKU numbers are NOT derivable, so nothing is ever constructed.
    resolver = bb.VENDOR_DOC_RESOLVERS["dfrobot"]
    assert resolver("esp32-devkitc", "esp32") == []
    assert resolver("heltec-wifi-kit-32-v3", "esp32-s3") == []
    assert resolver("beetle-esp32-c2", "esp32-c2") == []  # a plausible-but-unmapped dfrobot id


def _dfrobot_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the dfrobot resolver's URL for `bid` —
    any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["dfrobot"](bid, DFROBOT_SOC[bid])[0]
    return url, _fetcher({url: _fixture(fixture_name)})


@pytest.mark.parametrize("name", DFROBOT_CH340_BOARDS)
def test_dfrobot_usb_serial_grounds_ch340_where_page_names_it(name):
    # (d) usb_serial grounds ch340 on the 2 pages that name it in product prose.
    val = bb.extract_usb_serial(bb._visible_text(_fixture(name)))
    assert val == "ch340", name


@pytest.mark.parametrize("name", DFROBOT_NO_BRIDGE_BOARDS)
def test_dfrobot_usb_serial_omitted_when_page_names_no_bridge(name):
    # (e) CRITICAL cite-or-omit: the four pages that name no bridge (only a JTAG debug pin)
    # yield None — usb_serial stays OMITTED, never a false-positive flash-critical write.
    assert bb.extract_usb_serial(bb._visible_text(_fixture(name))) is None


@pytest.mark.parametrize("name", list(DFROBOT_VERIFIED_URLS))
def test_dfrobot_download_mode_and_images_omitted_on_real_pages(name):
    # (f) CRITICAL cite-or-omit: on ALL 6 REAL dfrobot pages the download_mode and image
    # heuristics return None (nothing groundable) — those fields stay OMITTED. (No image
    # gate is needed: the default heuristic false-positives on none of the 6 pages.)
    raw = _fixture(name)
    assert bb.extract_download_mode(bb._visible_text(raw)) is None
    assert bb.extract_images(raw, "https://wiki.dfrobot.com/x") is None


def test_dfrobot_firebeetle_2_e_grounds_getting_started_and_usb_serial(tmp_path):
    # (g) end-to-end: firebeetle-2-esp32-e grounds getting_started = the resolved URL AND
    # usb_serial = ch340 (the page names it), each cited; download_mode + images OMITTED.
    bid, soc = "firebeetle-2-esp32-e", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="dfrobot")
    url, fetch = _dfrobot_fetcher_for(bid, bid)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url == DFROBOT_VERIFIED_URLS[bid]
    assert set(entry["written"]) == {"getting_started", "usb_serial"}
    assert set(entry["omitted"]) == {"download_mode", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "ch340"
    assert "download_mode" not in fm
    assert "images" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url
    assert cited["usb_serial"]["url"] == url
    assert cited["usb_serial"]["verified"] == TODAY


@pytest.mark.parametrize("name", DFROBOT_NO_BRIDGE_BOARDS)
def test_dfrobot_grounds_getting_started_only(name, tmp_path):
    # (h) end-to-end on a bare board: each no-bridge page grounds getting_started = the
    # resolved URL and NOTHING else (usb_serial + download_mode + images OMITTED). Honest 0→1.
    path = _write_board(tmp_path, name, DFROBOT_SOC[name], brand="dfrobot")
    url, fetch = _dfrobot_fetcher_for(name, name)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url == DFROBOT_VERIFIED_URLS[name]
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "usb_serial", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert "usb_serial" not in fm
    assert "download_mode" not in fm
    assert "images" not in fm


def test_dfrobot_grounds_getting_started_when_usb_serial_already_filled(tmp_path):
    # (i) mirrors the real firebeetle-esp32 record (usb_serial: ch340 already present): backfill
    # writes ONLY getting_started, never touching the pre-filled usb_serial; download_mode +
    # images omitted. (The page DOES name ch340, but the field is already filled → not rewritten.)
    bid, soc = "firebeetle-esp32", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="dfrobot", extra_fields="usb_serial: ch340\n")
    url, fetch = _dfrobot_fetcher_for(bid, bid)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "images"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "ch340"                      # pre-filled, untouched
    usb_sources = [s for s in fm["sources"] if s["field"] == "usb_serial"]
    assert usb_sources == []                                # no new citation for a filled field


def test_dfrobot_board_404_skipped_cleanly(tmp_path):
    # (j) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid, soc = "beetle-esp32-c3", "esp32-c3"
    path = _write_board(tmp_path, bid, soc, brand="dfrobot")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ──────────────────────────────────────────────────────────────────────────────
# SLICE 10 — sparkfun vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 10).
# ──────────────────────────────────────────────────────────────────────────────
# Registers the "sparkfun" resolver on learn.sparkfun.com so board_backfill reaches the 5
# SparkFun ESP32 boards. Each board's official page is a learn.sparkfun.com hookup guide whose
# slug is NOT derivable from the board id (sparkfun-esp32-thing → esp32-thing-hookup-guide, but
# sparkfun-thing-plus-esp32-s2-wroom → esp32-s2-thing-plus-hookup-guide — the words reorder and
# the -wroom suffix drops), so — exactly like the seeed/dfrobot maps — this resolver is a small
# EXPLICIT per-board map. Only URLs CONFIRMED live=200 (content-matched to OUR board record) are
# ever emitted — never a guessed slug. The resolver claims only the 5 mapped ids; any other id
# yields [] (→ skipped doc-unreachable, never a guessed URL). The frontmatter `brand` for these
# boards is exactly `sparkfun`. The HTML is saved as the Slice-10 fixtures.
#
# EMPIRICAL grounding (measured on the REAL fetched hookup-guide pages under fixtures/):
#   * getting_started — grounds for ALL 5 (the resolved 200 doc page IS the link).
#   * usb_serial      — grounds ch340 only where the page NAMES the bridge in product prose
#                       (iot-redboard-esp32 names the CH340). The other four name no bridge in a
#                       groundable form — esp32-thing / micromod / s2-wroom name none, and
#                       thing-plus-esp32-wroom names only the USB-C *connector* (not a bridge
#                       chip enum) — so usb_serial is OMITTED there (cite-or-omit). NOTE the real
#                       data/boards/sparkfun/sparkfun-thing-plus-esp32-wroom file already carries
#                       usb_serial: ch340, so on a real run it is never rewritten.
#   * download_mode   — grounds AUTO only on thing-plus-esp32-wroom, whose page states in prose
#                       that the board carries an "auto-reset circuit" (bound to serial upload) —
#                       a citeable auto claim. The other four name no download-mode sequence →
#                       OMITTED (cite-or-omit; a wrong step can brick a board).
#   * images          — OMITTED on all 5: the espressif filename heuristic (the registry default
#                       for sparkfun — no dedicated sparkfun image extractor this slice) finds
#                       nothing, so no gate is needed (unlike lilygo/unexpected-maker).
# So this slice grounds getting_started for all 5 (+ usb_serial=ch340 for iot-redboard,
# + download_mode=auto for thing-plus-esp32-wroom) — an honest 0→1 (or 0→2) per board.

# The 5 URLs confirmed 200 (content-matched) by a live fetch (their HTML is the fixtures).
# The hookup-guide slug per board id is NOT derivable — an explicit human-verified map.
SPARKFUN_VERIFIED_URLS = {
    "sparkfun-esp32-thing": "https://learn.sparkfun.com/tutorials/esp32-thing-hookup-guide",
    "sparkfun-thing-plus-esp32-wroom":
        "https://learn.sparkfun.com/tutorials/esp32-thing-plus-hookup-guide",
    "sparkfun-micromod-esp32-processor":
        "https://learn.sparkfun.com/tutorials/micromod-esp32-processor-board-hookup-guide",
    "sparkfun-thing-plus-esp32-s2-wroom":
        "https://learn.sparkfun.com/tutorials/esp32-s2-thing-plus-hookup-guide",
    "sparkfun-iot-redboard-esp32":
        "https://learn.sparkfun.com/tutorials/iot-redboard-esp32-development-board-hookup-guide",
}

# All 5 sparkfun board ids the resolver must cover (the data/boards/sparkfun/* dirs).
SPARKFUN_ALL_BOARDS = list(SPARKFUN_VERIFIED_URLS)
SPARKFUN_SOC = {
    "sparkfun-esp32-thing": "esp32",
    "sparkfun-thing-plus-esp32-wroom": "esp32",
    "sparkfun-micromod-esp32-processor": "esp32",
    "sparkfun-thing-plus-esp32-s2-wroom": "esp32-s2",
    "sparkfun-iot-redboard-esp32": "esp32",
}
# The only board whose page NAMES the ch340 bridge in product prose (usb_serial grounds).
SPARKFUN_CH340_BOARDS = ["sparkfun-iot-redboard-esp32"]
# Boards whose page names no groundable bridge (usb_serial OMITTED — s2-wroom is native, and
# thing-plus-esp32-wroom names only the USB-C connector, not a bridge chip enum).
SPARKFUN_NO_BRIDGE_BOARDS = ["sparkfun-esp32-thing", "sparkfun-thing-plus-esp32-wroom",
                             "sparkfun-micromod-esp32-processor",
                             "sparkfun-thing-plus-esp32-s2-wroom"]
# The only board whose page states an auto-reset circuit (download_mode grounds auto).
SPARKFUN_AUTO_DOWNLOAD_BOARDS = ["sparkfun-thing-plus-esp32-wroom"]


def test_sparkfun_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained a "sparkfun" entry, and it returns the EXACT live-verified
    # learn.sparkfun.com hookup-guide URL (best-first) for every one of the 5 boards — from the
    # explicit slug map (the slug is not derivable from the board id, never a guessed variant).
    assert "sparkfun" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["sparkfun"]
    for bid, url in SPARKFUN_VERIFIED_URLS.items():
        cands = resolver(bid, SPARKFUN_SOC[bid])
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_sparkfun_resolver_covers_all_5_boards_on_learn_domain():
    # (b) every one of the 5 sparkfun boards resolves to a learn.sparkfun.com URL — no board
    # falls through uncovered (0 → 5 boards this slice).
    resolver = bb.VENDOR_DOC_RESOLVERS["sparkfun"]
    for bid in SPARKFUN_ALL_BOARDS:
        cands = resolver(bid, SPARKFUN_SOC[bid])
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://learn.sparkfun.com/tutorials/"), cands[0]


def test_sparkfun_resolver_unmapped_id_returns_empty():
    # (c) the resolver only claims the 5 mapped ids; an id it doesn't own — including a
    # plausible-but-unmapped sparkfun id — yields [] (→ skipped doc-unreachable, never a
    # guessed slug URL). Hookup-guide slugs are NOT derivable, so nothing is ever constructed.
    resolver = bb.VENDOR_DOC_RESOLVERS["sparkfun"]
    assert resolver("esp32-devkitc", "esp32") == []
    assert resolver("heltec-wifi-kit-32-v3", "esp32-s3") == []
    assert resolver("sparkfun-thing-plus-esp32-c6", "esp32-c6") == []  # plausible-but-unmapped


def _sparkfun_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the sparkfun resolver's URL for `bid` —
    any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["sparkfun"](bid, SPARKFUN_SOC[bid])[0]
    return url, _fetcher({url: _fixture(fixture_name)})


@pytest.mark.parametrize("name", SPARKFUN_CH340_BOARDS)
def test_sparkfun_usb_serial_grounds_ch340_where_page_names_it(name):
    # (d) usb_serial grounds ch340 on the one page (iot-redboard) that names it in product prose.
    val = bb.extract_usb_serial(bb._visible_text(_fixture(name)))
    assert val == "ch340", name


@pytest.mark.parametrize("name", SPARKFUN_NO_BRIDGE_BOARDS)
def test_sparkfun_usb_serial_omitted_when_page_names_no_bridge(name):
    # (e) CRITICAL cite-or-omit: the four pages that name no bridge chip (thing-plus-esp32-wroom
    # names only the USB-C connector, s2-wroom is native, esp32-thing/micromod name none) yield
    # None — usb_serial stays OMITTED, never a false-positive flash-critical write.
    assert bb.extract_usb_serial(bb._visible_text(_fixture(name))) is None


@pytest.mark.parametrize("name", SPARKFUN_AUTO_DOWNLOAD_BOARDS)
def test_sparkfun_download_mode_grounds_auto_where_page_states_auto_reset(name):
    # (f) download_mode grounds AUTO on thing-plus-esp32-wroom: its page states the board has an
    # "auto-reset circuit" bound to serial upload — a citeable auto claim (not a guessed step).
    dm = bb.extract_download_mode(bb._visible_text(_fixture(name)))
    assert dm == {"mode": "auto"}, name


@pytest.mark.parametrize("name", list(SPARKFUN_VERIFIED_URLS))
def test_sparkfun_images_and_bare_download_mode_omitted_on_real_pages(name):
    # (g) CRITICAL cite-or-omit: on ALL 5 REAL sparkfun pages the image heuristic returns None
    # (nothing groundable → images OMITTED; no gate needed). download_mode is OMITTED on the four
    # NON-auto-reset boards (only thing-plus-esp32-wroom grounds auto, asserted separately).
    raw = _fixture(name)
    assert bb.extract_images(raw, "https://learn.sparkfun.com/x") is None
    if name not in SPARKFUN_AUTO_DOWNLOAD_BOARDS:
        assert bb.extract_download_mode(bb._visible_text(raw)) is None


def test_sparkfun_iot_redboard_grounds_getting_started_and_usb_serial(tmp_path):
    # (h) end-to-end: iot-redboard-esp32 grounds getting_started = the resolved URL AND
    # usb_serial = ch340 (the page names it), each cited; download_mode + images OMITTED.
    bid, soc = "sparkfun-iot-redboard-esp32", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="sparkfun")
    url, fetch = _sparkfun_fetcher_for(bid, bid)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url == SPARKFUN_VERIFIED_URLS[bid]
    assert set(entry["written"]) == {"getting_started", "usb_serial"}
    assert set(entry["omitted"]) == {"download_mode", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["usb_serial"] == "ch340"
    assert "download_mode" not in fm
    assert "images" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url
    assert cited["usb_serial"]["url"] == url
    assert cited["usb_serial"]["verified"] == TODAY


def test_sparkfun_thing_plus_wroom_grounds_getting_started_and_auto_download(tmp_path):
    # (i) end-to-end: thing-plus-esp32-wroom grounds getting_started = the resolved URL AND
    # download_mode = auto (the page states an auto-reset circuit), each cited; usb_serial is
    # OMITTED (the page names only the USB-C connector, not a bridge chip); images OMITTED.
    bid, soc = "sparkfun-thing-plus-esp32-wroom", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="sparkfun")
    url, fetch = _sparkfun_fetcher_for(bid, bid)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url == SPARKFUN_VERIFIED_URLS[bid]
    assert set(entry["written"]) == {"getting_started", "download_mode"}
    assert set(entry["omitted"]) == {"usb_serial", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["download_mode"] == {"mode": "auto"}
    assert "usb_serial" not in fm
    assert "images" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["download_mode"]["url"] == url


@pytest.mark.parametrize("name", ["sparkfun-esp32-thing", "sparkfun-micromod-esp32-processor",
                                  "sparkfun-thing-plus-esp32-s2-wroom"])
def test_sparkfun_grounds_getting_started_only(name, tmp_path):
    # (j) end-to-end on a bare board: each page that grounds nothing but the URL writes
    # getting_started = the resolved URL and NOTHING else (all other fields OMITTED). Honest 0→1.
    path = _write_board(tmp_path, name, SPARKFUN_SOC[name], brand="sparkfun")
    url, fetch = _sparkfun_fetcher_for(name, name)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url == SPARKFUN_VERIFIED_URLS[name]
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "usb_serial", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert "usb_serial" not in fm
    assert "download_mode" not in fm
    assert "images" not in fm


def test_sparkfun_grounds_getting_started_when_usb_serial_already_filled(tmp_path):
    # (k) mirrors the real thing-plus-esp32-wroom record (usb_serial: ch340 already present):
    # backfill writes getting_started + download_mode (auto), never touching the pre-filled
    # usb_serial; images omitted. (The page names only USB-C anyway → usb_serial not re-derived.)
    bid, soc = "sparkfun-thing-plus-esp32-wroom", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="sparkfun", extra_fields="usb_serial: ch340\n")
    url, fetch = _sparkfun_fetcher_for(bid, bid)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert set(entry["written"]) == {"getting_started", "download_mode"}
    assert set(entry["omitted"]) == {"images"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["download_mode"] == {"mode": "auto"}
    assert fm["usb_serial"] == "ch340"                      # pre-filled, untouched
    usb_sources = [s for s in fm["sources"] if s["field"] == "usb_serial"]
    assert usb_sources == []                                # no new citation for a filled field


def test_sparkfun_board_404_skipped_cleanly(tmp_path):
    # (l) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid, soc = "sparkfun-esp32-thing", "esp32"
    path = _write_board(tmp_path, bid, soc, brand="sparkfun")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ──────────────────────────────────────────────────────────────────────────────
# SLICE 11 — freenove vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 11).
# ──────────────────────────────────────────────────────────────────────────────
# Registers the "freenove" resolver on docs.freenove.com so board_backfill reaches the 3
# Freenove ESP32-S3 Display boards. ALL THREE FNK0104 variants (a/b/s) share ONE official
# family doc — https://docs.freenove.com/projects/fnk0104/en/latest/ — CONFIRMED live=200 on
# 2026-09-11. The per-variant slugs (fnk0104a/b/s) return 404: only the base fnk0104 doc
# exists (it is the ESP32-S3 Display family doc that covers all three variants). So — exactly
# like the seeed/dfrobot/sparkfun maps — this resolver is a small EXPLICIT per-board map, all
# three ids pointing at the ONE verified family-doc URL; never a guessed per-variant slug. The
# resolver claims only the 3 mapped ids; any other id yields [] (→ skipped doc-unreachable,
# never a guessed URL). The frontmatter `brand` for these boards is exactly `freenove`. The
# HTML (identical for all 3, since they cite the same source) is saved as the Slice-11 fixtures.
#
# EMPIRICAL grounding (measured on the REAL fetched family-doc page under fixtures/):
#   * getting_started — grounds for ALL 3 (the resolved 200 doc page IS the link).
#   * usb_serial      — OMITTED on all 3: the fnk0104 landing page is a Sphinx toctree index
#                       whose visible text names NO bridge chip in a groundable form (a "USB_Serial"
#                       project title is not a chip enum), so extract_usb_serial returns None
#                       (cite-or-omit — never a false-positive flash-critical write).
#   * download_mode   — OMITTED on all 3: the index page states no Boot/Reset download sequence.
#   * images          — OMITTED on all 3: the espressif filename heuristic (the registry default
#                       for freenove — no dedicated freenove image extractor) finds nothing, so no
#                       gate is needed (unlike lilygo/unexpected-maker).
# So this slice grounds getting_started for all 3 — an honest 0→1 per board.

# The ONE family-doc URL confirmed 200 (all 3 variant slugs 404 → only the base doc exists).
FREENOVE_FAMILY_DOC = "https://docs.freenove.com/projects/fnk0104/en/latest/"
# All 3 freenove board ids the resolver must cover (the data/boards/freenove/* dirs). Every one
# maps to the SAME family doc (an explicit map, mirroring dfrobot/sparkfun — never a guess).
FREENOVE_VERIFIED_URLS = {
    "freenove-fnk0104a": FREENOVE_FAMILY_DOC,
    "freenove-fnk0104b": FREENOVE_FAMILY_DOC,
    "freenove-fnk0104s": FREENOVE_FAMILY_DOC,
}
FREENOVE_ALL_BOARDS = list(FREENOVE_VERIFIED_URLS)
FREENOVE_SOC = {bid: "esp32-s3" for bid in FREENOVE_ALL_BOARDS}


def test_freenove_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained a "freenove" entry, and it returns the EXACT live-verified
    # docs.freenove.com family-doc URL (best-first) for every one of the 3 variant ids — from
    # the explicit map (the per-variant slugs 404, so only the base doc is ever emitted).
    assert "freenove" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["freenove"]
    for bid, url in FREENOVE_VERIFIED_URLS.items():
        cands = resolver(bid, FREENOVE_SOC[bid])
        assert cands[0] == url, f"{bid} → {cands[0]!r} != {url!r}"


def test_freenove_resolver_all_variants_share_one_family_doc():
    # (b) all 3 FNK0104 variants resolve to the SAME single family doc on docs.freenove.com —
    # no board falls through uncovered, and none gets a (404) per-variant slug (0 → 3 boards).
    resolver = bb.VENDOR_DOC_RESOLVERS["freenove"]
    resolved = set()
    for bid in FREENOVE_ALL_BOARDS:
        cands = resolver(bid, FREENOVE_SOC[bid])
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0] == FREENOVE_FAMILY_DOC, cands[0]
        resolved.add(cands[0])
    assert resolved == {FREENOVE_FAMILY_DOC}  # one shared doc, not three per-variant URLs


def test_freenove_resolver_unmapped_id_returns_empty():
    # (c) the resolver only claims the 3 mapped ids; an id it doesn't own — including a
    # plausible-but-unmapped freenove id — yields [] (→ skipped doc-unreachable, never a
    # guessed URL).
    resolver = bb.VENDOR_DOC_RESOLVERS["freenove"]
    assert resolver("esp32-devkitc", "esp32") == []
    assert resolver("heltec-wifi-kit-32-v3", "esp32-s3") == []
    assert resolver("freenove-fnk0104x", "esp32-s3") == []       # plausible-but-unmapped variant
    assert resolver("freenove-fnk0099", "esp32-s3") == []        # plausible-but-unmapped product


def _freenove_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the freenove resolver's URL for `bid` —
    any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["freenove"](bid, FREENOVE_SOC[bid])[0]
    return url, _fetcher({url: _fixture(fixture_name)})


@pytest.mark.parametrize("name", FREENOVE_ALL_BOARDS)
def test_freenove_usb_serial_download_mode_images_omitted_on_real_page(name):
    # (d) CRITICAL cite-or-omit: on the REAL fnk0104 family-doc page (a Sphinx toctree index)
    # usb_serial / download_mode / images are ALL ungroundable — the page names no bridge chip,
    # no download sequence, and no groundable image — so each extractor returns None (OMITTED,
    # never a false-positive write).
    raw = _fixture(name)
    assert bb.extract_usb_serial(bb._visible_text(raw)) is None
    assert bb.extract_download_mode(bb._visible_text(raw)) is None
    assert bb.extract_images(raw, FREENOVE_FAMILY_DOC) is None


@pytest.mark.parametrize("name", FREENOVE_ALL_BOARDS)
def test_freenove_grounds_getting_started_only(name, tmp_path):
    # (e) end-to-end: each variant grounds getting_started = the resolved family-doc URL and
    # NOTHING else (all other fields OMITTED). Honest 0→1 per board.
    path = _write_board(tmp_path, name, FREENOVE_SOC[name], brand="freenove")
    url, fetch = _freenove_fetcher_for(name, name)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url == FREENOVE_VERIFIED_URLS[name]
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "usb_serial", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert "usb_serial" not in fm
    assert "download_mode" not in fm
    assert "images" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url
    assert cited["getting_started"]["verified"] == TODAY


def test_freenove_board_404_skipped_cleanly(tmp_path):
    # (f) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified — never a partial/invented write.
    bid = "freenove-fnk0104a"
    path = _write_board(tmp_path, bid, FREENOVE_SOC[bid], brand="freenove")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ──────────────────────────────────────────────────────────────────────────────
# SLICE 12 — elecrow vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 12).
# ──────────────────────────────────────────────────────────────────────────────
# Registers the "elecrow" resolver on www.elecrow.com/wiki so board_backfill reaches the 1
# Elecrow CrowPanel board. Its official page is an elecrow wiki article whose slug is NOT
# derivable from the board id (elecrow-crowpanel-esp32-s3-579-epaper ->
# CrowPanel_ESP32_E-paper_5.79-inch_HMI_Display), so - exactly like the seeed/dfrobot/
# sparkfun/freenove maps - this resolver is a small EXPLICIT per-board map. Only the URL
# CONFIRMED live=200 (content-matched to OUR board record) is ever emitted - never a guessed
# slug. The resolver claims only the mapped id; any other id yields [] (-> skipped doc-
# unreachable, never a guessed URL). The frontmatter `brand` for this board is exactly
# `elecrow`. The HTML is saved as the Slice-12 fixture.
#
# EMPIRICAL grounding (measured on the REAL fetched wiki page under fixtures/):
#   * getting_started - grounds (the resolved 200 doc page IS the link).
#   * images          - grounds a PINOUT: the page embeds exactly one <img> whose filename and
#                       alt text say "pinout" (ESP32-EPAPER-5.79inch-pinout.webp), and it lives
#                       in THIS board's own asset folder (.../CrowPanel_ESP32_E-paper_5.79-inch_
#                       HMI_Display/...) - the espressif filename heuristic (the registry default
#                       for elecrow) grounds it, high-confidence-or-omit (it is this board's own
#                       diagram, not a cross-board one - a wrong wiring diagram can fry a board).
#   * usb_serial      - OMITTED: the page names no bridge chip in a groundable form (it states
#                       only a "Type-C Interface ... for program flashing", not a chip enum), so
#                       extract_usb_serial returns None (cite-or-omit).
#   * download_mode   - OMITTED: the page states no Boot+Reset download-mode sentence that the
#                       extractor grounds -> None (cite-or-omit; a wrong step can brick a board).
# So this slice grounds getting_started + images(pinout) - an honest 0->2.

ELECROW_VERIFIED_URLS = {
    "elecrow-crowpanel-esp32-s3-579-epaper":
        "https://www.elecrow.com/wiki/CrowPanel_ESP32_E-paper_5.79-inch_HMI_Display.html",
}
ELECROW_ALL_BOARDS = list(ELECROW_VERIFIED_URLS)
ELECROW_SOC = {"elecrow-crowpanel-esp32-s3-579-epaper": "esp32-s3"}
# The one board's own pinout diagram, absolute-resolved against its doc URL.
ELECROW_PINOUT = ("https://www.elecrow.com/wiki/assets/images/"
                  "CrowPanel_ESP32_E-paper_5.79-inch_HMI_Display/ESP32-EPAPER-5.79inch-pinout.webp")


def test_elecrow_resolver_registered_returns_verified_docs_url():
    # (a) the registry gained an "elecrow" entry, and it returns the EXACT live-verified
    # www.elecrow.com/wiki article URL (best-first) for the board - from the explicit map (the
    # slug is not derivable from the board id, never a guessed variant).
    assert "elecrow" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["elecrow"]
    for bid, url in ELECROW_VERIFIED_URLS.items():
        cands = resolver(bid, ELECROW_SOC[bid])
        assert cands[0] == url, f"{bid} -> {cands[0]!r} != {url!r}"


def test_elecrow_resolver_covers_the_board_on_wiki_domain():
    # (b) the board resolves to a www.elecrow.com/wiki URL - it does not fall through uncovered.
    resolver = bb.VENDOR_DOC_RESOLVERS["elecrow"]
    for bid in ELECROW_ALL_BOARDS:
        cands = resolver(bid, ELECROW_SOC[bid])
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://www.elecrow.com/wiki/"), cands[0]


def test_elecrow_resolver_unmapped_id_returns_empty():
    # (c) the resolver only claims the mapped id; an id it doesn't own - including a plausible-
    # but-unmapped elecrow id - yields [] (-> skipped doc-unreachable, never a guessed slug URL).
    resolver = bb.VENDOR_DOC_RESOLVERS["elecrow"]
    assert resolver("esp32-devkitc", "esp32") == []
    assert resolver("heltec-wifi-kit-32-v3", "esp32-s3") == []
    assert resolver("elecrow-crowpanel-esp32-s3-499-epaper", "esp32-s3") == []  # plausible-unmapped


def _elecrow_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the elecrow resolver's URL for `bid` -
    any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["elecrow"](bid, ELECROW_SOC[bid])[0]
    return url, _fetcher({url: _fixture(fixture_name)})


@pytest.mark.parametrize("name", ELECROW_ALL_BOARDS)
def test_elecrow_usb_serial_download_mode_omitted_on_real_page(name):
    # (d) CRITICAL cite-or-omit: on the REAL CrowPanel wiki page usb_serial and download_mode are
    # ungroundable - the page names no bridge chip and states no Boot+Reset download sequence the
    # extractor grounds - so each returns None (OMITTED, never a false-positive flash-critical write).
    raw = _fixture(name)
    assert bb.extract_usb_serial(bb._visible_text(raw)) is None
    assert bb.extract_download_mode(bb._visible_text(raw)) is None


@pytest.mark.parametrize("name", ELECROW_ALL_BOARDS)
def test_elecrow_pinout_image_grounds_this_boards_own_diagram(name):
    # (e) images grounds THIS board's own pinout diagram (filename+alt say "pinout", in the
    # board's own asset folder) - high-confidence-or-omit, never a cross-board diagram.
    raw = _fixture(name)
    imgs = bb.extract_images(raw, ELECROW_VERIFIED_URLS[name])
    assert imgs == {"pinout": ELECROW_PINOUT}, imgs


def test_elecrow_grounds_getting_started_and_pinout(tmp_path):
    # (f) end-to-end: the CrowPanel board grounds getting_started = the resolved URL AND
    # images.pinout = its own diagram, each cited; usb_serial + download_mode OMITTED.
    bid = "elecrow-crowpanel-esp32-s3-579-epaper"
    path = _write_board(tmp_path, bid, ELECROW_SOC[bid], brand="elecrow")
    url, fetch = _elecrow_fetcher_for(bid, bid)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url == ELECROW_VERIFIED_URLS[bid]
    assert set(entry["written"]) == {"getting_started", "images"}
    assert set(entry["omitted"]) == {"download_mode", "usb_serial"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert fm["images"] == {"pinout": ELECROW_PINOUT}
    assert "usb_serial" not in fm
    assert "download_mode" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url
    assert cited["images"]["url"] == url
    assert cited["images"]["verified"] == TODAY


def test_elecrow_board_404_skipped_cleanly(tmp_path):
    # (g) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified - never a partial/invented write.
    bid = "elecrow-crowpanel-esp32-s3-579-epaper"
    path = _write_board(tmp_path, bid, ELECROW_SOC[bid], brand="elecrow")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before


# ──────────────────────────────────────────────────────────────────────────────
# SLICE 13 — waveshare vendor doc resolver (SPEC-board-backfill-vendors.md §Slice 13).
# ──────────────────────────────────────────────────────────────────────────────
# Registers the "waveshare" resolver on docs.waveshare.com so board_backfill reaches the 2
# Waveshare ESP32-S3 boards. Each board's official page is a docs.waveshare.com wiki article
# whose slug is NOT derivable from the board id (waveshare-esp32-s3-rlcd-42 -> ESP32-S3-RLCD-4.2,
# waveshare-esp32-s3-touch-lcd-349 -> ESP32-S3-Touch-LCD-3.49 - the decimal dots come back), so -
# exactly like the seeed/dfrobot/sparkfun/freenove maps - this resolver is a small EXPLICIT
# per-board map. Only URLs CONFIRMED live=200 (content-matched to OUR board record) are ever
# emitted - never a guessed slug. The resolver claims only the 2 mapped ids; any other id yields
# [] (-> skipped doc-unreachable, never a guessed URL). The frontmatter `brand` for these boards
# is exactly `waveshare`. The HTML is saved as the Slice-13 fixtures.
#
# EMPIRICAL grounding (measured on the REAL fetched wiki pages under fixtures/):
#   * getting_started - grounds for BOTH (the resolved 200 doc page IS the link).
#   * download_mode   - GATED OFF for the vendor (VENDOR_UNGROUNDABLE_FIELDS) -> OMITTED for both.
#                       The docs.waveshare.com wiki renders its hardware description as a big
#                       PERIODLESS table/list; _visible_text flattens the whole page into ONE
#                       "sentence" (no ./!/? boundary), which contains the words "boot", "reset"/
#                       "EN" and "download mode" - so extract_download_mode's Espressif manual
#                       branch grabs the WHOLE-PAGE blob as `steps` (a >1000-char fragment), a
#                       structural false-positive on a flash-critical field. That is the lilygo/
#                       unexpected-maker trap at page-structure scale, so download_mode is gated
#                       OFF and honestly reported OMITTED - never a blob write. (RLCD-4.2's real
#                       instruction is even Boot-ONLY - "hold BOOT to power on again to enter
#                       download mode", no Reset - so it isn't the standard Boot+Reset manual
#                       sequence anyway; and neither page yields a clean citeable sentence.)
#   * usb_serial      - OMITTED on both: the pages name no bridge chip in a groundable form (only
#                       a "Type-C Interface ... for program flashing"), so extract_usb_serial -> None.
#   * images          - OMITTED on both: the espressif filename heuristic (the registry default
#                       for waveshare) finds no pinout/photo filename -> None (no gate needed).
# So this slice grounds getting_started for both - an honest 0->1 per board.

WAVESHARE_VERIFIED_URLS = {
    "waveshare-esp32-s3-rlcd-42": "https://docs.waveshare.com/ESP32-S3-RLCD-4.2",
    "waveshare-esp32-s3-touch-lcd-349": "https://docs.waveshare.com/ESP32-S3-Touch-LCD-3.49",
}
WAVESHARE_ALL_BOARDS = list(WAVESHARE_VERIFIED_URLS)
WAVESHARE_SOC = {bid: "esp32-s3" for bid in WAVESHARE_ALL_BOARDS}


def test_waveshare_resolver_registered_returns_verified_docs_urls():
    # (a) the registry gained a "waveshare" entry, and it returns the EXACT live-verified
    # docs.waveshare.com article URL (best-first) for both boards - from the explicit map (the
    # slug is not derivable from the board id, never a guessed variant).
    assert "waveshare" in bb.VENDOR_DOC_RESOLVERS
    resolver = bb.VENDOR_DOC_RESOLVERS["waveshare"]
    for bid, url in WAVESHARE_VERIFIED_URLS.items():
        cands = resolver(bid, WAVESHARE_SOC[bid])
        assert cands[0] == url, f"{bid} -> {cands[0]!r} != {url!r}"


def test_waveshare_resolver_covers_both_boards_on_docs_domain():
    # (b) both waveshare boards resolve to a docs.waveshare.com URL - no board falls through
    # uncovered (0 -> 2 boards this slice).
    resolver = bb.VENDOR_DOC_RESOLVERS["waveshare"]
    for bid in WAVESHARE_ALL_BOARDS:
        cands = resolver(bid, WAVESHARE_SOC[bid])
        assert cands, f"{bid} yielded no candidate URL"
        assert cands[0].startswith("https://docs.waveshare.com/"), cands[0]


def test_waveshare_resolver_unmapped_id_returns_empty():
    # (c) the resolver only claims the 2 mapped ids; an id it doesn't own - including a plausible-
    # but-unmapped waveshare id - yields [] (-> skipped doc-unreachable, never a guessed slug URL).
    resolver = bb.VENDOR_DOC_RESOLVERS["waveshare"]
    assert resolver("esp32-devkitc", "esp32") == []
    assert resolver("heltec-wifi-kit-32-v3", "esp32-s3") == []
    assert resolver("waveshare-esp32-s3-touch-lcd-185", "esp32-s3") == []  # plausible-but-unmapped


def _waveshare_fetcher_for(bid, fixture_name):
    """Fake fetcher that serves the given fixture ONLY at the waveshare resolver's URL for `bid` -
    any other URL 404s (proves resolution lands on the right page)."""
    url = bb.VENDOR_DOC_RESOLVERS["waveshare"](bid, WAVESHARE_SOC[bid])[0]
    return url, _fetcher({url: _fixture(fixture_name)})


@pytest.mark.parametrize("name", WAVESHARE_ALL_BOARDS)
def test_waveshare_download_mode_gated_off_because_page_flattens_to_blob(name):
    # (d) CRITICAL flash-safety: download_mode is GATED OFF for waveshare. Prove WHY: on the REAL
    # periodless wiki page the ungated extractor DOES fire - but only by swallowing the WHOLE PAGE
    # as one "sentence" (a >1000-char blob), a fragment that must never be written as `steps`. The
    # gate excludes the field so it is honestly OMITTED, never that blob.
    dm_blob = bb.extract_download_mode(bb._visible_text(_fixture(name)))
    assert dm_blob is not None and dm_blob["mode"] == "manual"      # the false-positive fires...
    assert len(dm_blob["steps"]) > 1000                            # ...but only as a whole-page blob
    assert "download_mode" in bb.VENDOR_UNGROUNDABLE_FIELDS["waveshare"]  # -> GATED OFF -> OMITTED


@pytest.mark.parametrize("name", WAVESHARE_ALL_BOARDS)
def test_waveshare_usb_serial_and_images_omitted_on_real_page(name):
    # (e) CRITICAL cite-or-omit: on both REAL pages usb_serial names no groundable bridge chip and
    # the image heuristic finds no pinout/photo filename -> each returns None (OMITTED, no gate needed).
    raw = _fixture(name)
    assert bb.extract_usb_serial(bb._visible_text(raw)) is None
    assert bb.extract_images(raw, WAVESHARE_VERIFIED_URLS[name]) is None


@pytest.mark.parametrize("name", WAVESHARE_ALL_BOARDS)
def test_waveshare_grounds_getting_started_only(name, tmp_path):
    # (f) end-to-end: each board grounds getting_started = the resolved URL and NOTHING else
    # (download_mode gated off; usb_serial + images ungroundable -> all OMITTED). Honest 0->1.
    path = _write_board(tmp_path, name, WAVESHARE_SOC[name], brand="waveshare")
    url, fetch = _waveshare_fetcher_for(name, name)
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["url"] == url == WAVESHARE_VERIFIED_URLS[name]
    assert entry["written"] == ["getting_started"]
    assert set(entry["omitted"]) == {"download_mode", "usb_serial", "images"}
    assert entry["partial"] is True

    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert "download_mode" not in fm       # gated off - never the whole-page blob
    assert "usb_serial" not in fm
    assert "images" not in fm
    cited = {s["field"]: s for s in fm["sources"]}
    assert cited["getting_started"]["url"] == url
    assert cited["getting_started"]["verified"] == TODAY


def test_waveshare_board_404_skipped_cleanly(tmp_path):
    # (g) a board whose doc page 404s is SKIPPED doc-unreachable and left byte-for-byte
    # unmodified - never a partial/invented write.
    bid = "waveshare-esp32-s3-rlcd-42"
    path = _write_board(tmp_path, bid, WAVESHARE_SOC[bid], brand="waveshare")
    before = path.read_text()
    entry = bb.backfill_board(path, tmp_path, _fetcher({}), TODAY)  # every URL 404s

    assert entry["status"] == "skipped"
    assert entry["reason"] == "doc-unreachable"
    assert entry["modified"] is False
    assert path.read_text() == before
