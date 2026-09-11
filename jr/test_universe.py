"""EspAtlas Jr — pytest for the board-universe manifest + honest coverage denominator
(jr/universe.py, SPEC-universe.md).

Every test runs OFFLINE by construction — universe.py never touches the network and only
reads committed manifests + the data/boards/ filesystem. Filesystem-shape tests use tmp_path
fixtures so they don't depend on future catalog changes; a small set of tests pin the REAL
committed seeed manifest (3 cataloged / 5 universe, missing c5 + s3-sense) as the
characterization anchor for this slice.

Run: cd jr && python3 -m pytest test_universe.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import universe  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
REAL_UNIVERSE_DIR = REPO / "docs" / "universe"
REAL_BOARDS_ROOT = REPO / "data" / "boards"


# ─────────────────────────── helpers ───────────────────────────

def _write_manifest(docs_dir: Path, brand: str, boards: list[dict]) -> Path:
    path = docs_dir / f"{brand}.yaml"
    path.write_text(yaml.safe_dump({"brand": brand, "boards": boards}, sort_keys=False),
                    encoding="utf-8")
    return path


def _entry(board_id, **over):
    e = {
        "board_id": board_id,
        "name": f"Board {board_id}",
        "mcu": "esp32-s3",
        "source_url": f"https://example.com/{board_id}",
        "status": "active",
    }
    e.update(over)
    return e


def _catalog(boards_root: Path, brand: str, board_id: str) -> None:
    d = boards_root / brand / board_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "board.md").write_text("---\nid: x\n---\n", encoding="utf-8")


# ─────────────────────────── load / parse ───────────────────────────

def test_load_manifest_parses_entries_and_optional_note(tmp_path):
    _write_manifest(tmp_path, "acme", [
        _entry("a-1"),
        _entry("a-2", status="discontinued", note="EOL 2024"),
    ])
    entries = universe.load_manifest(tmp_path / "acme.yaml")
    assert [e["board_id"] for e in entries] == ["a-1", "a-2"]
    assert entries[0]["brand"] == "acme"
    assert "note" not in entries[0]
    assert entries[1]["status"] == "discontinued"
    assert entries[1]["note"] == "EOL 2024"


def test_load_universe_returns_brand_to_entries_and_ignores_coverage(tmp_path):
    _write_manifest(tmp_path, "acme", [_entry("a-1")])
    _write_manifest(tmp_path, "beta", [_entry("b-1")])
    (tmp_path / "coverage.md").write_text("# not a manifest\n", encoding="utf-8")
    (tmp_path / "coverage.yaml").write_text("brand: bogus\nboards: []\n", encoding="utf-8")
    uni = universe.load_universe(tmp_path)
    assert set(uni) == {"acme", "beta"}
    assert [e["board_id"] for e in uni["acme"]] == ["a-1"]


def test_load_universe_missing_dir_returns_empty(tmp_path):
    assert universe.load_universe(tmp_path / "nope") == {}


# ─────────────────────────── malformed-entry handling ───────────────────────────

@pytest.mark.parametrize("boards, needle", [
    ([{"name": "x", "mcu": "esp32", "source_url": "u", "status": "active"}], "board_id"),
    ([_entry("a-1", source_url="")], "source_url"),
    ([{k: v for k, v in _entry("a-1").items() if k != "source_url"}], "source_url"),
    ([_entry("a-1", status="prototype")], "status"),
    ([_entry("a-1", name="")], "name"),
    ([_entry("a-1", mcu="")], "mcu"),
    ([_entry("a-1"), _entry("a-1")], "duplicate"),
])
def test_load_manifest_rejects_malformed_entry(tmp_path, boards, needle):
    _write_manifest(tmp_path, "acme", boards)
    with pytest.raises(universe.ManifestError) as ei:
        universe.load_manifest(tmp_path / "acme.yaml")
    assert needle in str(ei.value)


def test_load_manifest_rejects_missing_brand_or_boards(tmp_path):
    (tmp_path / "a.yaml").write_text("boards: []\n", encoding="utf-8")
    with pytest.raises(universe.ManifestError):
        universe.load_manifest(tmp_path / "a.yaml")
    (tmp_path / "b.yaml").write_text("brand: acme\n", encoding="utf-8")
    with pytest.raises(universe.ManifestError):
        universe.load_manifest(tmp_path / "b.yaml")


def test_load_manifest_rejects_non_mapping_document(tmp_path):
    (tmp_path / "a.yaml").write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(universe.ManifestError):
        universe.load_manifest(tmp_path / "a.yaml")


# ─────────────────────────── derived-catalog check ───────────────────────────

def test_is_cataloged_is_derived_from_board_md(tmp_path):
    root = tmp_path / "boards"
    _catalog(root, "acme", "a-1")
    (root / "acme" / "a-2").mkdir(parents=True)  # dir exists but no board.md
    assert universe.is_cataloged("acme", "a-1", root) is True
    assert universe.is_cataloged("acme", "a-2", root) is False   # dir alone != cataloged
    assert universe.is_cataloged("acme", "a-3", root) is False   # nothing at all


# ─────────────────────────── coverage math ───────────────────────────

def test_coverage_math_and_missing_order(tmp_path):
    docs, root = tmp_path / "docs", tmp_path / "boards"
    docs.mkdir()
    _write_manifest(docs, "acme", [_entry("a-1"), _entry("a-2"), _entry("a-3")])
    _catalog(root, "acme", "a-1")   # a-2, a-3 missing (in manifest order)
    cov = universe.coverage(universe.load_universe(docs), root)
    b = cov["brands"]["acme"]
    assert b == {"universe_count": 3, "cataloged_count": 1, "missing": ["a-2", "a-3"]}
    assert cov["overall"] == {
        "universe_count": 3, "cataloged_count": 1, "missing_count": 2,
        "pct": round(1 / 3 * 100, 1),
    }


def test_coverage_empty_universe_is_zero_not_crash():
    cov = universe.coverage({})
    assert cov["overall"]["pct"] == 0.0
    assert cov["overall"]["universe_count"] == 0
    assert cov["brands"] == {}


def test_coverage_does_not_write_to_boards_root(tmp_path):
    docs, root = tmp_path / "docs", tmp_path / "boards"
    docs.mkdir()
    root.mkdir()
    _write_manifest(docs, "acme", [_entry("a-1")])
    before = list(root.rglob("*"))
    universe.coverage(universe.load_universe(docs), root)
    assert list(root.rglob("*")) == before   # read-only: nothing created


# ─────────────────────────── report render ───────────────────────────

def test_render_coverage_md_has_overall_and_missing(tmp_path):
    docs, root = tmp_path / "docs", tmp_path / "boards"
    docs.mkdir()
    _write_manifest(docs, "acme", [_entry("a-1"), _entry("a-2")])
    _catalog(root, "acme", "a-1")
    md = universe.render_coverage_md(universe.coverage(universe.load_universe(docs), root))
    assert "1/2" in md
    assert "`a-2`" in md
    assert "cataloged ÷ universe" in md


# ─────────────────────── REAL committed seeed manifest (characterization) ───────────────────────

def test_real_seeed_manifest_loads_five_verified_entries():
    uni = universe.load_universe(REAL_UNIVERSE_DIR)
    assert "seeed" in uni
    ids = [e["board_id"] for e in uni["seeed"]]
    assert ids == ["xiao-esp32c3", "xiao-esp32c6", "xiao-esp32s3",
                   "xiao-esp32c5", "xiao-esp32s3-sense"]
    for e in uni["seeed"]:
        assert e["source_url"].startswith("https://wiki.seeedstudio.com/")
        assert e["mcu"].startswith("esp32-")
        assert e["status"] in universe.VALID_STATUS


# ─────────────────────── REAL committed adafruit manifest (characterization) ───────────────────────

# The 11 board_ids esp-atlas already catalogs under data/boards/adafruit/ — these MUST derive
# in_catalog=true from the real filesystem (board.md existence), so cataloged_count includes them.
_ADAFRUIT_KNOWN_CATALOGED = [
    "adafruit-feather-esp32-s2",
    "adafruit-feather-esp32-s3-reverse-tft",
    "adafruit-feather-esp32-s3",
    "adafruit-feather-esp32-v2",
    "adafruit-huzzah32-esp32-feather",
    "adafruit-itsybitsy-esp32",
    "adafruit-matrixportal-s3",
    "adafruit-metro-esp32-s3",
    "adafruit-qt-py-esp32-c3",
    "adafruit-qt-py-esp32-s2",
    "adafruit-qt-py-esp32-s3",
]


def test_real_adafruit_manifest_loads_and_is_well_formed():
    uni = universe.load_universe(REAL_UNIVERSE_DIR)
    assert "adafruit" in uni
    ids = [e["board_id"] for e in uni["adafruit"]]
    assert len(ids) == len(set(ids))            # unique board_ids
    assert len(ids) >= 26                        # the arduino-esp32 boards.txt backbone
    for e in uni["adafruit"]:
        assert e["source_url"].startswith("https://")
        assert "adafruit.com" in e["source_url"]  # first-party Adafruit source
        assert e["mcu"].startswith("esp32")
        assert e["status"] in universe.VALID_STATUS


def test_real_adafruit_known_ids_derive_in_catalog():
    # The 11 already-cataloged ids must be present in the manifest AND derive in_catalog=true
    # from the real data/boards/adafruit/<id>/board.md filesystem.
    uni = universe.load_universe(REAL_UNIVERSE_DIR)
    manifest_ids = {e["board_id"] for e in uni["adafruit"]}
    for bid in _ADAFRUIT_KNOWN_CATALOGED:
        assert bid in manifest_ids, f"{bid} missing from adafruit manifest"
        assert universe.is_cataloged("adafruit", bid, REAL_BOARDS_ROOT) is True


def test_real_adafruit_coverage_derives_and_includes_the_11():
    uni = universe.load_universe(REAL_UNIVERSE_DIR)
    manifest_ids = [e["board_id"] for e in uni["adafruit"]]
    on_disk = {bid for bid in manifest_ids
               if (REAL_BOARDS_ROOT / "adafruit" / bid / "board.md").exists()}
    cov = universe.coverage(uni, REAL_BOARDS_ROOT)
    b = cov["brands"]["adafruit"]
    assert b["universe_count"] == len(manifest_ids)
    assert b["cataloged_count"] == len(on_disk)
    assert set(b["missing"]) == set(manifest_ids) - on_disk
    # every one of the 11 known ids contributes to cataloged_count (none in missing)
    assert set(_ADAFRUIT_KNOWN_CATALOGED).isdisjoint(set(b["missing"]))
    assert b["cataloged_count"] >= len(_ADAFRUIT_KNOWN_CATALOGED)


def test_real_seeed_coverage_is_consistent_with_the_filesystem():
    # Mechanism test (NOT a frozen count snapshot): coverage must always agree with the
    # real manifest size and which board dirs actually exist, so it stays correct as Phase B
    # authors the missing boards. universe_count == manifest entries; cataloged/missing are
    # derived from data/boards/seeed/<id>/board.md existence.
    manifest_ids = [e["board_id"] for e in universe.load_universe(REAL_UNIVERSE_DIR)["seeed"]]
    on_disk = {bid for bid in manifest_ids if (REAL_BOARDS_ROOT / "seeed" / bid / "board.md").exists()}
    cov = universe.coverage(universe.load_universe(REAL_UNIVERSE_DIR), REAL_BOARDS_ROOT)
    b = cov["brands"]["seeed"]
    assert b["universe_count"] == len(manifest_ids)
    assert b["cataloged_count"] == len(on_disk)
    assert set(b["missing"]) == set(manifest_ids) - on_disk
    assert b["cataloged_count"] + len(b["missing"]) == b["universe_count"]
