"""Boards admitted after the vendor resolver maps were written (2026-09-10/11) resolve to the vendor
page their own record already cites (incident 214785f8dec6: unmapped boards were skipped
doc-unreachable and cooled forever, so the backfill lane produced nothing)."""
from __future__ import annotations

from pathlib import Path

import pytest

import board_backfill as bb

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

CITED_PAGES = {
    ("adafruit", "adafruit-pycamera-s3"): "https://learn.adafruit.com/adafruit-memento-camera-board",
    ("m5stack", "m5stack-core"): "https://docs.m5stack.com/en/core/basic",
    ("m5stack", "m5stack-core-aws"): "https://docs.m5stack.com/en/core/core2_for_aws",
    ("m5stack", "m5stack-cores3-se"): "https://docs.m5stack.com/en/products/sku/K128-SE",
    ("m5stack", "m5stick-c"): "https://docs.m5stack.com/en/core/m5stickc",
    ("seeed", "xiao-esp32c5"): "https://wiki.seeedstudio.com/xiao_esp32c5_getting_started/",
    ("seeed", "xiao-esp32s3-sense"): "https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/",
}


@pytest.mark.parametrize("brand,board_id", sorted(CITED_PAGES))
def test_board_resolves_to_the_page_its_record_cites(brand, board_id):
    path = DATA / "boards" / brand / board_id / "board.md"
    fm, _ = bb.parse_frontmatter(path)
    cited = {s.get("url") for s in fm.get("sources") or [] if isinstance(s, dict)}
    url = CITED_PAGES[(brand, board_id)]
    assert url in cited
    assert bb.VENDOR_DOC_RESOLVERS[brand](board_id, bb.resolve_soc(fm, DATA)) == [url]


@pytest.mark.parametrize("board_id", ["m5stack-fire", "m5stick-cplus"])
def test_board_whose_pinmap_section_leads_with_another_image_stays_unmapped(board_id):
    # Their PinMap section's first image is an IMU axis diagram (fire) or the schematic
    # (StickC Plus): mapping them would write that as the board's pinout.
    assert bb.VENDOR_DOC_RESOLVERS["m5stack"](board_id, "esp32") == []
