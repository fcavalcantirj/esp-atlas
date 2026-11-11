"""Oracle for FIX 2 batch 1 (SPEC-serp-ctr.md §3 and §5): every part page listed in
docs/seo-audit/2026-11-10/page-one-zero-click.json carries an editorial `seo_title`.

For each of the 9 part records the title must exist, fit TITLE_MAX (60 chars, so the web
never clamps it) and lead with the record's exact `name`. Read-only over data/.

Run: python3 -m pytest scripts/test_part_seo_title_batch1.py -v
"""
from __future__ import annotations
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
TITLE_MAX = 60

BATCH_1_PART_IDS = [
    "m5stick-s3",
    "esp32-wrover-e",
    "esp32-s31",
    "xiao-esp32s3",
    "esp32-c5-devkitc-1",
    "m5stack-papers3",
    "lolin-s3-mini",
    "esp32-devkitc-v4",
    "lolin-d32",
]


def _frontmatter(part_id: str) -> dict:
    candidates = [p for p in DATA.glob(f"**/{part_id}/*.md") if p.name in ("board.md", "module.md", "chip.md")]
    assert len(candidates) == 1, f"{part_id}: expected one record file, found {candidates}"
    text = candidates[0].read_text(encoding="utf-8")
    _, fm, _ = text.split("---\n", 2)
    return yaml.safe_load(fm)


@pytest.mark.parametrize("part_id", BATCH_1_PART_IDS)
def test_batch1_part_has_seo_title_within_limit_leading_with_name(part_id):
    fm = _frontmatter(part_id)
    title = fm.get("seo_title")
    assert isinstance(title, str) and title.strip(), f"{part_id}: seo_title missing"
    assert len(title) <= TITLE_MAX, f"{part_id}: {len(title)} chars > {TITLE_MAX}: {title!r}"
    assert title.startswith(fm["name"]), f"{part_id}: {title!r} does not start with {fm['name']!r}"
