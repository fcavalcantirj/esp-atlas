"""Oracle for FIX 2 batch 2 (SPEC-serp-ctr.md §3 and §5): every firmware page listed in
docs/seo-audit/2026-11-10/page-one-zero-click.json carries an editorial `seo_title`.

For each of the 8 firmware records the title must exist, be 45-60 chars (fits TITLE_MAX so
the web never clamps it, long enough to carry the board and what it does), contain and lead
with the record's exact `name`, and be plain ASCII except an em dash. Read-only over data/.

Run: python3 -m pytest scripts/test_firmware_seo_title_batch2.py -v
"""
from __future__ import annotations
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
FIRMWARE = REPO_ROOT / "data" / "firmware"
TITLE_MIN = 45
TITLE_MAX = 60
EM_DASH = "—"

BATCH_2_FIRMWARE_IDS = [
    "tamaputer",
    "draftling",
    "mclite",
    "m5hamradio",
    "esp32-homekit-remote",
    "meshcore-cardputer-adv",
    "m5tool",
    "esphome",
]


def _frontmatter(firmware_id: str) -> dict:
    text = (FIRMWARE / firmware_id / "firmware.md").read_text(encoding="utf-8")
    _, fm, _ = text.split("---\n", 2)
    return yaml.safe_load(fm)


@pytest.mark.parametrize("firmware_id", BATCH_2_FIRMWARE_IDS)
def test_batch2_firmware_has_seo_title_within_limits_containing_name(firmware_id):
    fm = _frontmatter(firmware_id)
    title = fm.get("seo_title")
    assert isinstance(title, str) and title.strip(), f"{firmware_id}: seo_title missing"
    assert TITLE_MIN <= len(title) <= TITLE_MAX, f"{firmware_id}: {len(title)} chars: {title!r}"
    assert fm["name"] in title, f"{firmware_id}: {title!r} does not contain {fm['name']!r}"
    assert title.startswith(fm["name"]), f"{firmware_id}: {title!r} does not lead with {fm['name']!r}"


@pytest.mark.parametrize("firmware_id", BATCH_2_FIRMWARE_IDS)
def test_batch2_firmware_seo_title_is_ascii_except_em_dash(firmware_id):
    title = _frontmatter(firmware_id).get("seo_title") or ""
    stray = [c for c in title if not c.isascii() and c != EM_DASH]
    assert not stray, f"{firmware_id}: non-ASCII characters {stray!r} in {title!r}"
