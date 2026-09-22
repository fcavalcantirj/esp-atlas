"""Firmware + recipe accessors — read data/firmware/ and data/recipes/ directly.

Deliberately separate from `parts`: like brands (see esp_atlas_core.brands),
firmware and recipes are not searchable/filterable parts, never indexed into
esp-atlas.db (see esp_atlas_core.index_build.build_index). The dataset is small
(low tens of records), so these read straight off disk on every call, the same
way esp_atlas_core.validate.known_ids() scans data/ rather than a build artifact.

    list_firmware()                          # -> [{"id": "esp32marauder", "boards": 3, ...}, ...]
    get_firmware("esp32marauder")             # -> {"id": "esp32marauder", ...} or None
    recipes_for_board("m5cardputer")          # -> [{"id": "m5cardputer__esp32marauder", ...}, ...]
    recipes_for_firmware("esp32marauder")     # -> [{"id": "m5cardputer__esp32marauder", ...}, ...]
"""
from collections import Counter

from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter


def _records(kind):
    return [parse_frontmatter(path)[0] for k, path in iter_data_files() if k == kind]


def _reason_text(body):
    """A recipe's cited justification: the markdown body minus its leading
    "# board x firmware" heading, which only repeats what the frontmatter
    already states."""
    heading, _, rest = body.partition("\n")
    return rest.strip() if heading.strip().startswith("#") else body.strip()


def popularity_key(record):
    """Sort key for popularity ranking: stars desc, forks desc, name asc.

    Records with null/absent `popularity.stars` sort LAST, ordered by name
    among themselves (forks are meaningless without stars to rank against).
    The single source of truth for ordering -- reused by the `/firmware` list
    endpoint and the `/examples` projection so the two surfaces can never
    diverge (SPEC-firmware-popularity.md).
    """
    popularity = record.get("popularity") or {}
    stars = popularity.get("stars")
    name = record.get("name") or ""
    if stars is None:
        return (1, 0, 0, name)
    return (0, -stars, -(popularity.get("forks") or 0), name)


def sort_by_popularity(records):
    """`records` ordered by `popularity_key` -- see there for the exact rule."""
    return sorted(records, key=popularity_key)


def name_key(record):
    """Sort key for alphabetical ranking: name casefolded ascending, `id` tie-break.

    Records with a null/absent `name` sort LAST (trailing bucket), ordered by
    `id` among themselves. `id` is the final deterministic tie-break for equal
    (casefolded) names -- see SPEC-firmware-ordering.md §3. Replaces the old
    case-sensitive, tie-break-less inline `sorted(records, key=lambda r: r["name"])`
    that used to live in the `/firmware` endpoint.
    """
    name = record.get("name")
    rid = record.get("id") or ""
    if name is None:
        return (1, "", rid)
    return (0, name.casefold(), rid)


def _sort_by_name(records, *, descending):
    """Shared engine for `name`/`name-desc`: null names always trail, `id` is
    always the ascending tie-break regardless of direction. Two stable passes
    (sort by id, then stable-sort by name with `reverse=descending`) get this
    without needing to numerically negate a string."""
    present = [r for r in records if r.get("name") is not None]
    missing = sorted((r for r in records if r.get("name") is None), key=lambda r: r.get("id") or "")
    present = sorted(present, key=lambda r: r.get("id") or "")
    present = sorted(present, key=lambda r: r["name"].casefold(), reverse=descending)
    return present + missing


def forks_key(record):
    """Sort key for fork-count ranking: forks desc, stars desc (tie-break),
    name asc (tie-break), `id` (final tie-break).

    Records with a null/absent `popularity.forks` sort LAST (trailing bucket),
    ordered by name then `id` among themselves -- stars are meaningless without
    forks to rank against, mirroring `popularity_key`'s null-stars rule.
    """
    popularity = record.get("popularity") or {}
    forks = popularity.get("forks")
    name = record.get("name") or ""
    rid = record.get("id") or ""
    if forks is None:
        return (1, 0, 0, name, rid)
    stars = popularity.get("stars") or 0
    return (0, -forks, -stars, name, rid)


def boards_key(record):
    """Sort key for board-count ranking: `boards` (recipe count) desc, then
    `popularity_key` as the tie-break, then `id` (final tie-break).

    Records with a null/absent `boards` count sort LAST (trailing bucket),
    ordered by `popularity_key` then `id` among themselves.
    """
    boards = record.get("boards")
    rid = record.get("id") or ""
    bucket = 1 if boards is None else 0
    return (bucket, -(boards or 0)) + popularity_key(record) + (rid,)


def sort_by_mode(records, mode):
    """`records` ordered per the `?sort=` mode string (SPEC-firmware-ordering.md
    §2): `popularity` (default), `name`, `name-desc`, `forks`, `boards`. Every
    mode is backed by exactly one core comparator so `/firmware` and any future
    caller can never diverge. Unrecognized modes clamp to `popularity`."""
    if mode == "name":
        return _sort_by_name(records, descending=False)
    if mode == "name-desc":
        return _sort_by_name(records, descending=True)
    if mode == "forks":
        return sorted(records, key=forks_key)
    if mode == "boards":
        return sorted(records, key=boards_key)
    return sort_by_popularity(records)


def list_firmware():
    """Every seeded firmware record's frontmatter, plus `boards`: the number of
    recipes targeting it. Computed in one pass over `list_recipes()` via a
    `Counter` keyed by recipe firmware id -- not an O(n^2) `recipes_for_firmware`
    call per record."""
    board_counts = Counter(r["firmware"] for r in list_recipes() if r.get("firmware"))
    return [{**fm, "boards": board_counts.get(fm["id"], 0)} for fm in _records("firmware")]


def get_firmware(firmware_id):
    """One firmware record by id, or None if data/firmware/<firmware_id>/ has no firmware.md."""
    return next((fm for fm in list_firmware() if fm["id"] == firmware_id), None)


def list_recipes():
    """Every seeded recipe record's frontmatter, plus the cited `reason` text
    from its markdown body -- e.g. "ESP32 Marauder lists the M5Cardputer among
    its supported devices." -- the grounded justification for this board x
    firmware edge, never invented."""
    records = []
    for kind, path in iter_data_files():
        if kind != "recipe":
            continue
        frontmatter, body = parse_frontmatter(path)
        records.append({**frontmatter, "reason": _reason_text(body)})
    return records


def recipes_for_board(board_id):
    """Every recipe targeting the given board id."""
    return [r for r in list_recipes() if r.get("board") == board_id]


def recipes_for_firmware(firmware_id):
    """Every recipe targeting the given firmware id."""
    return [r for r in list_recipes() if r.get("firmware") == firmware_id]
