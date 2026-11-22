"""Shared YAML-frontmatter parsing for the esp-atlas dataset.

Mirrors the parsing convention already used by scripts/build_index.py and
scripts/validate.py (split on the leading `---` fences, `yaml.safe_load` the
frontmatter) so every esp_atlas_core module reads `data/**/*.md` the same way.
"""
import copy
import os
from pathlib import Path

import yaml

from esp_atlas_core.paths import DATA_DIR

# content type -> glob pattern (relative to data/), matching scripts/validate.py's TYPES
DATA_PATTERNS = {
    "soc": "socs/*/chip.md",
    "module": "modules/*/module.md",
    "board": "boards/*/*/board.md",
    "brand": "brands/*/brand.md",
    "firmware": "firmware/*/firmware.md",
    "recipe": "recipes/*/recipe.md",
}


def parse_frontmatter_text(text):
    """Parse a full markdown document and return (frontmatter_dict, body_markdown).

    Used both by parse_frontmatter(path) below and by validate_markdown()/stdin/API
    callers that have a document in hand but no file path.
    """
    if not text.startswith("---"):
        raise ValueError("missing YAML frontmatter")
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError("malformed frontmatter fences")
    fm = yaml.safe_load(parts[1])
    body = parts[2].strip()
    return fm, body


# A deployed API serves a data/ tree that never changes within the deployment; apps/web/api/index.py sets
# ESP_ATLAS_IMMUTABLE_DATA=1 before anything reads it. There each file is parsed once per process and the
# directory listed once (2026-11-21: re-parsing ~640 YAML files made an uncached firmware page take 2.3-3.9 s,
# and Google held back crawling new pages). Anywhere else (Jr, local runs, tests) every call reads the disk.
_PARSED: dict = {}
_FILES: dict = {}


def _immutable() -> bool:
    return os.environ.get("ESP_ATLAS_IMMUTABLE_DATA") == "1"


def parse_frontmatter(path):
    """Read a data/**/*.md file and return (frontmatter_dict, body_markdown). With immutable data the parse
    is kept per process and every caller gets its own copy of the frontmatter."""
    key = str(path)
    if _immutable() and key in _PARSED:
        fm, body = _PARSED[key]
        return copy.deepcopy(fm), body
    text = Path(path).read_text(encoding="utf-8")
    try:
        fm, body = parse_frontmatter_text(text)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from e
    if _immutable():
        _PARSED[key] = (copy.deepcopy(fm), body)
    return fm, body


QUARANTINE_FILE = "quarantine.json"


def _quarantined_recipes(root):
    """The recipe ids data/quarantine.json hides: an empty set when the file is absent (nothing quarantined),
    None when it exists but cannot be read as {"version": 1, "recipes": {id: entry}, ...} (fail closed)."""
    path = Path(root) / QUARANTINE_FILE
    if not path.exists():
        return set()
    try:
        import json
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("version") != 1 or not isinstance(doc.get("recipes"), dict):
        return None
    return set(doc["recipes"])


def _served(root, files):
    """What the SERVING process exposes (Jr redesign plan, 2026-11-22): every record except the quarantined
    recipes. An unreadable quarantine file hides every build-target fact (fail closed) and nothing else."""
    hidden = _quarantined_recipes(root)
    out = []
    for kind, path in files:
        if kind == "recipe":
            if hidden is None:
                fm, _body = parse_frontmatter(path)
                if isinstance(fm, dict) and fm.get("status") == "build-target":
                    continue
            elif path.parent.name in hidden:
                continue
        out.append((kind, path))
    return out


def iter_data_files(data_dir=None):
    """Yield (type, Path) for every data/**/*.md file, type in {soc, module, board,
    brand, firmware, recipe}. In the serving process (ESP_ATLAS_IMMUTABLE_DATA=1) the recipes that
    data/quarantine.json hides are left out; Jr, validators and checkers (no flag) see every record."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    if _immutable():
        key = str(root)
        if key not in _FILES:
            _FILES[key] = _served(root, [(t, p) for t, pattern in DATA_PATTERNS.items() for p in sorted(root.glob(pattern))])
        yield from _FILES[key]
        return
    for content_type, pattern in DATA_PATTERNS.items():
        for path in sorted(root.glob(pattern)):
            yield content_type, path
