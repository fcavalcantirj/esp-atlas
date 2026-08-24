"""SQLite schema + connection helpers for esp-atlas.db.

Two-part index: `parts` is the structured table for exact filtering, `parts_fts`
is an FTS5 virtual table over free text (name/aka/prose/notes). `brands` is a
small editorial lookup (data/brands/<slug>/brand.md), kept out of `parts` on
purpose — see esp_atlas_core.brands. `meta` tracks the build id used to key the
answer cache in `answer_cache`.
"""
import sqlite3

from esp_atlas_core.paths import DEFAULT_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS parts (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    vendor_or_brand TEXT NOT NULL,
    name TEXT NOT NULL,
    wifi_standard TEXT,
    wifi_bands TEXT,
    ble_version TEXT,
    bt_classic INTEGER,
    ieee802154 INTEGER,
    ieee802154_protocols TEXT,
    form_factor TEXT,
    price_tier TEXT,
    soc_ref TEXT,
    module_ref TEXT,
    usb_native INTEGER,
    path TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    frontmatter_json TEXT NOT NULL DEFAULT '{}',
    body TEXT NOT NULL DEFAULT '',
    flash_mb REAL,
    psram_mb REAL
);

CREATE INDEX IF NOT EXISTS idx_parts_type ON parts(type);
CREATE INDEX IF NOT EXISTS idx_parts_form_factor ON parts(form_factor);
CREATE INDEX IF NOT EXISTS idx_parts_soc_ref ON parts(soc_ref);

CREATE VIRTUAL TABLE IF NOT EXISTS parts_fts USING fts5(
    id UNINDEXED,
    name,
    aka,
    prose,
    notes
);

CREATE TABLE IF NOT EXISTS brands (
    slug TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS answer_cache (
    cache_key TEXT PRIMARY KEY,
    build_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    citations_json TEXT NOT NULL,
    used_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def connect(db_path=None):
    """Open (and if needed, create) the esp-atlas SQLite database."""
    path = db_path if db_path is not None else DEFAULT_DB_PATH
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


# Columns added after the first release. CREATE TABLE IF NOT EXISTS never alters an
# existing table, so a db built by an older version is migrated in place here.
_ADDED_COLUMNS = {
    "frontmatter_json": "TEXT NOT NULL DEFAULT '{}'",
    "body": "TEXT NOT NULL DEFAULT ''",
    "flash_mb": "REAL",
    "psram_mb": "REAL",
}

# Indexes over columns that may only exist after _ensure_columns runs (a fresh
# CREATE TABLE already includes them, but a migrated older db does not until
# the ALTER TABLE above lands) -- created here instead of inside SCHEMA so they
# never run against a not-yet-existing column.
_POST_MIGRATION_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_parts_psram_mb ON parts(psram_mb)",
    "CREATE INDEX IF NOT EXISTS idx_parts_flash_mb ON parts(flash_mb)",
)


def _ensure_columns(conn):
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(parts)")}
    for name, decl in _ADDED_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE parts ADD COLUMN {name} {decl}")


def create_schema(conn):
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    for stmt in _POST_MIGRATION_INDEXES:
        conn.execute(stmt)
    conn.commit()


def clear_parts(conn):
    conn.execute("DELETE FROM parts")
    conn.execute("DELETE FROM parts_fts")
    conn.commit()


def clear_brands(conn):
    conn.execute("DELETE FROM brands")
    conn.commit()


def get_meta(conn, key, default=None):
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(conn, key, value):
    conn.execute(
        "INSERT INTO meta(key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
