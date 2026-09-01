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
