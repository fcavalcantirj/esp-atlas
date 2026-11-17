"""EspAtlas Jr — the catalogued boards a text names, from the catalog's own vocabulary (jr/board_names.py).

Why (2026-11-17, measured): the admission scorer's device vocabulary was jr/device_map.py, 13 hand-written
regexes covering 14 of the catalog's 118 boards, all M5Stack. "Heltec Wireless Tracker", "LilyGO T-Display
S3" or "M5StickC" in a repo's own description named no catalogued device, and the firmware was rejected
`no_board_evidence` — 92 of the 130 topic rejects on main, several above 200 stars. The catalog-derived
resolver (jr/board_alias.py) knew every one of those boards but served only the evidence gate.

This module is the one rule for "which catalogued boards does this prose name", built from data/boards
itself (board_alias.atlas_boards: id, name, aka, brand, soc), deterministic, no model:

  - A board is named by a WHOLE-WORD match of one of its terms, a separator optional between every
    character ("T-Display S3", "tdisplay-s3", "T_DISPLAY_S3" and "M5Stick C Plus" all count; never
    "rust-embedded" for the T-Embed — a compact-containment rule did, the one false positive in the
    spike). A term is: the catalog id (brand-prefixed by construction), the brand plus the catalog name
    ("heltec wireless tracker", "m5stack fire"), any aka (toolchain ids, exact), and the bare name only
    when it carries a digit (an "S3"/"V3"/"2": "T-Display-S3", "StickC-Plus2", "Inkplate 6"). A bare
    name without a digit ("Fire", "Core", "Wireless Tracker", "T-Deck") is English or a product line and
    needs its brand in front — jr/device_map.py, which runs first, keeps the precise M5Stack sibling rules.
  - Chip-only terms (`esp32s3`) and generic words (board_alias._GENERIC) never name a board; terms
    shorter than MIN_TERM alphanumerics never count.
  - Specific beats general: a match whose span lies inside another board's match is dropped ("T-Display
    S3" names the T-Display-S3, not also the T-Display).
  - URLs, library/SDK references and #includes are not prose (autoreview._prose), so "M5Cardputer Arduino
    library" is a dependency, not a device.

The caller (jr/scorer.py) admits only when exactly ONE board is named; several is `ambiguous_board`, a
skip, never a guess. The SOC cross-check and the device-build evidence gate still run after it.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import autoreview
import board_alias

MIN_TERM = 5          # alphanumerics; "s3", "d32" alone never name a board
_SEP = r"[-_ ]?"


def _parts(term: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (term or "").lower())


def _qualifies(parts: list[str]) -> bool:
    compact = "".join(parts)
    return (len(compact) >= MIN_TERM and not board_alias.chip_only(compact)
            and compact not in board_alias._GENERIC)


def _pattern(parts: list[str]) -> re.Pattern:
    """Whole-word, a separator optional between EVERY character: the catalog writes "m5stick-cplus",
    a README "M5Stick C Plus" or "M5StickCPlus"; all three are the one board."""
    return re.compile(r"(?<![a-z0-9])" + _SEP.join(map(re.escape, "".join(parts))) + r"(?![a-z0-9])")


def _terms(board: dict) -> list[list[str]]:
    """The term part-lists a board may be named by (see the module docstring for the rule)."""
    out: list[list[str]] = []
    bid, name, brand = board.get("id") or "", board.get("name") or "", board.get("brand") or ""
    out.append(_parts(bid))
    for prefix in sorted({brand, *board_alias._BRAND_PREFIXES.get(brand, set())}):
        if prefix:
            out.append(_parts(prefix) + _parts(name))
    for aka in board.get("aka") or []:
        out.append(_parts(aka))
    if re.search(r"\d", name):
        out.append(_parts(name))
    seen, uniq = set(), []
    for p in out:
        key = tuple(p)
        if p and key not in seen and _qualifies(p):
            seen.add(key)
            uniq.append(p)
    return uniq


@lru_cache(maxsize=4)
def _table(root: Path | None) -> list[tuple[str, re.Pattern]]:
    boards = board_alias.atlas_boards(root)
    return [(bid, _pattern(p)) for bid, b in sorted(boards.items()) for p in _terms(b)]


def clear_caches() -> None:
    _table.cache_clear()


def boards_named_in(text: str | None, root: Path | None = None) -> list[str]:
    """Sorted ids of the catalogued boards `text` names (prose only; see the module docstring).
    `root` is the catalog root (default: the module's own repo), as board_alias.atlas_boards takes it."""
    low = autoreview._prose(text or "").lower()
    if not low.strip():
        return []
    spans: list[tuple[int, int, str]] = []
    for bid, pat in _table(root):
        for m in pat.finditer(low):
            spans.append((m.start(), m.end(), bid))
    named = set()
    for s, e, bid in spans:
        inside = any(bid != o and os_ <= s and e <= oe and (oe - os_) > (e - s) for os_, oe, o in spans)
        if not inside:
            named.add(bid)
    return sorted(named)
