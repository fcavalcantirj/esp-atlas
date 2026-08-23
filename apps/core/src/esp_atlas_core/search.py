"""Deterministic search over esp-atlas.db: structured WHERE + FTS5 MATCH, no LLM.

    search("zigbee", filters={"form": "xiao"})
    search("", filters={"radio": "wifi-6", "band": 5})

`radio` is a minimum capability, not an exact match: Wi-Fi generations are backward
compatible, so radio="wifi-4" also matches wifi-6 parts (e.g. ESP32-C6/C5), while
radio="wifi-6" matches only wifi-6 parts. Parts with no Wi-Fi radio at all (e.g.
ESP32-H2) never match any radio= request.
"""
import json
import re

from esp_atlas_core import db as dbmod
from esp_atlas_core.brands import get_brand, list_brands

# CLI/public filter key -> parts column (or handler) it maps to
_BOOL_FILTERS = {"ieee802154", "ble", "bt_classic", "usb_native"}
_EXACT_FILTERS = {"type", "form", "soc", "module", "brand"}
_KNOWN_FILTERS = _BOOL_FILTERS | _EXACT_FILTERS | {"band", "protocol", "radio"}

_FTS_SPECIAL = re.compile(r'[^\w\s]')

# Wi-Fi generations are backward compatible: a request for wifi-4 must also match
# newer, wifi-6 parts. Higher rank = newer generation; extend here for wifi-7.
_WIFI_STANDARD_RANK = {"wifi-4": 4, "wifi-6": 6}


def _wifi_standards_at_or_above(min_standard):
    if min_standard not in _WIFI_STANDARD_RANK:
        raise ValueError(
            f"unknown wifi standard: {min_standard!r}, expected one of {sorted(_WIFI_STANDARD_RANK)}"
        )
    min_rank = _WIFI_STANDARD_RANK[min_standard]
    return [s for s, rank in _WIFI_STANDARD_RANK.items() if rank >= min_rank]


def _validate_filters(filters):
    unknown = set(filters) - _KNOWN_FILTERS
    if unknown:
        raise ValueError(f"unknown search filter(s): {sorted(unknown)}")


def _normalize_band(value):
    """Render a GHz band the same way it's stored: whole numbers with no trailing '.0'.

    CLI options are declared as type=float (so `--band 5` arrives here as `5` for the
    `5` GHz band), while wifi_bands stores tokens like "2.4,5". Without this, 5.0
    stringifies to "5.0" and never matches the stored "5" token.
    """
    text = str(value)
    if text.endswith(".0"):
        text = text[:-2]
    return text


def _build_where(filters):
    clauses = []
    params = []

    if "type" in filters:
        clauses.append("parts.type = ?")
        params.append(filters["type"])
    if "radio" in filters:
        standards = _wifi_standards_at_or_above(filters["radio"])
        clauses.append(f"parts.wifi_standard IN ({','.join('?' for _ in standards)})")
        params.extend(standards)
    if "form" in filters:
        clauses.append("LOWER(parts.form_factor) = LOWER(?)")
        params.append(filters["form"])
    if "soc" in filters:
        clauses.append("parts.soc_ref = ?")
        params.append(filters["soc"])
    if "module" in filters:
        clauses.append("parts.module_ref = ?")
        params.append(filters["module"])
    if "brand" in filters:
        # exact: vendor_or_brand holds the canonical folder slug (e.g. "unexpected-maker")
        clauses.append("parts.vendor_or_brand = ?")
        params.append(filters["brand"])
    if "band" in filters:
        clauses.append("(',' || parts.wifi_bands || ',') LIKE ?")
        params.append(f"%,{_normalize_band(filters['band'])},%")
    if "protocol" in filters:
        clauses.append("LOWER(parts.ieee802154_protocols) LIKE LOWER(?)")
        params.append(f"%{filters['protocol']}%")
    if "ieee802154" in filters:
        clauses.append("parts.ieee802154 = ?")
        params.append(1 if filters["ieee802154"] else 0)
    if "ble" in filters:
        clauses.append("parts.ble_version IS NOT NULL" if filters["ble"] else "parts.ble_version IS NULL")
    if "bt_classic" in filters:
        clauses.append("parts.bt_classic = ?")
        params.append(1 if filters["bt_classic"] else 0)
    if "usb_native" in filters:
        clauses.append("parts.usb_native = ?")
        params.append(1 if filters["usb_native"] else 0)

    return clauses, params


def _fts_query(query):
    """Turn free text into a safe FTS5 MATCH expression (quoted terms, OR'd)."""
    terms = [t for t in _FTS_SPECIAL.sub(" ", query).split() if t]
    if not terms:
        return None
    return " OR ".join(f'"{t}"' for t in terms)


