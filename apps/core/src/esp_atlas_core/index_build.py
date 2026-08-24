"""Build esp-atlas.db from data/**/*.md — the query artifact for search/wizard/ask.

    from esp_atlas_core.index_build import build_index
    build_index()  # -> esp-atlas.db at the repo root, returns the build id

Radios (wifi/bluetooth/802.15.4) and usb are declared once on the SoC and
inherited by modules (via `soc`) and boards (via `module` -> `soc`, or a
direct `soc`) per schema/*.schema.json — never restated downstream. This
module resolves that inheritance into flat, queryable columns.
"""
import hashlib
from datetime import datetime, timezone

from esp_atlas_core import db as dbmod
from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter
from esp_atlas_core.paths import REPO_ROOT


def _load_all(data_dir=None):
    """Parse every data file once; return list of (type, path, fm, body)."""
    records = []
    for content_type, path in iter_data_files(data_dir):
        fm, body = parse_frontmatter(path)
        records.append((content_type, path, fm, body))
    return records


def _resolve_soc_and_module(content_type, fm, soc_by_id, module_by_id):
    """Return (soc_fm, soc_id, module_id) a record ultimately builds on."""
    if content_type == "soc":
        return fm, fm["id"], None
    if content_type == "module":
        soc_id = fm["soc"]
        return soc_by_id.get(soc_id, {}), soc_id, fm["id"]
    # board: exactly one of soc/module per schema.board.json's anyOf
    if "soc" in fm:
        soc_id = fm["soc"]
        return soc_by_id.get(soc_id, {}), soc_id, None
    module_id = fm["module"]
    module_fm = module_by_id.get(module_id, {})
    soc_id = module_fm.get("soc")
    return soc_by_id.get(soc_id, {}), soc_id, module_id


def _resolve_usb_native(content_type, fm, soc_fm):
    soc_native = (soc_fm.get("usb") or {}).get("native")
    if content_type != "board":
        return soc_native
    # a board's own usb.bridge == 'native' means it exposes the SoC's native USB
    board_usb = fm.get("usb") or {}
    if board_usb.get("bridge") == "native":
        return True
    return soc_native


def _resolve_memory(content_type, fm, module_fm):
    """(flash_mb, psram_mb) per SPEC.md: a module's own value is authoritative for
    itself; a board's own value wins, falling back to its linked module's resolved
    value when the board states none. A soc carries neither -- out of scope."""
    if content_type == "module":
        return fm.get("flash_mb"), fm.get("psram_mb")
    if content_type == "board":
        flash_mb = fm.get("flash_mb")
        if flash_mb is None:
            flash_mb = module_fm.get("flash_mb")
        psram_mb = fm.get("psram_mb")
        if psram_mb is None:
            psram_mb = module_fm.get("psram_mb")
        return flash_mb, psram_mb
    return None, None


def _row_for(content_type, path, fm, body, soc_by_id, module_by_id):
    soc_fm, soc_id, module_id = _resolve_soc_and_module(content_type, fm, soc_by_id, module_by_id)
    module_fm = module_by_id.get(module_id, {}) if module_id else {}
    flash_mb, psram_mb = _resolve_memory(content_type, fm, module_fm)
    radios = soc_fm.get("radios") or {}
    wifi = radios.get("wifi") or {}
    bluetooth = radios.get("bluetooth") or {}
    ieee = radios.get("ieee802154") or {}

    wifi_bands = wifi.get("bands_ghz")
    ieee_protocols = ieee.get("protocols")

    return {
        "id": fm["id"],
        "type": content_type,
        "vendor_or_brand": fm.get("vendor") or fm.get("brand"),
        "name": fm["name"],
        "wifi_standard": wifi.get("standard"),
        "wifi_bands": ",".join(str(b) for b in wifi_bands) if wifi_bands else None,
        "ble_version": bluetooth.get("le"),
        "bt_classic": _bool_to_int(bluetooth.get("classic")),
        "ieee802154": _bool_to_int(ieee.get("present")),
        "ieee802154_protocols": ",".join(ieee_protocols) if ieee_protocols else None,
        "form_factor": fm.get("form_factor"),
        "price_tier": fm.get("price_tier"),
        "soc_ref": soc_id,
        "module_ref": module_id,
        "usb_native": _bool_to_int(_resolve_usb_native(content_type, fm, soc_fm)),
        "flash_mb": flash_mb,
        "psram_mb": psram_mb,
        "path": str(path.relative_to(REPO_ROOT)),
        "sources_json": _json_dumps(fm.get("sources") or []),
        "frontmatter_json": _json_dumps(fm),
        "body": body,
        "aka": " ".join(fm.get("aka") or []),
        "notes": "\n".join(fm.get("notes") or []),
        "prose": body,
    }


