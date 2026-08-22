import sqlite3

from esp_atlas_core.index_build import build_index
from esp_atlas_core.paths import DATA_DIR


def test_build_index_creates_structured_and_fts_tables(tmp_path):
    db_path = tmp_path / "esp-atlas.db"
    build_id = build_index(db_path=db_path)
    assert build_id

    conn = sqlite3.connect(db_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table','view')")}
    assert "parts" in tables
    assert "parts_fts" in tables
    assert "meta" in tables

    cols = {r[1] for r in conn.execute("PRAGMA table_info(parts)")}
    required = {
        "id", "type", "vendor_or_brand", "name", "wifi_standard", "wifi_bands",
        "ble_version", "bt_classic", "ieee802154", "ieee802154_protocols",
        "form_factor", "price_tier", "soc_ref", "module_ref",
    }
    assert required.issubset(cols)


def test_build_index_row_count_matches_data_files():
    import glob
    n_files = sum(
        len(list((DATA_DIR).glob(p)))
        for p in ("socs/*/chip.md", "modules/*/module.md", "boards/*/*/board.md")
    )
    assert n_files > 0


def test_build_index_resolves_soc_radios_directly(tmp_path):
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM parts WHERE id = 'esp32-c6'").fetchone()
    assert row["type"] == "soc"
    assert row["wifi_standard"] == "wifi-6"
    assert row["wifi_bands"] == "2.4"
    assert row["ble_version"] == "5.3"
    assert bool(row["ieee802154"]) is True
    assert "zigbee-3.0" in row["ieee802154_protocols"]
    assert row["soc_ref"] == "esp32-c6"
    assert row["module_ref"] is None


def test_build_index_resolves_module_radios_via_soc(tmp_path):
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM parts WHERE id = 'esp32-c6-wroom-1'").fetchone()
    assert row["type"] == "module"
    # module inherits radios from its soc (esp32-c6), never restates them
    assert row["wifi_standard"] == "wifi-6"
    assert bool(row["ieee802154"]) is True
    assert row["soc_ref"] == "esp32-c6"
    assert row["module_ref"] == "esp32-c6-wroom-1"


def test_build_index_resolves_board_radios_via_module_then_soc(tmp_path):
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM parts WHERE id = 'esp32-c6-devkitc-1'").fetchone()
    assert row["type"] == "board"
    assert row["vendor_or_brand"] == "espressif"
    assert row["form_factor"] == "devkit"
    assert row["wifi_standard"] == "wifi-6"
    assert bool(row["ieee802154"]) is True
    assert row["soc_ref"] == "esp32-c6"
    assert row["module_ref"] == "esp32-c6-wroom-1"


def test_build_index_resolves_board_with_direct_soc_and_no_module(tmp_path):
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM parts WHERE id = 'xiao-esp32c6'").fetchone()
    assert row["type"] == "board"
    assert row["vendor_or_brand"] == "seeed"
    assert row["form_factor"] == "xiao"
    assert row["wifi_standard"] == "wifi-6"
    assert bool(row["ieee802154"]) is True
    assert row["soc_ref"] == "esp32-c6"
    assert row["module_ref"] is None


def test_build_index_resolves_board_radios_via_direct_soc(tmp_path):
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM parts WHERE id = 'lilygo-t-display-s3'").fetchone()
    assert row["type"] == "board"
    assert row["soc_ref"] == "esp32-s3"
    assert row["module_ref"] is None
    assert row["wifi_standard"] == "wifi-4"
    assert bool(row["ieee802154"]) is False


def test_build_index_resolves_board_price_tier_when_set(tmp_path):
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM parts WHERE id = 'xiao-esp32c3'").fetchone()
    assert row["price_tier"] == "cheap"


def test_build_index_price_tier_is_null_when_unset(tmp_path):
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM parts WHERE id = 'esp32-c6'").fetchone()
    assert row["price_tier"] is None


def test_build_index_fts_table_has_prose_and_notes(tmp_path):
    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name FROM parts_fts WHERE parts_fts MATCH 'Zigbee' AND id = 'esp32-c6'"
    ).fetchone()
    assert row is not None


def test_build_index_is_deterministic_build_id():
    id1 = build_index(db_path=":memory:")
    id2 = build_index(db_path=":memory:")
    assert id1 == id2


def test_build_index_stores_frontmatter_json_and_body(tmp_path):
    import json

    db_path = tmp_path / "esp-atlas.db"
    build_index(db_path=db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM parts WHERE id = 'xiao-esp32c6'").fetchone()
    fm = json.loads(row["frontmatter_json"])
    assert fm["dimensions_mm"] == [21, 17.8]
    assert fm["usb"]["connector"] == "usb-c"
    assert row["body"].startswith("# Seeed Studio XIAO ESP32C6")


def test_create_schema_adds_missing_columns_to_an_older_db(tmp_path):
    """A db built before frontmatter_json/body existed must be migrated in place,
    not fail on INSERT — CREATE TABLE IF NOT EXISTS alone never alters a table."""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE parts (
            id TEXT PRIMARY KEY, type TEXT NOT NULL, vendor_or_brand TEXT NOT NULL,
            name TEXT NOT NULL, wifi_standard TEXT, wifi_bands TEXT, ble_version TEXT,
            bt_classic INTEGER, ieee802154 INTEGER, ieee802154_protocols TEXT,
            form_factor TEXT, price_tier TEXT, soc_ref TEXT, module_ref TEXT,
            usb_native INTEGER, path TEXT NOT NULL, sources_json TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()

    build_index(db_path=db_path)

    conn = sqlite3.connect(db_path)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(parts)")}
    assert {"frontmatter_json", "body"}.issubset(cols)
    assert conn.execute("SELECT COUNT(*) FROM parts WHERE body != ''").fetchone()[0] > 0
