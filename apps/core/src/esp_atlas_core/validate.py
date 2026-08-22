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
}


def _load_schema(kind):
    if kind not in SCHEMA_FILES:
        raise ValueError(f"unknown or missing kind {kind!r}, expected one of {sorted(SCHEMA_FILES)}")
    return json.loads((SCHEMA_DIR / SCHEMA_FILES[kind]).read_text(encoding="utf-8"))


def known_ids(data_dir=None):
    """Scan data/ for existing soc and module ids, to resolve inheritance refs against."""
    ids = {"soc": set(), "module": set()}
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    for kind in ids:
        for path in root.glob(DATA_PATTERNS[kind]):
            try:
                fm, _body = parse_frontmatter_text(path.read_text(encoding="utf-8"))
            except (ValueError, yaml.YAMLError):
                continue
            if isinstance(fm, dict) and fm.get("id"):
                ids[kind].add(fm["id"])
    return ids


def _check_inheritance(fm, kind, ids):
    errors = []
    if kind == "module" and "soc" in fm and fm["soc"] not in ids["soc"]:
        errors.append(f"soc '{fm['soc']}' not found in data/socs/")
    if kind == "board":
        if "module" in fm and fm["module"] not in ids["module"]:
            errors.append(f"module '{fm['module']}' not found in data/modules/")
        if "soc" in fm and fm["soc"] not in ids["soc"]:
            errors.append(f"soc '{fm['soc']}' not found in data/socs/")
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
