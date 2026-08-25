"""Firmware + recipe accessors — read data/firmware/ and data/recipes/ directly.

Deliberately separate from `parts`: like brands (see esp_atlas_core.brands),
firmware and recipes are not searchable/filterable parts, never indexed into
esp-atlas.db (see esp_atlas_core.index_build.build_index). The dataset is small
(low tens of records), so these read straight off disk on every call, the same
way esp_atlas_core.validate.known_ids() scans data/ rather than a build artifact.

    list_firmware()                          # -> [{"id": "esp32marauder", ...}, ...]
    get_firmware("esp32marauder")             # -> {"id": "esp32marauder", ...} or None
    recipes_for_board("m5cardputer")          # -> [{"id": "m5cardputer__esp32marauder", ...}, ...]
    recipes_for_firmware("esp32marauder")     # -> [{"id": "m5cardputer__esp32marauder", ...}, ...]
"""
from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter


def _records(kind):
    return [parse_frontmatter(path)[0] for k, path in iter_data_files() if k == kind]


def _reason_text(body):
    """A recipe's cited justification: the markdown body minus its leading
    "# board x firmware" heading, which only repeats what the frontmatter
    already states."""
    heading, _, rest = body.partition("\n")
    return rest.strip() if heading.strip().startswith("#") else body.strip()


def list_firmware():
    """Every seeded firmware record's frontmatter."""
    return _records("firmware")


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
