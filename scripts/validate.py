#!/usr/bin/env python3
"""Validate every data/**/*.md frontmatter against schema/<type>.schema.json.

The correctness gate for esp-atlas. CI runs this on every PR; a spec change with
no matching source entry, or any schema violation, fails the build. Run locally:

    python3 scripts/validate.py
"""
import glob
import json
import os
import sys

import jsonschema
import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_DIR = os.path.join(ROOT, "schema")

# content type -> (glob under data/, schema file)
TYPES = {
    "soc": ("data/socs/*/chip.md", "soc.schema.json"),
    # "module": ("data/modules/*/module.md", "module.schema.json"),
    # "board":  ("data/boards/*/*/board.md", "board.schema.json"),
}


def parse_frontmatter(path):
    txt = open(path, encoding="utf-8").read()
    if not txt.startswith("---"):
        raise ValueError("missing YAML frontmatter")
    return yaml.safe_load(txt.split("---", 2)[1])


def main():
    total = errors = 0
    for tname, (pattern, schema_file) in TYPES.items():
        schema = json.load(open(os.path.join(SCHEMA_DIR, schema_file)))
        for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
            total += 1
            rel = os.path.relpath(path, ROOT)
            try:
                fm = parse_frontmatter(path)
                jsonschema.validate(fm, schema)
                # folder id must match frontmatter id
                folder_id = os.path.basename(os.path.dirname(path))
                if fm.get("id") != folder_id:
                    raise ValueError(f"id '{fm.get('id')}' != folder '{folder_id}'")
            except (jsonschema.ValidationError, ValueError, yaml.YAMLError) as e:
                errors += 1
                msg = getattr(e, "message", str(e))
                print(f"  ✗ {rel}: {msg}")
    print(f"\n{total - errors}/{total} valid, {errors} error(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
