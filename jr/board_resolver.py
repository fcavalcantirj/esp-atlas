"""EspAtlas Jr — firmware-manifest board resolver (jr/board_resolver.py).

Phase 1 (SPEC-firmware-board-mapping.md §4 + §6). A firmware's supported-board sources
(a repo `boards/<vendor>/<board>/` manifest dir, a README device table, ...) name boards
the way the repo's author typed them — `m5stack_sticks3`, `esp32_S3_DevKitC_1`,
`dfrobot_firebeetle_2_ESP32_S3` — not the way the esp-atlas catalog does
(`m5stick-s3`, `esp32-s3-devkitc-1`, `firebeetle-2-esp32-s3`). This module is the ONE
place that translation lives for that source domain, and it is deterministic: no model,
no fuzzy scoring, no hardcoded board list — the catalog is read live from `data/boards/`
via `board_alias.atlas_boards()` (the same source `esp_atlas_core.frontmatter`'s
`DATA_PATTERNS["board"]` glob reads), so a new catalog board is pickable up without a
code change here.

THE HARD RULE (the whole point of this module, SPEC §4): resolve to a BOARD, never a
SoC. `board_alias.chip_only()` rejects a raw name that names only a chip family
(`esp32`, `esp32-s3`, `esp32-p4`, `esp32-c5`, `esp32-c6`, ...) before any board matching
runs — a fabricated board edge is worse than a gap (SPEC §8).

Matching, in order:
  1. exact — compact(raw) equals a catalog board's compact id/name/aka, or one of those
     with a redundant vendor shorthand stripped (`m5stack-cores3` bakes the full
     "m5stack-" vendor into its id; `m5stick-s3` bakes the short "m5" into both id and
     name — SEEDING that inconsistency into one lookup table beats special-casing each
     board). Ambiguous exact matches (>1 board) refuse rather than guess.
  2. contain — a catalog board's (possibly debranded) compact key appears inside
     compact(raw) with only a vendor prefix (the board's own brand, from
     `board_alias._BRAND_PREFIXES`) and/or a memory-SKU suffix around it — reusing
     `board_alias`'s own containment rule verbatim, because "the same board, named with
     its vendor folder prepended" is exactly the shape that rule already exists for.
     Ambiguous containment (>1 board) refuses rather than guess.

Unresolved names are never silently dropped: `resolve_boards()` surfaces them as a
`candidate` list for a human (or a later phase) to review — SPEC §4's "growth lever, not
an error to swallow."

This module never writes.
"""
from __future__ import annotations

import board_alias as ba


def _all_keys(board: dict) -> set[str]:
    """id/name/aka compact keys, plus each debranded variant where a leading vendor
    shorthand (board_alias._BRAND_PREFIXES) is baked into the key itself — e.g.
    'm5sticks3' (id AND name, both bake in the "m5" shorthand) -> also 'sticks3', so a
    raw name that spells the vendor out in full ('m5stack_sticks3') still contains it."""
    base = ba._atlas_compact_keys(board)
    prefixes = ba._BRAND_PREFIXES.get(board["brand"], set())
    debranded = set()
    for key in base:
        for prefix in prefixes:
            if key.startswith(prefix) and len(key) - len(prefix) >= ba.MIN_CONTAIN:
                debranded.add(key[len(prefix):])
    return base | debranded


def resolve(raw_name: str | None, vendor: str | None = None) -> str | None:
    """Map one raw supported-board reference (a manifest dir name, a README device
    cell) to a catalog board id, or None when it doesn't resolve — to a board, never a
    SoC (board_alias.chip_only rejects bare chip-family names up front)."""
    if not raw_name:
        return None
    if ba.chip_only(raw_name):
        return None                          # a SoC-only reference is never a board

    compact_raw = ba.compact((vendor or "") + raw_name)
    boards = ba.atlas_boards()

    exact = [b for b in boards.values() if compact_raw in _all_keys(b)]
    if len(exact) == 1:
        return exact[0]["id"]
    if len(exact) > 1:
        return None                          # ambiguous exact match: refuse, don't guess

    allowed_vendor = {ba.compact(vendor)} if vendor else set()
    contained = []
    for b in boards.values():
        allowed_prefixes = {""} | ba._BRAND_PREFIXES.get(b["brand"], set()) | {ba.compact(b["brand"])} | allowed_vendor
        for k in _all_keys(b):
            if len(k) < ba.MIN_CONTAIN or k in ba._GENERIC or ba.chip_only(k):
                continue
            if ba._contains_as_same_board(compact_raw, k, allowed_prefixes):
                contained.append(b)
                break
    if len(contained) == 1:
        return contained[0]["id"]
    return None                              # no match, or an ambiguous one: refuse


def resolve_boards(raw_refs: list[str]) -> dict[str, dict[str, str] | list[str]]:
    """Resolve a batch of raw supported-board references. Never drops an unresolved
    ref — it becomes a candidate for a human/Jr to review (SPEC §4), not a silent gap."""
    resolved: dict[str, str] = {}
    unresolved: list[str] = []
    for raw in raw_refs:
        board_id = resolve(raw)
        if board_id:
            resolved[raw] = board_id
        else:
            unresolved.append(raw)
    return {"resolved": resolved, "unresolved": unresolved}
