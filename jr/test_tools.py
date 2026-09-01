"""Tests for the board-authoring lane (SPEC-espatlas-jr.md §3a "board population"):
coverage_backlog, fetch_url, author_board, board_triple_validate. Network is always mocked —
these must never make a live HTTP call. board_triple_validate's guard gate (gate1) shells the
REAL scripts/validate.py over the real (currently-clean) dataset — that's a local subprocess,
not network, and is what makes "passes on the C5 reference" a genuine integration check.
"""
import json
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tools

REPO = tools.REPO
BOARD_SCHEMA = json.loads((REPO / "schema/board.schema.json").read_text())

TEST_BRAND = "zzz-test-fixture-vendor"    # real brand folder under data/boards/, always cleaned up


@pytest.fixture
def real_board_dir():
    """author_board() computes its return path via .relative_to(REPO), so it must write under
    the REAL data/boards/ tree (BOARDS_DIR can't be monkeypatched to an outside tmp_path for
    these tests). Cleans up the throwaway brand dir after every test, pass or fail."""
    yield REPO / "data/boards" / TEST_BRAND
    shutil.rmtree(REPO / "data/boards" / TEST_BRAND, ignore_errors=True)


@pytest.fixture
def real_metro_board_dir():
    """The replay test's payload uses the real `adafruit` brand (matching the exact live-failure
    payload) rather than TEST_BRAND, so it needs its own narrow cleanup: only the one throwaway
    board_id dir under the real adafruit/ brand, never the whole (real, populated) brand dir."""
    d = REPO / "data/boards/adafruit/metro-esp32-s2"
    yield d
    shutil.rmtree(d, ignore_errors=True)


class _FakeHeadResponse:
    """A HEAD response that never raises — simulates every cited source being alive."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_urlopen_alive(req, timeout=None):
    return _FakeHeadResponse()


def _fake_urlopen_dead(req, timeout=None):
    raise OSError("simulated network failure")


class _FakeGetResponse:
    def __init__(self, html: bytes):
        self._html = html

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self, n=-1):
        return self._html

    @property
    def headers(self):
        class _H:
            def get_content_charset(self_inner):
                return "utf-8"

        return _H()


# ─────────────────────────── board_refs ───────────────────────────

def test_board_refs_returns_real_ids_from_the_repo():
    refs = tools.board_refs()

    assert "esp32-c5" in refs["soc_ids"]                  # real soc dir under data/socs/
    assert "esp32-s3-wroom-1" in refs["module_ids"]        # real module dir under data/modules/
    assert refs["soc_ids"] == sorted(refs["soc_ids"])
    assert refs["module_ids"] == sorted(refs["module_ids"])


def test_board_refs_excludes_non_dirs(monkeypatch, tmp_path):
    socs_dir = tmp_path / "socs"
    socs_dir.mkdir()
    (socs_dir / "esp32-c5").mkdir()
    (socs_dir / "esp32").mkdir()
    (socs_dir / "README.md").write_text("not a soc")      # stray file — must be excluded
    modules_dir = tmp_path / "modules"
    modules_dir.mkdir()
    (modules_dir / "esp32-s3-wroom-1").mkdir()
    (modules_dir / "NOTES.txt").write_text("not a module")
    monkeypatch.setattr(tools, "SOCS_DIR", socs_dir)
    monkeypatch.setattr(tools, "MODULES_DIR", modules_dir)

    refs = tools.board_refs()

    assert refs == {"soc_ids": ["esp32", "esp32-c5"], "module_ids": ["esp32-s3-wroom-1"]}


def test_board_refs_missing_dirs_returns_empty_lists(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "SOCS_DIR", tmp_path / "no-socs")
    monkeypatch.setattr(tools, "MODULES_DIR", tmp_path / "no-modules")

    assert tools.board_refs() == {"soc_ids": [], "module_ids": []}


# ─────────────────────────── coverage_backlog ───────────────────────────

COVERAGE_FIXTURE = """# Board Coverage Backlog

## VendorA

- [x] Checked Board — https://example.com/checked
- [ ] Board Two — https://example.com/two
- [ ] Board Three — https://example.com/three
- [ ] Board No Url — (url: to-verify)
- [ ] Board Wrapped — deferred: confirmed live at
  https://example.com/wrapped (verified 2026-08-28), needs a follow-up

## VendorB

