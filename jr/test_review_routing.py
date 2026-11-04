"""Tests for jr/review_routing.py — the ONE risk classifier: review (owner merges) or auto.

Pure function over the staged diff and the stage results: no git, no gh, no network.

Run: cd jr && python3 -m pytest test_review_routing.py -v
"""
from __future__ import annotations

import review_routing as rr
from review_routing import Change

FIRMWARE_MD = """---
id: tool
type: firmware
name: Tool
url: https://github.com/o/tool
popularity:
  stars: 95
  forks: 10
  as_of: '2026-09-20'
sources:
- field: '*'
  url: https://github.com/o/tool
  verified: '2026-08-27'
- field: popularity
  url: https://github.com/o/tool
  verified: '2026-09-01'
summary: A tool.
---

Body text.
"""

BOARD_MD = """---
id: b
type: board
name: B
usb:
  connector: usb-c
  bridge: native
usb_serial: native-usb-serial-jtag
getting_started: https://example.com/b
sources:
- field: '*'
  url: https://example.com/b
  verified: '2026-08-27'
---
"""


def _star_refresh(text: str) -> str:
    return (text.replace("stars: 95", "stars: 120").replace("forks: 10", "forks: 12")
            .replace("as_of: '2026-09-20'", "as_of: '2026-11-04'")
            .replace("verified: '2026-09-01'", "verified: '2026-11-04'"))


# --- AUTO: low-risk only -------------------------------------------------------------------------

def test_bookkeeping_only_is_auto():
    route = rr.classify([Change("jr/proposed_ledger.json", "M"), Change("jr/board_cooldown.json", "M"),
                         Change("docs/telemetry/data-trend.jsonl", "M"), Change("docs/telemetry/data-2026-11-04.md", "A")])
    assert route.route == rr.AUTO and not route.review and route.reasons == []


def test_demand_and_signals_snapshots_are_auto():
    route = rr.classify([Change("docs/demand/2026-11-04.json", "A"), Change("docs/demand/unresolved.json", "M"),
                         Change("data/firmware/tool/signals.json", "M"), Change("data/firmware/old/signals.json", "A")])
    assert route.route == rr.AUTO


def test_a_star_and_date_refresh_of_an_existing_record_is_auto():
    route = rr.classify([Change("data/firmware/tool/firmware.md", "M", FIRMWARE_MD, _star_refresh(FIRMWARE_MD))])
    assert route.route == rr.AUTO, route.reasons


# --- REVIEW --------------------------------------------------------------------------------------

def test_a_new_firmware_entry_is_review():
    route = rr.classify([Change("data/firmware/newtool/firmware.md", "A"), Change("data/firmware/newtool/signals.json", "A"),
                         Change("jr/proposed_ledger.json", "M")])
    assert route.route == rr.REVIEW and route.review
    assert any("new firmware" in r and "newtool" in r for r in route.reasons)


def test_a_new_or_changed_recipe_is_review():
    for status in ("A", "M"):
        route = rr.classify([Change("data/recipes/b__tool/recipe.md", status, "x", "y")])
        assert route.route == rr.REVIEW and any("recipe" in r for r in route.reasons)


def test_a_flashing_field_change_on_a_board_is_review_and_names_the_field():
    new = BOARD_MD.replace("usb_serial: native-usb-serial-jtag", "usb_serial: cp2102")
    route = rr.classify([Change("data/boards/x/b/board.md", "M", BOARD_MD, new)])
    assert route.route == rr.REVIEW and any("usb_serial" in r and "flashing" in r for r in route.reasons)
    added = BOARD_MD.replace("getting_started:", "download_mode:\n  mode: auto\ngetting_started:")
    assert rr.classify([Change("data/boards/x/b/board.md", "M", BOARD_MD, added)]).route == rr.REVIEW


def test_a_content_edit_beyond_a_refresh_is_review_when_unsure():
    new = _star_refresh(FIRMWARE_MD).replace("summary: A tool.", "summary: A different tool.")
    assert rr.classify([Change("data/firmware/tool/firmware.md", "M", FIRMWARE_MD, new)]).route == rr.REVIEW
    body = FIRMWARE_MD.replace("Body text.", "Other body.")
    assert rr.classify([Change("data/firmware/tool/firmware.md", "M", FIRMWARE_MD, body)]).route == rr.REVIEW
    # a new popularity source is a new citation, not a refresh of one
    cited = FIRMWARE_MD.replace("summary: A tool.", "- field: summary\n  url: https://x\n  verified: '2026-11-04'\nsummary: A tool.")
    assert rr.classify([Change("data/firmware/tool/firmware.md", "M", FIRMWARE_MD, cited)]).route == rr.REVIEW


def test_an_unreadable_record_diff_is_review():
    assert rr.classify([Change("data/firmware/tool/firmware.md", "M")]).route == rr.REVIEW
    assert rr.classify([Change("data/firmware/tool/firmware.md", "M", "", "")]).route == rr.REVIEW
    assert rr.classify([Change("data/firmware/tool/firmware.md", "M", "no frontmatter", FIRMWARE_MD)]).route == rr.REVIEW


def test_a_path_off_the_low_risk_list_is_review():
    for change in (Change("data/boards/x/new/board.md", "A"), Change("data/board_universe.json", "M"),
                   Change("apps/core/src/x.py", "M"), Change("jr/state/etags.json", "D"),
                   Change("data/firmware/tool/signals.json", "D"), Change("docs/demand/2026-11-04.json", "D")):
        assert rr.classify([change]).route == rr.REVIEW, change


def test_an_empty_staged_diff_is_review_fail_closed():
    route = rr.classify([])
    assert route.route == rr.REVIEW and route.reasons


def test_a_device_evidence_needs_review_item_is_review_even_on_a_bookkeeping_diff():
    stages = [{"name": "admit_topics", "needs_human": False,
               "review": [{"id": "zap", "repo": "z/zap", "kind": "release_bin", "url": "u", "why": "w"}]}]
    route = rr.classify([Change("jr/proposed_ledger.json", "M")], stages)
    assert route.route == rr.REVIEW and any("needs_review" in r and "z/zap" in r for r in route.reasons)


def test_a_stage_or_caller_asking_for_a_human_is_review():
    assert rr.classify([Change("jr/proposed_ledger.json", "M")], [{"name": "admit", "needs_human": True}]).route == rr.REVIEW
    route = rr.classify([Change("jr/proposed_ledger.json", "M")], needs_human=True)
    assert route.route == rr.REVIEW and any("needs_human" in r for r in route.reasons)


def test_has_review_label_reads_gh_label_shapes():
    assert rr.has_review_label({"labels": [{"name": "jr-review"}]})
    assert rr.has_review_label({"labels": [{"name": "JR-Review"}, {"name": "x"}]})
    assert not rr.has_review_label({"labels": [{"name": "veto"}]})
    assert not rr.has_review_label({"labels": None}) and not rr.has_review_label({})
    assert not rr.has_review_label({"labels": ["jr-review", None]})   # malformed entries never match
