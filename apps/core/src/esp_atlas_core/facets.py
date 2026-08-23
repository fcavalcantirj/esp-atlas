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

FACET_KEYS = _SINGLE_VALUE_COLUMNS + _MULTI_VALUE_COLUMNS


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
        return result
    finally:
        conn.close()
