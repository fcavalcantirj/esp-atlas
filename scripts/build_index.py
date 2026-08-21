#!/usr/bin/env python3
"""Compile all data/**/*.md frontmatter into a single index.json.

This is the always-fresh query artifact. CI runs it on every merge to main and
publishes index.json (GitHub Pages / release asset) so the site can fetch ONE
small file and answer structured queries live — no database to sync. The chat
layer fetches individual .md files on demand for grounded, cited answers.

    python3 scripts/build_index.py            # -> index.json
"""
import glob
import json
import os

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERNS = ["data/socs/*/chip.md", "data/modules/*/module.md", "data/boards/*/*/board.md"]


def main():
    records = []
    for pattern in PATTERNS:
        for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
            txt = open(path, encoding="utf-8").read()
            fm = yaml.safe_load(txt.split("---", 2)[1])
            fm["_path"] = os.path.relpath(path, ROOT)
            records.append(fm)
    index = {"schema_version": 1, "count": len(records), "records": records}
    out = os.path.join(ROOT, "index.json")
    json.dump(index, open(out, "w"), indent=2, ensure_ascii=False)
    print(f"wrote index.json — {len(records)} record(s)")


if __name__ == "__main__":
    main()