- [ ] Board Four — https://example.com/four
"""


def _write_coverage(tmp_path):
    p = tmp_path / "COVERAGE.md"
    p.write_text(COVERAGE_FIXTURE)
    return p


def test_coverage_backlog_skips_checked_and_parses_unchecked(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "COVERAGE_MD", _write_coverage(tmp_path))
    monkeypatch.setattr(tools, "BOARDS_DIR", tmp_path / "boards")  # empty -> nothing pre-authored

    backlog = tools.coverage_backlog()

    names = {b["name"] for b in backlog}
    assert "Checked Board" not in names          # [x] is done, never returned
    assert "Board Two" in names
    assert "Board Four" in names
    two = next(b for b in backlog if b["name"] == "Board Two")
    assert two == {"name": "Board Two", "vendor": "VendorA", "url": "https://example.com/two"}
    four = next(b for b in backlog if b["name"] == "Board Four")
    assert four["vendor"] == "VendorB"


def test_coverage_backlog_url_none_when_unverified(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "COVERAGE_MD", _write_coverage(tmp_path))
    monkeypatch.setattr(tools, "BOARDS_DIR", tmp_path / "boards")

    entry = next(b for b in tools.coverage_backlog() if b["name"] == "Board No Url")
    assert entry["url"] is None                  # "(url: to-verify)" must not become a fake URL


def test_coverage_backlog_finds_url_on_continuation_line(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "COVERAGE_MD", _write_coverage(tmp_path))
    monkeypatch.setattr(tools, "BOARDS_DIR", tmp_path / "boards")

    entry = next(b for b in tools.coverage_backlog() if b["name"] == "Board Wrapped")
    assert entry["url"] == "https://example.com/wrapped"


def test_coverage_backlog_dedups_boards_already_authored(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "COVERAGE_MD", _write_coverage(tmp_path))
    boards_dir = tmp_path / "boards"
    # "Board Three" already has a dir (id-slug match) even though COVERAGE.md still shows [ ]
    (boards_dir / "vendora" / "board-three").mkdir(parents=True)
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)

    names = {b["name"] for b in tools.coverage_backlog()}
    assert "Board Three" not in names
    assert "Board Two" in names                  # unaffected sibling entry still returned


def test_coverage_backlog_dedups_by_frontmatter_name(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "COVERAGE_MD", _write_coverage(tmp_path))
    boards_dir = tmp_path / "boards"
    d = boards_dir / "vendorb" / "some-other-folder-id"
    d.mkdir(parents=True)
    (d / "board.md").write_text("---\nid: some-other-folder-id\ntype: board\nbrand: vendorb\n"
                                "name: Board Four\nsoc: esp32-c5\nsources:\n- field: '*'\n"
                                "  url: https://example.com\n  verified: '2026-08-28'\n---\n\nx\n")
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)

    names = {b["name"] for b in tools.coverage_backlog()}
    assert "Board Four" not in names              # matched by name:, even though id-slug differs


def test_coverage_backlog_missing_file_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "COVERAGE_MD", tmp_path / "does-not-exist.md")
    assert tools.coverage_backlog() == []


# ─────────────────────────── fetch_url ───────────────────────────

def test_fetch_url_strips_tags_and_scripts(monkeypatch):
    html = (b"<html><head><style>.x{color:red}</style></head><body>"
            b"<script>evil()</script><h1>ESP32-Foo</h1><p>Some &amp; text.</p></body></html>")
    monkeypatch.setattr(tools.urllib.request, "urlopen", lambda req, timeout=None: _FakeGetResponse(html))

    result = tools.fetch_url("https://example.com/product")

    assert result["url"] == "https://example.com/product"
    assert "ESP32-Foo" in result["text"]
    assert "Some & text." in result["text"]
    assert "evil()" not in result["text"]
    assert "color:red" not in result["text"]
    assert "<h1>" not in result["text"]


def test_fetch_url_rejects_non_http_scheme():
    result = tools.fetch_url("ftp://example.com/x")
    assert "error" in result


def test_fetch_url_reports_network_error(monkeypatch):
    def _raise(req, timeout=None):
        raise OSError("boom")

    monkeypatch.setattr(tools.urllib.request, "urlopen", _raise)
    result = tools.fetch_url("https://example.com/dead")
    assert "error" in result


# ─────────────────────────── author_board ───────────────────────────

def _c5_like_sources():
    return [
        {"field": "*", "url": "https://example.com/guide", "verified": "2026-08-28"},
        {"field": "io.gpio_free", "url": "https://example.com/guide", "verified": "2026-08-28"},
    ]


def test_author_board_writes_schema_valid_frontmatter(real_board_dir):
    result = tools.author_board(
        "test-devkit-1", TEST_BRAND, "Test-DevKit-1",
        fields={"form_factor": "devkit", "usb": {"connector": "usb-c"}, "extras": ["rgb-led"],
                "io": {"gpio_free": 12, "gpio_pins": [0, 1, 2]},
                "notes": ["derived io.gpio_free=12, math shown"]},
        sources=_c5_like_sources(),
        body="A test devkit board.",
        soc="esp32-c5",
    )

    assert "error" not in result
    assert result["board_id"] == "test-devkit-1"
    path = REPO / result["path"]
    assert path == real_board_dir / "test-devkit-1" / "board.md"

    fm = yaml.safe_load(path.read_text().split("---", 2)[1])
    assert fm["id"] == "test-devkit-1"
    assert fm["brand"] == TEST_BRAND
    assert fm["soc"] == "esp32-c5"
    jsonschema.validate(fm, BOARD_SCHEMA)          # the authoritative contract itself


def test_author_board_only_writes_provided_fields(real_board_dir):
    result = tools.author_board(
        "bare-board", TEST_BRAND, "Bare Board",
        fields={"form_factor": "devkit"},
        sources=[{"field": "*", "url": "https://example.com", "verified": "2026-08-28"}],
        body="Bare board, most fields unknown so omitted.",
        soc="esp32-c5",
    )

    fm = yaml.safe_load((REPO / result["path"]).read_text().split("---", 2)[1])
    for absent in ("display", "power", "io", "extras", "psram_mb", "flash_mb", "dimensions_mm"):
        assert absent not in fm                   # cite-or-omit: never write a field not given


def test_author_board_rejects_both_soc_and_module(real_board_dir):
    result = tools.author_board(
        "bad-board", TEST_BRAND, "Bad Board", fields={},
        sources=[{"field": "*", "url": "https://example.com", "verified": "2026-08-28"}],
        body="x", soc="esp32-c5", module="esp32-s3-wroom-1",
    )

    assert "error" in result
    assert not (real_board_dir / "bad-board").exists()


def test_author_board_rejects_neither_soc_nor_module(real_board_dir):
    result = tools.author_board(
        "bad-board-2", TEST_BRAND, "Bad Board 2", fields={},
        sources=[{"field": "*", "url": "https://example.com", "verified": "2026-08-28"}],
        body="x",
    )

    assert "error" in result


def test_author_board_rejects_missing_source(real_board_dir):
    result = tools.author_board(
        "uncited-board", TEST_BRAND, "Uncited Board",
        fields={"display": "1.9in 170x320 IPS"},        # set...
        sources=[{"field": "usb", "url": "https://example.com", "verified": "2026-08-28"}],  # ...but not cited
        body="x", soc="esp32-c5",
    )

    assert "error" in result
    assert "display" in result["error"]
    assert not (real_board_dir / "uncited-board").exists()


def test_author_board_drops_unknown_field_silently(real_board_dir):
    """A weak model's unknown field key must never crash/reject the call — it's silently
    omitted, not a schema property author_board raises or errors on (SPEC: cite-or-omit applies
    to what IS written; junk keys just never make it into the record)."""
    result = tools.author_board(
        "weird-board", TEST_BRAND, "Weird Board",
        fields={"clock_speed_ghz": 0.24, "form_factor": "devkit"},  # clock_speed_ghz: not a board.schema.json property
        sources=[{"field": "*", "url": "https://example.com", "verified": "2026-08-28"}],
        body="x", soc="esp32-c5",
    )

    assert "error" not in result, result
    fm = yaml.safe_load((REPO / result["path"]).read_text().split("---", 2)[1])
    assert "clock_speed_ghz" not in fm
    assert fm["form_factor"] == "devkit"


def test_author_board_coerces_bare_usb_string(real_board_dir):
    result = tools.author_board(
        "usb-string-board", TEST_BRAND, "USB String Board",
        fields={"usb": "USB-C"},
        sources=[{"field": "*", "url": "https://example.com", "verified": "2026-08-28"}],
        body="x", soc="esp32-c5",
    )

    assert "error" not in result, result
    fm = yaml.safe_load((REPO / result["path"]).read_text().split("---", 2)[1])
    assert fm["usb"] == {"connector": "usb-c"}
    jsonschema.validate(fm, BOARD_SCHEMA)


def test_author_board_drops_unrecognized_usb_string(real_board_dir):
    result = tools.author_board(
        "usb-junk-board", TEST_BRAND, "USB Junk Board",
        fields={"usb": "some-nonsense-connector", "form_factor": "devkit"},
        sources=[{"field": "*", "url": "https://example.com", "verified": "2026-08-28"}],
        body="x", soc="esp32-c5",
    )

    assert "error" not in result, result
    fm = yaml.safe_load((REPO / result["path"]).read_text().split("---", 2)[1])
    assert "usb" not in fm


def test_author_board_normalizes_bool_verified_when_today_given(real_board_dir):
    """A weak model sometimes emits a bare bool `verified` instead of a date. When the caller
    supplies `today`, that bool (or a missing verified) is normalized to a real ISO date."""
    result = tools.author_board(
        "today-normalized-board", TEST_BRAND, "Today Normalized Board",
        fields={"form_factor": "devkit"},
        sources=[{"field": "*", "url": "https://example.com", "verified": True}],
        body="x", soc="esp32-c5",
        today="2026-08-28",
    )

    assert "error" not in result, result
    fm = yaml.safe_load((REPO / result["path"]).read_text().split("---", 2)[1])
    assert fm["sources"][0]["verified"] == "2026-08-28"


def test_author_board_leaves_verified_alone_when_today_is_none(real_board_dir):
    """Without `today`, a bool `verified` is left as-is (still truthy, still accepted) rather
    than silently rewritten — no datetime call happens at all."""
    result = tools.author_board(
        "no-today-board", TEST_BRAND, "No Today Board",
        fields={"form_factor": "devkit"},
        sources=[{"field": "*", "url": "https://example.com", "verified": True}],
        body="x", soc="esp32-c5",
    )

    assert "error" not in result, result
    fm = yaml.safe_load((REPO / result["path"]).read_text().split("---", 2)[1])
    assert fm["sources"][0]["verified"] is True


def test_author_board_still_rejects_source_missing_field(real_board_dir):
    """cite-or-omit stays enforced as a clean error, never a raise, for a genuinely broken
    sources[] entry (e.g. missing 'field')."""
    result = tools.author_board(
        "bad-source-board", TEST_BRAND, "Bad Source Board",
        fields={"form_factor": "devkit"},
        sources=[{"url": "https://example.com", "verified": "2026-08-28"}],  # no 'field' at all
        body="x", soc="esp32-c5",
    )

    assert "error" in result
    assert not (real_board_dir / "bad-source-board").exists()


# ─────────────────────────── author_board tool schema (Agno) ───────────────────────────

def test_author_board_agno_schema_has_no_extra_required_property():
    """Same bug class as the fixed `**extra` issue: any author_board param with no default gets
    marked REQUIRED in Agno's auto-generated tool-call JSON schema. When Groq gpt-oss-120b omits
    an optional-in-spirit param like `body`, the call hard-fails with 'missing properties: body'
    and the board is lost. Only board_id/brand/name are genuinely required — fields, sources,
    body, soc, module, today must all be optional. Introspect the REAL registered tool off the
    REAL agent (agent.make_jr_board()), exactly as Agno hands it to the model."""
    from agno.tools.function import Function
    from agent import make_jr_board

    a = make_jr_board()
    author_board_fn = next(t for t in a.tools if getattr(t, "__name__", None) == "author_board")
    schema = Function.from_callable(author_board_fn).parameters

    assert set(schema["required"]) == {"board_id", "brand", "name"}
    assert "extra" not in schema["properties"]


def test_author_board_callable_with_body_omitted(real_board_dir):
    """The live-failure shape: Groq omits `body` entirely. Must not raise, and must still write a
    valid (empty-body) record rather than hard-failing on a missing required schema property."""
    result = tools.author_board(
        "no-body-board", TEST_BRAND, "No Body Board",
        fields={"form_factor": "devkit"},
        sources=[{"field": "*", "url": "https://example.com", "verified": "2026-08-28"}],
        soc="esp32-c5",
    )

    assert "error" not in result, result
    path = REPO / result["path"]
    assert path.read_text().strip().endswith("---")   # empty body after the frontmatter, no raise


# ─────────────────────────── author_board replay (live-failure payload) ───────────────────────────

def test_author_board_replay_of_live_failure_payload_never_raises(real_metro_board_dir):
    """The exact payload from the live Groq run that crashed on the missing `extra` schema
    property. It must always come back as a dict (success or {"error": ...}), never raise, and
    board_triple_validate() must then return a real verdict for it."""
    result = tools.author_board(
        board_id="metro-esp32-s2", brand="adafruit", name="Adafruit Metro ESP32-S2",
        soc="esp32-s2",
        fields={
            "form_factor": "UNO", "dimensions_mm": [53.2, 72, 14.8], "usb": "USB-C",
            "power": "6-12V barrel jack, USB-C, LiPo",
            "extras": "STEMMA QT connector, MAX17048 battery monitor, JTAG pads",
            "flash_mb": 4, "psram_mb": 2,
            "notes": "Single-core 240 MHz ESP32-S2, no Bluetooth.",
        },
        sources=[{"field": "*", "url": "https://www.adafruit.com/product/4775", "verified": True}],
        body="",
    )

    assert isinstance(result, dict)

    verdict = tools.board_triple_validate("metro-esp32-s2")
    assert isinstance(verdict, dict)
    assert "pass" in verdict


# ─────────────────────────── board_triple_validate ───────────────────────────

def test_board_triple_validate_passes_on_c5_reference(monkeypatch):
    monkeypatch.setattr(tools.urllib.request, "urlopen", _fake_urlopen_alive)

    result = tools.board_triple_validate("esp32-c5-devkitc-1")

    assert result["pass"] is True, result
    assert result["gate1_guard"] == "green"


def test_board_triple_validate_fails_on_fabricated_uncited_field(monkeypatch, tmp_path):
    fake_boards = tmp_path / "boards"
    d = fake_boards / "testvendor" / "fake-board"
    d.mkdir(parents=True)
    (d / "board.md").write_text(
        "---\n"
        "id: fake-board\n"
        "type: board\n"
        "brand: testvendor\n"
        "name: Fake Board\n"
        "soc: esp32-c5\n"
        "display: 3.5in fabricated display, never on the source page\n"
        "sources:\n"
        "- field: name\n"
        "  url: https://example.com/fake\n"
        "  verified: '2026-08-28'\n"
        "---\n\n# Fake Board\n"
    )
    monkeypatch.setattr(tools, "BOARDS_DIR", fake_boards)
    monkeypatch.setattr(tools.urllib.request, "urlopen", _fake_urlopen_alive)

    result = tools.board_triple_validate("fake-board")

    assert result["pass"] is False
    assert any("display" in p for p in result["gate3_integrity"])


def test_board_triple_validate_unknown_board(monkeypatch, tmp_path):
    monkeypatch.setattr(tools, "BOARDS_DIR", tmp_path / "boards")
    result = tools.board_triple_validate("does-not-exist")
    assert result["pass"] is False


# ─────────────── board_triple_validate — chip-family cross-check (the MagTag guard gap) ───────────────

def _write_board(boards_dir, brand, board_id, *, soc=None, module=None, source_url):
    d = boards_dir / brand / board_id
    d.mkdir(parents=True)
    ref = f"soc: {soc}\n" if soc else f"module: {module}\n"
    (d / "board.md").write_text(
        "---\n"
        f"id: {board_id}\n"
        "type: board\n"
        f"brand: {brand}\n"
        "name: Adafruit MagTag ESP32-S2\n"
        f"{ref}"
        "sources:\n"
        "- field: '*'\n"
        f"  url: {source_url}\n"
        "  verified: '2026-08-28'\n"
        "---\n\n# Adafruit MagTag\n"
    )
    return d / "board.md"


_MAGTAG_PAGE_TEXT = (
    "Adafruit MagTag - 2.9\" Grayscale E-Ink WiFi Display, ESP32-S2\n"
    "4 MB Flash, 2 MB PSRAM, USB-C, native USB. Powered by the ESP32-S2 chip.\n"
)


def test_board_triple_validate_fails_on_chip_family_mismatch(monkeypatch, tmp_path):
    """The live wrong-ref bug: an Adafruit MagTag (real chip: ESP32-S2, per
    https://www.adafruit.com/product/4800) authored with module: esp32-wrover-e — a classic
    dual-core ESP32 module, wrong chip family entirely. board_triple_validate must catch this
    even though the module id itself is a valid ref (the gap the guard didn't check before)."""
    boards_dir = tmp_path / "boards"
    _write_board(boards_dir, "adafruit", "magtag", module="esp32-wrover-e",
                source_url="https://www.adafruit.com/product/4800")
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": _MAGTAG_PAGE_TEXT})
    monkeypatch.setattr(tools.urllib.request, "urlopen", _fake_urlopen_alive)

    result = tools.board_triple_validate("magtag")

    assert result["pass"] is False
    assert any("chip-family mismatch" in p and "esp32-s2" in p and "esp32-wrover-e" in p
              for p in result["gate3_integrity"]), result


def test_board_triple_validate_passes_chip_family_check_when_correct(monkeypatch, tmp_path):
    """The fixed MagTag: soc: esp32-s2 (matching the page) instead of module: esp32-wrover-e."""
    boards_dir = tmp_path / "boards"
    _write_board(boards_dir, "adafruit", "magtag", soc="esp32-s2",
                source_url="https://www.adafruit.com/product/4800")
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "fetch_url", lambda url: {"url": url, "text": _MAGTAG_PAGE_TEXT})
    monkeypatch.setattr(tools.urllib.request, "urlopen", _fake_urlopen_alive)

    result = tools.board_triple_validate("magtag")

    assert not any("chip-family mismatch" in p for p in
                  (result["gate3_integrity"] if isinstance(result["gate3_integrity"], list) else []))


def test_board_triple_validate_skips_chip_family_check_when_page_names_no_chip(monkeypatch, tmp_path):
    """A page that never mentions any ESP32-family token can't verify or refute the record's
    chip — skip the cross-check rather than failing on it (can't-verify != wrong)."""
    boards_dir = tmp_path / "boards"
    _write_board(boards_dir, "adafruit", "magtag", module="esp32-wrover-e",
                source_url="https://www.adafruit.com/product/4800")
    monkeypatch.setattr(tools, "BOARDS_DIR", boards_dir)
    monkeypatch.setattr(tools, "fetch_url",
                        lambda url: {"url": url, "text": "A lovely e-ink display board with WiFi."})
    monkeypatch.setattr(tools.urllib.request, "urlopen", _fake_urlopen_alive)

    result = tools.board_triple_validate("magtag")

    assert not any("chip-family mismatch" in p for p in
                  (result["gate3_integrity"] if isinstance(result["gate3_integrity"], list) else []))


# ─────────────────────────── _catalogued_repos_and_tokens ───────────────────────────

def _write_firmware(root, fw_id, name, url="https://github.com/someone/somerepo"):
    d = root / fw_id
    d.mkdir()
    (d / "firmware.md").write_text(
        f"---\nid: {fw_id}\ntype: firmware\nname: {name}\nurl: {url}\n---\n\n# {name}\n")
    return d


def test_catalogued_repos_and_tokens_splits_concatenated_id_via_name_field(monkeypatch, tmp_path):
    """A firmware id with no delimiter (e.g. 'esp32marauder') can't be split into its CORE
    token by hyphen/underscore alone — but its human-readable `name:` frontmatter field
    ('ESP32 Marauder') can. This is what makes the M5stick-Marauder device-port dedup possible
    (real bug: a candidate named 'M5stickC Plus 2 Marauder (BLE Fix)' was authored as new)."""
    monkeypatch.setattr(tools, "FIRMWARE_DIR", tmp_path)
    _write_firmware(tmp_path, "esp32marauder", "ESP32 Marauder",
                    url="https://github.com/justcallmekoko/ESP32Marauder")

    _repos, tokens = tools._catalogued_repos_and_tokens()

    assert "marauder" in tokens


def test_catalogued_repos_and_tokens_excludes_generic_vendor_tokens(monkeypatch, tmp_path):
    """A bare 'esp32' token must never enter the dedup fingerprint on its own — it names the
    chip family shared by half the catalog, not a specific firmware, and would false-skip
    unrelated new firmware that merely targets the same chip. The real CORE tokens ('marauder',
    'pirate') must still come through."""
    monkeypatch.setattr(tools, "FIRMWARE_DIR", tmp_path)
    _write_firmware(tmp_path, "esp32marauder", "ESP32 Marauder",
                    url="https://github.com/justcallmekoko/ESP32Marauder")
    _write_firmware(tmp_path, "esp32-bit-pirate", "ESP32 Bit Pirate",
                    url="https://github.com/someone/esp32-bit-pirate")

    _repos, tokens = tools._catalogued_repos_and_tokens()

    assert "esp32" not in tokens
    assert "marauder" in tokens
    assert "pirate" in tokens