def _row_to_record(row, brands_lookup=None):
    """`brands_lookup` is {slug: {"name", "url"}} — see esp_atlas_core.brands.list_brands.
    Loaded once per query and passed in, never fetched per row."""
    brands_lookup = brands_lookup or {}
    slug = row["vendor_or_brand"]
    brand = brands_lookup.get(slug, {})
    return {
        "id": row["id"],
        "type": row["type"],
        "name": row["name"],
        "vendor_or_brand": slug,
        "brand_name": brand.get("name", slug),
        "brand_url": brand.get("url"),
        "wifi_standard": row["wifi_standard"],
        "wifi_bands": row["wifi_bands"],
        "ble_version": row["ble_version"],
        "bt_classic": None if row["bt_classic"] is None else bool(row["bt_classic"]),
        "ieee802154": None if row["ieee802154"] is None else bool(row["ieee802154"]),
        "ieee802154_protocols": row["ieee802154_protocols"],
        "form_factor": row["form_factor"],
        "price_tier": row["price_tier"],
        "soc_ref": row["soc_ref"],
        "module_ref": row["module_ref"],
        "usb_native": None if row["usb_native"] is None else bool(row["usb_native"]),
        "_path": row["path"],
        "sources": json.loads(row["sources_json"]),
    }


def search(query, filters=None, db_path=None, limit=500):
    filters = filters or {}
    _validate_filters(filters)
    where_clauses, params = _build_where(filters)
    fts_expr = _fts_query(query) if query else None

    brands_lookup = list_brands(db_path=db_path)
    conn = dbmod.connect(db_path)
    try:
        if fts_expr:
            sql = (
                "SELECT parts.*, bm25(parts_fts) AS rank FROM parts "
                "JOIN parts_fts ON parts.id = parts_fts.id "
                "WHERE parts_fts MATCH ?"
            )
            params = [fts_expr] + params
            if where_clauses:
                sql += " AND " + " AND ".join(where_clauses)
            sql += " ORDER BY rank LIMIT ?"
            params.append(limit)
        else:
            sql = "SELECT parts.*, 0 AS rank FROM parts"
            if where_clauses:
                sql += " WHERE " + " AND ".join(where_clauses)
            sql += " ORDER BY parts.type, parts.name LIMIT ?"
            params.append(limit)

        rows = conn.execute(sql, params).fetchall()
        return [_row_to_record(r, brands_lookup) for r in rows]
    finally:
        conn.close()


def _fetch_record(conn, part_id, brands_lookup):
    row = conn.execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
    return _row_to_record(row, brands_lookup) if row else None


def get_part(part_id, db_path=None):
    """One part by id, with everything the detail page needs, or None.

    Returns the flat record (same shape as search()) plus:
      frontmatter  the record's full YAML frontmatter as a dict (board usb/power/
                   display/extras, module flash/psram, soc cpu/memory, ...)
      body         the markdown prose below the frontmatter
      chain        {"soc": record|None, "module": record|None} — the parents this
                   part inherits from (a soc has neither; a bare-chip board has no module)
      related      other parts on the same soc (and, for a module, boards using it),
                   excluding the part itself, ordered by type then name
    """
    brands_lookup = list_brands(db_path=db_path)
    conn = dbmod.connect(db_path)
    try:
        row = conn.execute("SELECT * FROM parts WHERE id = ?", (part_id,)).fetchone()
        if row is None:
            return None

        record = _row_to_record(row, brands_lookup)
        record["frontmatter"] = json.loads(row["frontmatter_json"])
        record["body"] = row["body"]

        soc_id = row["soc_ref"]
        module_id = row["module_ref"]
        record["chain"] = {
            "soc": _fetch_record(conn, soc_id, brands_lookup) if soc_id and soc_id != part_id else None,
            "module": _fetch_record(conn, module_id, brands_lookup) if module_id and module_id != part_id else None,
        }

        # siblings on the same soc (+ boards using this module), minus self and the chain parents
        related_rows = conn.execute(
            "SELECT * FROM parts WHERE id NOT IN (?, ?, ?) AND (soc_ref = ? OR module_ref = ?) "
            "ORDER BY parts.type, parts.name",
            (part_id, soc_id or "", module_id or "", soc_id, part_id),
        ).fetchall()
        record["related"] = [_row_to_record(r, brands_lookup) for r in related_rows]
        return record
    finally:
        conn.close()


def brand_page(slug, db_path=None):
    """Everything /brands/<slug> needs: the brand's own {slug, name, url} (falling
    back to the slug itself when data/brands/<slug>/ has no brand.md) plus every
    part from it. An unknown slug still returns 200 with an empty `results` list,
    same as search(filters={"brand": slug}) — the caller 404s on empty results."""
    results = search("", filters={"brand": slug}, db_path=db_path)
    brand = get_brand(slug, db_path=db_path) or {"slug": slug, "name": slug, "url": None}
    return {"brand": brand, "results": results}
