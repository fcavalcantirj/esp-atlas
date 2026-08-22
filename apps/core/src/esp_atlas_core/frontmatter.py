"""Shared YAML-frontmatter parsing for the esp-atlas dataset.

Mirrors the parsing convention already used by scripts/build_index.py and
scripts/validate.py (split on the leading `---` fences, `yaml.safe_load` the
frontmatter) so every esp_atlas_core module reads `data/**/*.md` the same way.
"""
from pathlib import Path

import yaml

from esp_atlas_core.paths import DATA_DIR

# content type -> glob pattern (relative to data/), matching scripts/validate.py's TYPES
DATA_PATTERNS = {
    "soc": "socs/*/chip.md",
    "module": "modules/*/module.md",
    "board": "boards/*/*/board.md",
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


def parse_frontmatter(path):
    """Read a data/**/*.md file and return (frontmatter_dict, body_markdown)."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        return parse_frontmatter_text(text)
    except ValueError as e:
        raise ValueError(f"{path}: {e}") from e


def iter_data_files(data_dir=None):
    """Yield (type, Path) for every data/**/*.md file, type in {soc, module, board}."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    for content_type, pattern in DATA_PATTERNS.items():
        for path in sorted(root.glob(pattern)):
            yield content_type, path
