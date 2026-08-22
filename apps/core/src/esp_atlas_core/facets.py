"""Distinct values (with counts) of every filterable column in esp-atlas.db.

    facets()  # -> {"form_factor": [{"value": "devkit", "count": 19}, ...], ...}

This is what lets a UI build its dropdowns from the data instead of hardcoding
them: a new form factor or price tier shows up the moment it is indexed. Multi-
valued columns (wifi_bands, ieee802154_protocols) are stored comma-joined and are
split back into individual tokens here. Each list is sorted by count desc, then
value, and NULL/empty values are dropped.
"""
from collections import Counter

from esp_atlas_core import db as dbmod

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


def facets(db_path=None):
    conn = dbmod.connect(db_path)
    try:
        result = {}
        for column in _SINGLE_VALUE_COLUMNS:
            rows = conn.execute(
                f"SELECT {column} AS value, COUNT(*) AS count FROM parts "
                f"WHERE {column} IS NOT NULL AND {column} != '' GROUP BY {column}"
            ).fetchall()
            result[column] = _sorted_facet({row["value"]: row["count"] for row in rows})

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
