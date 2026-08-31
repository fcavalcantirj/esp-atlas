"""EspAtlas Jr — device-name -> catalogued board_id map (feeds scorer.py's zero-LLM scorer).

Hand-curated from `data/boards/*/*/board.md` (see tools.board_soc for the ground-truth chip
lookup this feeds). Ordered list of (regex, board_id): first match wins, so more specific
patterns (StickC **Plus2**) are listed before looser ones. Deliberately does NOT map a bare
"StickC Plus" (no "2") or a bare "Core" (no "2"/"S3") to anything — those variants are not
catalogued (only m5stick-cplus2 and m5stack-core2/m5stack-cores3 exist), and guessing would
repeat the exact wrong-chip class of bug this map exists to kill (DECISION-LOG.md #71).
"""
from __future__ import annotations
import re

DEVICE_BOARD_PATTERNS: list[tuple[str, str]] = [
    (r"stick\s*c\s*-?\s*plus\s*2|stickcp2\b", "m5stick-cplus2"),
    (r"stick\s*s3", "m5stick-s3"),
    (r"atom\s*s3\s*lite", "m5atoms3-lite"),
    (r"atom\s*s3", "m5atoms3"),
    (r"core\s*s3", "m5stack-cores3"),
    (r"core\s*2\b", "m5stack-core2"),
    (r"cardputer", "m5cardputer"),          # covers "Cardputer", "Cardputer ADV", "Cardputer & ADV"
    (r"stamp\s*s3", "m5stamp-s3"),
    (r"stamp\s*c3", "m5stamp-c3"),
    (r"nano\s*c6", "m5nanoc6"),
    (r"m5\s*-?\s*dial\b", "m5dial"),         # requires the "m5" prefix — bare "dial" is too generic to trust,
                                              # and this also catches the fused "M5Dial" spelling a bare \bdial\b
                                              # word-boundary match misses (no boundary between "5" and "d")
    (r"t-?deck", "lilygo-t-deck"),
]

# Deliberately the loosest, catch-all pattern in the whole map — matches bare "Atom" whenever it
# isn't immediately "Atom S3" — kept OUT of DEVICE_BOARD_PATTERNS and tried only as an absolute
# last resort (see device_from_text) so it can never shadow a real signal elsewhere.
_WEAK_FALLBACK_PATTERN = (r"\batom\b(?!\s*s3)", "m5atom-lite")

# Only launcher `category` values that map UNAMBIGUOUSLY to one catalogued board — used as a
# fallback when `name` (and the repo description) carry no device token at all. "stickc" and
# "core" are deliberately excluded: the launcher bins StickC/StickC-Plus/StickC-Plus2 (and
# Core/Core2/CoreS3) into one coarse category, so it can't tell us WHICH board without a name
# token — that ambiguity is exactly the CatHack/#71 failure mode.
CATEGORY_BOARD_FALLBACK: dict[str, str] = {
    "atoms3": "m5atoms3",
    "core2": "m5stack-core2",
    "cores3": "m5stack-cores3",
    "cardputer": "m5cardputer",
    "stamps3": "m5stamp-s3",
}


def device_from_text(*texts: str | None) -> str | None:
    """First catalogued board_id whose pattern matches, `texts` tried IN ORDER (name first, then
    any fallback text like a repo description/README title) — `name` is authoritative: THIS
    catalog entry's own title (e.g. "MK75-Watch **for Core2**") must win over a repo-level
    description that may generically list every board variant the underlying repo supports
    across ALL its catalog listings (e.g. "Open-Source Smartwatch Software for M5Stack Core2 /
    CoreS3" — that sentence describes the whole repo, not this specific Core2-titled entry; a
    global pattern-priority search that let a "CoreS3" match anywhere in that description beat
    this entry's own "Core2" name was a real at-scale regression, caught and reverted).

    The ONE exception is the catch-all bare-"atom" pattern (_WEAK_FALLBACK_PATTERN, deliberately
    excluded from DEVICE_BOARD_PATTERNS): it is tried only as an absolute last resort, AFTER every
    real pattern has been tried against every text — so a bare "atom" hit in `name` (e.g. "Atom
    Plane Tracker") can never shadow a real "atom s3" signal sitting in `description` ("...for the
    M5Stack Atom S3R...", an ESP32-S3 board wrongly derived as the plain-ESP32 m5atom-lite before
    this fix). None if no text names a catalogued device."""
    lowered = [t.lower() for t in texts if t]
    for low in lowered:
        for pattern, board_id in DEVICE_BOARD_PATTERNS:
            if re.search(pattern, low):
                return board_id
    pattern, board_id = _WEAK_FALLBACK_PATTERN
    for low in lowered:
        if re.search(pattern, low):
            return board_id
    return None


def device_from_category(category: str | None) -> str | None:
    """Fallback board_id from the launcher's coarse `category` field — only for categories
    that map to exactly one catalogued board (see CATEGORY_BOARD_FALLBACK)."""
    return CATEGORY_BOARD_FALLBACK.get((category or "").lower())
