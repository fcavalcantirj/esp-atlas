"""Editorial brand lookup — resolves the `vendor_or_brand` folder slug (e.g.
"unexpected-maker") stored on every part into the human display name and
homepage from data/brands/<slug>/brand.md, when that record exists.

Deliberately separate from `parts`: brands are not searchable/filterable parts,
just a display-name lookup keyed by slug (see esp_atlas_core.index_build).

    get_brand("espressif")   # -> {"slug": "espressif", "name": "Espressif", "url": "https://www.espressif.com"}
    get_brand("no-such-brand")  # -> None
"""
from esp_atlas_core import db as dbmod


def get_brand(slug, db_path=None):
    """One brand's {slug, name, url}, or None if data/brands/<slug>/ has no brand.md."""
    conn = dbmod.connect(db_path)
    try:
        row = conn.execute("SELECT slug, name, url FROM brands WHERE slug = ?", (slug,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def list_brands(db_path=None):
    """Every known brand, keyed by slug: {slug: {"name": ..., "url": ...}}."""
    conn = dbmod.connect(db_path)
    try:
        rows = conn.execute("SELECT slug, name, url FROM brands").fetchall()
        return {row["slug"]: {"name": row["name"], "url": row["url"]} for row in rows}
    finally:
        conn.close()
