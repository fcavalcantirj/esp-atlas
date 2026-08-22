"""Deterministic search over esp-atlas.db: structured WHERE + FTS5 MATCH, no LLM.

    search("zigbee", filters={"form": "xiao"})
    search("", filters={"radio": "wifi-6", "band": 5})
"""
import json
import re

from esp_atlas_core import db as dbmod

# CLI/public filter key -> parts column (or handler) it maps to
_BOOL_FILTERS = {"ieee802154", "ble", "bt_classic", "usb_native"}
_EXACT_FILTERS = {"type", "radio", "form"}
_KNOWN_FILTERS = _BOOL_FILTERS | _EXACT_FILTERS | {"band", "protocol"}

_FTS_SPECIAL = re.compile(r'[^\w\s]')


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
        clauses.append("parts.wifi_standard = ?")
        params.append(filters["radio"])
    if "form" in filters:
        clauses.append("LOWER(parts.form_factor) = LOWER(?)")
        params.append(filters["form"])
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


def _row_to_record(row):
    return {
        "id": row["id"],
        "type": row["type"],
        "name": row["name"],
        "vendor_or_brand": row["vendor_or_brand"],
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
        return [_row_to_record(r) for r in rows]
    finally:
        conn.close()