def _bool_to_int(value):
    return None if value is None else int(bool(value))


def _json_dumps(value):
    import json

    # default=str: an unquoted YAML date would otherwise be a datetime.date and fail
    return json.dumps(value, ensure_ascii=False, default=str)


def _compute_build_id(records):
    hasher = hashlib.sha256()
    for _content_type, path, _fm, _body in sorted(records, key=lambda r: str(r[1])):
        hasher.update(str(path.relative_to(REPO_ROOT)).encode("utf-8"))
        hasher.update(path.read_bytes())
    return hasher.hexdigest()[:16]


def build_index(db_path=None, data_dir=None):
    """Rebuild esp-atlas.db from data/**/*.md. Returns the new build id.

    Brand records (data/brands/<slug>/brand.md) are an editorial lookup, not a
    part — they never enter `parts`/`parts_fts`, only the separate `brands` table.
    Firmware and recipe records (data/firmware/, data/recipes/) are likewise
    first-class entities, not parts — they are read straight off disk by
    esp_atlas_core.firmware instead of being indexed here at all.
    """
    records = _load_all(data_dir)
    part_records = [r for r in records if r[0] not in ("brand", "firmware", "recipe")]
    brand_records = [r for r in records if r[0] == "brand"]
    soc_by_id = {fm["id"]: fm for t, _p, fm, _b in part_records if t == "soc"}
    module_by_id = {fm["id"]: fm for t, _p, fm, _b in part_records if t == "module"}

    conn = dbmod.connect(db_path)
    try:
        dbmod.create_schema(conn)
        dbmod.clear_parts(conn)
        dbmod.clear_brands(conn)

        for content_type, path, fm, body in part_records:
            row = _row_for(content_type, path, fm, body, soc_by_id, module_by_id)
            conn.execute(
                """
                INSERT INTO parts (
                    id, type, vendor_or_brand, name, wifi_standard, wifi_bands,
                    ble_version, bt_classic, ieee802154, ieee802154_protocols,
                    form_factor, price_tier, soc_ref, module_ref, usb_native, path, sources_json,
                    frontmatter_json, body, flash_mb, psram_mb
                ) VALUES (
                    :id, :type, :vendor_or_brand, :name, :wifi_standard, :wifi_bands,
                    :ble_version, :bt_classic, :ieee802154, :ieee802154_protocols,
                    :form_factor, :price_tier, :soc_ref, :module_ref, :usb_native, :path, :sources_json,
                    :frontmatter_json, :body, :flash_mb, :psram_mb
                )
                """,
                row,
            )
            conn.execute(
                "INSERT INTO parts_fts (id, name, aka, prose, notes) VALUES (:id, :name, :aka, :prose, :notes)",
                row,
            )

        for _content_type, _path, fm, _body in brand_records:
            conn.execute(
                "INSERT INTO brands (slug, name, url) VALUES (:slug, :name, :url)",
                {"slug": fm["id"], "name": fm["name"], "url": fm["url"]},
            )

        build_id = _compute_build_id(records)
        dbmod.set_meta(conn, "build_id", build_id)
        dbmod.set_meta(conn, "built_at", datetime.now(timezone.utc).isoformat())
        dbmod.set_meta(conn, "count", str(len(part_records)))
        conn.commit()
        return build_id
    finally:
        conn.close()
