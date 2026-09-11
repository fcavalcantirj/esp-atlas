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
    ("esp32-lyrat", "initiates the firmware upload mode"),   # esp-adf phrasing
])
def test_download_mode_manual_extracts_with_exact_cited_steps(name, contains):
    dm = bb.extract_download_mode(bb._visible_text(_fixture(name)))
    assert dm is not None and dm["mode"] == "manual"
    assert contains in dm["steps"]  # the exact sentence quoted from the doc


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
    # (b) a brand with NO registered resolver (waveshare — still unregistered after Slice 4)
    # is skipped with reason "no-resolver" and left byte-for-byte unmodified — the guarantee
    # that a brand without a resolver is never touched.
    bid, soc = "waveshare-esp32-s3-touch", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="waveshare")
    before = path.read_text()

    entry = bb.backfill_board(path, tmp_path, _fetcher({_url(bid, soc): DOC_WITH_MANUAL}), TODAY)

    assert entry["status"] == "skipped"
    assert entry["reason"] == "no-resolver"
    assert entry["modified"] is False
    assert path.read_text() == before  # byte-for-byte untouched


def test_run_is_registry_driven_processing_only_resolvable_brands(tmp_path):
    # (c) run() processes exactly the brands with a registered resolver (espressif + m5stack
    # + adafruit + lilygo after Slice 4), NOT other vendors — driven off VENDOR_DOC_RESOLVERS
    # keys, not a hardcoded brand. waveshare has no resolver → only LISTED, never processed.
    p_esp = _write_board(tmp_path, "esp32-c5-devkitc-1", "esp32-c5")
    p_m5 = _write_board(tmp_path, "m5stack-core2", "esp32", brand="m5stack")
    p_ws = _write_board(tmp_path, "waveshare-esp32-s3-touch", "esp32-s3", brand="waveshare")
    before_m5, before_ws = p_m5.read_text(), p_ws.read_text()
    url = _url("esp32-c5-devkitc-1", "esp32-c5")

    # fetcher serves only the espressif URL → m5stack-core2's docs.m5stack.com URL 404s, so it
    # is PROCESSED (registered) but skipped doc-unreachable — proving run() reaches m5stack now.
    report = bb.run(data_root=tmp_path, fetch=_fetcher({url: DOC_WITH_MANUAL}), today=TODAY)

    processed = {e["board_id"] for e in report["backfilled"]} | {e["board_id"] for e in report["skipped"]}
    assert "esp32-c5-devkitc-1" in processed
    assert "m5stack-core2" in processed              # m5stack is registered after Slice 2
    assert "waveshare-esp32-s3-touch" not in processed
    # a registered brand is NOT on the needs_doc_url list; only the unregistered one is
    assert "m5stack/m5stack-core2" not in report["needs_doc_url"]
    assert "waveshare/waveshare-esp32-s3-touch" in report["needs_doc_url"]
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
    bid, soc = "m5cardputer", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="m5stack")
    url, fetch = _m5_fetcher_for(bid, "m5cardputer")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    fm, _ = bb.parse_frontmatter(path)
    assert fm["usb_serial"] == "native-usb-serial-jtag"
    assert fm["getting_started"] == url


def test_m5stack_stick_s3_grounds_getting_started_and_photo_only(tmp_path):
    # (e) StickS3's REAL page names NO bridge chip and no JTAG → usb_serial OMITTED. Its
    # carousel hero grounds images.photo, but its PinMap section is TABLES-ONLY (no diagram
    # image) → images.pinout correctly OMITTED (high-confidence-or-omit). getting_started
    # grounds off the resolved URL.
    bid, soc = "m5stick-s3", "esp32-s3"
    path = _write_board(tmp_path, bid, soc, brand="m5stack")
    url, fetch = _m5_fetcher_for(bid, "m5stick-s3")
    entry = bb.backfill_board(path, tmp_path, fetch, TODAY)

    assert entry["status"] == "backfilled"
    assert entry["written"] == ["getting_started", "images"]
    assert set(entry["omitted"]) == {"download_mode", "usb_serial"}
    fm, _ = bb.parse_frontmatter(path)
    assert fm["getting_started"] == url
    assert "usb_serial" not in fm
    assert "download_mode" not in fm
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


def test_m5stack_download_mode_not_grounded_and_espressif_img_heuristic_finds_nothing():
    # CRITICAL cite-or-omit: on the REAL m5stack pages the Espressif-tuned download_mode
    # heuristic correctly returns None (no Boot-button sequence → no false positive), so
    # download_mode stays omitted. And the ESPRESSIF filename image heuristic (the registry
    # default) still finds NOTHING on m5stack's opaque CDN — m5stack images only ground via
    # the dedicated context extractor (extract_images_m5stack), never the filename fallback.
    for name in ("m5stack-core2", "m5cardputer", "m5stick-s3", "m5stack-papers3"):
        raw = _fixture(name)
        assert bb.extract_download_mode(bb._visible_text(raw)) is None
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
    # claim. The download_mode auto-branch must NOT be fooled by it → returns None (omit).
    # usb_serial still grounds (the page names CH9102).
    raw = _fixture("m5stack-papers3")
    text = bb._visible_text(raw)
    assert bb.extract_download_mode(text) is None    # "automatic port recognition" ≠ auto-download
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
