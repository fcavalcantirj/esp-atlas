"""Distinct values (with counts) of every filterable column in esp-atlas.db.

    facets()  # -> {"form_factor": [{"value": "devkit", "count": 19}, ...], ...}

This is what lets a UI build its dropdowns from the data instead of hardcoding
them: a new form factor or price tier shows up the moment it is indexed. Multi-
valued columns (wifi_bands, ieee802154_protocols) are stored comma-joined and are
split back into individual tokens here. Each list is sorted by count desc, then
value, and NULL/empty values are dropped.

`vendor_or_brand` entries additionally carry `display_name` (and `url` when
known) resolved from the `brands` table — see esp_atlas_core.brands — so a UI
never has to render the raw folder slug. A slug with no data/brands/ record
falls back to itself as the display name.

`psram_min`/`flash_min` are different in kind: they are minimum-capability
*tiers*, not exact values (see esp_atlas_core.search/wizard `psram_min`/
`flash_min`), so each entry's `count` is how many parts clear that floor, not
how many equal it. The candidate tiers are fixed by SPEC-hosting-lane.md, not
derived from data — only the ones with >=1 matching part are returned, so the
UI never offers a dead option.
"""
from collections import Counter

from esp_atlas_core import db as dbmod

_VENDOR_OR_BRAND = "vendor_or_brand"

_SINGLE_VALUE_COLUMNS = (
    "type",
    "vendor_or_brand",
    "form_factor",
    "wifi_standard",
    "price_tier",
    "soc_ref",
)
_MULTI_VALUE_COLUMNS = ("wifi_bands", "ieee802154_protocols")

# need key -> (column, candidate tiers in MB) -- fixed by SPEC-hosting-lane.md
_MEMORY_MIN_TIERS = {
    "psram_min": ("psram_mb", (2, 4, 8)),
    "flash_min": ("flash_mb", (4, 8, 16)),
}

FACET_KEYS = _SINGLE_VALUE_COLUMNS + _MULTI_VALUE_COLUMNS + tuple(_MEMORY_MIN_TIERS)


def _sorted_facet(counter):
    return [
        {"value": value, "count": count}
        for value, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))
    ]


def _brand_lookup(conn):
    rows = conn.execute("SELECT slug, name, url FROM brands").fetchall()
    return {row["slug"]: (row["name"], row["url"]) for row in rows}


def _enrich_vendor_or_brand(entries, conn):
    brands = _brand_lookup(conn)
    for entry in entries:
        name, url = brands.get(entry["value"], (None, None))
        entry["display_name"] = name or entry["value"]
        if url:
            entry["url"] = url
    return entries


def _memory_min_tiers(conn, column, tiers):
    counter = {}
    for tier in tiers:
        count = conn.execute(f"SELECT COUNT(*) AS c FROM parts WHERE {column} >= ?", (tier,)).fetchone()["c"]
        if count:
            counter[tier] = count
    return _sorted_facet(counter)


def facets(db_path=None):
    conn = dbmod.connect(db_path)
    try:
        result = {}
        for column in _SINGLE_VALUE_COLUMNS:
            rows = conn.execute(
                f"SELECT {column} AS value, COUNT(*) AS count FROM parts "
                f"WHERE {column} IS NOT NULL AND {column} != '' GROUP BY {column}"
            ).fetchall()
            entries = _sorted_facet({row["value"]: row["count"] for row in rows})
            if column == _VENDOR_OR_BRAND:
                entries = _enrich_vendor_or_brand(entries, conn)
            result[column] = entries

        for column in _MULTI_VALUE_COLUMNS:
            counter = Counter()
            for row in conn.execute(f"SELECT {column} AS value FROM parts WHERE {column} IS NOT NULL"):
                for token in row["value"].split(","):
                    token = token.strip()
                    if token:
                        counter[token] += 1
            result[column] = _sorted_facet(counter)

        for need_key, (column, tiers) in _MEMORY_MIN_TIERS.items():
            result[need_key] = _memory_min_tiers(conn, column, tiers)

        return result
    finally:
        conn.close()
