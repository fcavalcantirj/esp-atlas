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
    "module": ("data/modules/*/module.md", "module.schema.json"),
    "board": ("data/boards/*/*/board.md", "board.schema.json"),
}


def parse_frontmatter(path):
    txt = open(path, encoding="utf-8").read()
    if not txt.startswith("---"):
        raise ValueError("missing YAML frontmatter")
    return yaml.safe_load(txt.split("---", 2)[1])


def main():
    total = errors = 0
    ids = {"soc": set(), "module": set()}
    records = []  # (rel, type, fm) for the post-pass reference check

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
                # board brand must match its parent folder
                if tname == "board":
                    brand_dir = os.path.basename(os.path.dirname(os.path.dirname(path)))
                    if fm.get("brand") != brand_dir:
                        raise ValueError(f"brand '{fm.get('brand')}' != folder '{brand_dir}'")
                if tname in ids:
                    ids[tname].add(fm["id"])
                records.append((rel, tname, fm))
            except (jsonschema.ValidationError, ValueError, yaml.YAMLError) as e:
                errors += 1
                msg = getattr(e, "message", str(e))
                print(f"  ✗ {rel}: {msg}")

    # inheritance integrity: every module.soc and board.module/soc must resolve
    for rel, tname, fm in records:
        if tname == "module" and fm["soc"] not in ids["soc"]:
            errors += 1
            print(f"  ✗ {rel}: soc '{fm['soc']}' not found in data/socs/")
        if tname == "board":
            if "module" in fm and fm["module"] not in ids["module"]:
                errors += 1
                print(f"  ✗ {rel}: module '{fm['module']}' not found in data/modules/")
            if "soc" in fm and fm["soc"] not in ids["soc"]:
                errors += 1
                print(f"  ✗ {rel}: soc '{fm['soc']}' not found in data/socs/")

    print(f"\n{total - errors}/{total} valid, {errors} error(s)")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
