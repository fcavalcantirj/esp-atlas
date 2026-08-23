"""Shared record validation for esp-atlas data.

Single implementation behind scripts/validate.py (the CI gate), the `esp-atlas
validate` CLI command, and the API's POST /validate — so a human or agent can
self-check a proposed soc/module/board record before opening a PR, using exactly
the rules CI enforces. It checks: JSON Schema conformance against schema/<kind>.schema.json
(which itself carries the source-or-omit rule via each schema's non-empty `sources`
array), frontmatter id (and, for boards, brand) agreement with the data/ folder a
record lives in, and inheritance references (module.soc, board.module/soc)
resolving to a real record.
"""
import json
from pathlib import Path

import jsonschema
import yaml

from esp_atlas_core.frontmatter import DATA_PATTERNS, parse_frontmatter_text
from esp_atlas_core.paths import DATA_DIR, REPO_ROOT

SCHEMA_DIR = REPO_ROOT / "schema"

SCHEMA_FILES = {
    "soc": "soc.schema.json",
    "module": "module.schema.json",
    "board": "board.schema.json",
    "brand": "brand.schema.json",
    "firmware": "firmware.schema.json",
    "recipe": "recipe.schema.json",
}


def _load_schema(kind):
    if kind not in SCHEMA_FILES:
        raise ValueError(f"unknown or missing kind {kind!r}, expected one of {sorted(SCHEMA_FILES)}")
    return json.loads((SCHEMA_DIR / SCHEMA_FILES[kind]).read_text(encoding="utf-8"))


def _read_fm(path):
    try:
        fm, _body = parse_frontmatter_text(path.read_text(encoding="utf-8"))
    except (ValueError, yaml.YAMLError):
        return None
    return fm if isinstance(fm, dict) and fm.get("id") else None


def known_ids(data_dir=None):
    """Scan data/ for existing soc/module/board/firmware ids, to resolve inheritance
    refs against. Also returns `board_soc`: {board_id: resolved soc id} (via the
    board's own `soc`, or its `module`'s `soc`), used to check a recipe's
    `chip_family` against the board it targets, and `recipe_firmware_refs`: every
    firmware id referenced by at least one recipe, used by check_orphan_firmware()."""
    ids = {"soc": set(), "module": set(), "board": set(), "firmware": set()}
    root = Path(data_dir) if data_dir is not None else DATA_DIR

    module_soc = {}
    for path in root.glob(DATA_PATTERNS["module"]):
        fm = _read_fm(path)
        if fm:
            ids["module"].add(fm["id"])
            module_soc[fm["id"]] = fm.get("soc")

    for path in root.glob(DATA_PATTERNS["soc"]):
        fm = _read_fm(path)
        if fm:
            ids["soc"].add(fm["id"])

    board_soc = {}
    for path in root.glob(DATA_PATTERNS["board"]):
        fm = _read_fm(path)
        if fm:
            ids["board"].add(fm["id"])
            board_soc[fm["id"]] = fm.get("soc") or module_soc.get(fm.get("module"))

    for path in root.glob(DATA_PATTERNS["firmware"]):
        fm = _read_fm(path)
        if fm:
            ids["firmware"].add(fm["id"])

    recipe_firmware_refs = set()
    for path in root.glob(DATA_PATTERNS["recipe"]):
        fm = _read_fm(path)
        if fm and fm.get("firmware"):
            recipe_firmware_refs.add(fm["firmware"])

    ids["board_soc"] = board_soc
    ids["recipe_firmware_refs"] = recipe_firmware_refs
    return ids


def check_orphan_firmware(ids):
    """Dataset-level check (not per-file): every seeded firmware must be referenced
    by at least one recipe. Run after per-file validation via scripts/validate.py;
    an orphan firmware (zero recipes) is a hard CI error, not a warning."""
    firmware_ids = ids.get("firmware", set())
    referenced = ids.get("recipe_firmware_refs", set())
    return [
        f"orphan firmware: no recipe references '{firmware_id}'"
        for firmware_id in sorted(firmware_ids - referenced)
    ]


def _check_inheritance(fm, kind, ids):
    errors = []
    if kind == "module" and "soc" in fm and fm["soc"] not in ids["soc"]:
        errors.append(f"soc '{fm['soc']}' not found in data/socs/")
    if kind == "board":
        if "module" in fm and fm["module"] not in ids["module"]:
            errors.append(f"module '{fm['module']}' not found in data/modules/")
        if "soc" in fm and fm["soc"] not in ids["soc"]:
            errors.append(f"soc '{fm['soc']}' not found in data/socs/")
    if kind == "recipe":
        board_id, firmware_id = fm.get("board"), fm.get("firmware")
        board_ids, firmware_ids = ids.get("board", set()), ids.get("firmware", set())
        if board_id is not None and board_id not in board_ids:
            errors.append(f"board '{board_id}' not found in data/boards/")
        if firmware_id is not None and firmware_id not in firmware_ids:
            errors.append(f"firmware '{firmware_id}' not found in data/firmware/")
        if board_id in board_ids:
            board_soc = ids.get("board_soc", {}).get(board_id)
            chip_family = fm.get("chip_family")
            if board_soc is not None and chip_family is not None and chip_family != board_soc:
                errors.append(
                    f"chip_family '{chip_family}' does not match board '{board_id}' soc '{board_soc}'"
                )
    return errors


def validate_frontmatter(fm, kind, ids=None):
    """Validate one record's frontmatter dict against schema/<kind>.schema.json and
    inheritance references. There is no folder here, so id/brand-vs-folder is not checked
    (that's validate_file's job)."""
    if not isinstance(fm, dict):
        return {"ok": False, "errors": [f"frontmatter must be a mapping, got {type(fm).__name__}"]}

    try:
        schema = _load_schema(kind)
    except ValueError as e:
        return {"ok": False, "errors": [str(e)]}

    errors = []
    try:
        jsonschema.validate(fm, schema)
    except jsonschema.ValidationError as e:
        errors.append(e.message)

    errors.extend(_check_inheritance(fm, kind, known_ids() if ids is None else ids))
    return {"ok": not errors, "errors": errors}


def _parse_and_validate(text, kind, ids):
    try:
        fm, _body = parse_frontmatter_text(text)
    except (ValueError, yaml.YAMLError) as e:
        return None, kind, [str(e)]

    if kind is None:
        kind = fm.get("type") if isinstance(fm, dict) else None
    if kind not in SCHEMA_FILES:
        return fm, kind, [f"unknown or missing 'type' in frontmatter: {kind!r}"]

    result = validate_frontmatter(fm, kind, ids=ids)
    return fm, kind, result["errors"]


def validate_markdown(text, kind=None, ids=None):
    """Validate a full markdown document (frontmatter + body). `kind` is read from
    the frontmatter's `type` field unless given explicitly."""
    _fm, kind, errors = _parse_and_validate(text, kind, ids)
    return {"ok": not errors, "errors": errors, "kind": kind}


def validate_file(path, kind=None, ids=None):
    """Validate a data/**/*.md file: everything validate_markdown() checks, plus the
    folder-vs-frontmatter id (and, for boards, brand) agreement scripts/validate.py
    has always enforced."""
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    fm, kind, errors = _parse_and_validate(text, kind, ids)
    errors = list(errors)

    if isinstance(fm, dict) and kind in SCHEMA_FILES:
        folder_id = path.parent.name
        if fm.get("id") != folder_id:
            errors.append(f"id '{fm.get('id')}' != folder '{folder_id}'")
        if kind == "board":
            brand_dir = path.parent.parent.name
            if fm.get("brand") != brand_dir:
                errors.append(f"brand '{fm.get('brand')}' != folder '{brand_dir}'")

    return {"ok": not errors, "errors": errors, "kind": kind}
