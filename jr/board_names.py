"""EspAtlas Jr — the catalogued boards a text names, from the catalog's own vocabulary (jr/board_names.py).

Why (2026-11-17, measured): the admission scorer's device vocabulary was jr/device_map.py, 13 hand-written
regexes covering 14 of the catalog's 118 boards, all M5Stack. "Heltec Wireless Tracker", "LilyGO T-Display
S3" or "M5StickC" in a repo's own description named no catalogued device, and the firmware was rejected
`no_board_evidence` — 92 of the 130 topic rejects on main, several above 200 stars. The catalog-derived
resolver (jr/board_alias.py) knew every one of those boards but served only the evidence gate.

This module is the one rule for "which catalogued boards does this prose name", built from data/boards
itself (board_alias.atlas_boards: id, name, aka, brand, soc), deterministic, no model:

  - A board is named by a WHOLE-WORD match of one of its terms. A term is: the catalog id, the brand
    plus the catalog name ("heltec wireless tracker", "m5stack fire"), any aka (toolchain ids), and the
    bare name only when it carries a digit (an "S3"/"V3"/"2": "T-Display-S3", "StickC-Plus2",
    "Inkplate 6"). A bare name without a digit ("Fire", "Core", "Wireless Tracker", "T-Deck") is English
    or a product line and needs its brand in front — jr/device_map.py, which runs first, keeps the
    precise M5Stack sibling rules.
  - How a term may be spelled. With its brand: a separator optional between every character
    ("T-Display S3", "tdisplay-s3", "M5Stick C Plus"; never "rust-embedded" for the T-Embed). A coined
    brandless name ("PaperS3", "TinyS3"): only at the catalog's own word breaks. A name that starts with
    a chip ("ESP32-Ethernet-Kit", "ESP32-S3-DevKitC-1") reads as plain English once its hyphens go
    ("any ESP32 Ethernet kit"), so it counts only spelled with the catalog's hyphens or underscores.
  - WHAT FOLLOWS THE NAME DECIDES. Vendors sell siblings whose name is a catalogued name plus a word
    ("T-Beam Supreme", an ESP32-S3; "T-Embed CC1101"; "T-Display S3 Long"), and that word is an open
    set: no list of suffixes can be complete (#1797 was blocked three times on the next one). So a name
    counts only when it is followed by the end of the text, punctuation, or a word of FOLLOW_OK (plain
    words that never make a product: "with", "for", "board", "firmware", "support"). Any other word
    makes it an unknown sibling and names nothing. This costs sentences such as "T-Display S3 Spotify
    remote"; a missed board is a smaller catalog, a wrong board is a false claim.
  - A GitHub topic is a label typed whole: it names a board only when the WHOLE topic is one of the
    board's terms ("m5stickc", "lilygo-tdisplay-s3"); "t-beam-supreme" is not the T-Beam.
  - Chip-only terms (`esp32s3`) and generic words (board_alias._GENERIC) never name a board; terms
    shorter than MIN_TERM alphanumerics never count.
  - Specific beats general: a match whose span lies inside another board's match is dropped ("T-Display
    S3" names the T-Display-S3, not also the T-Display).
  - URLs, library/SDK references and #includes are not prose (autoreview._prose), so "M5Cardputer Arduino
    library" is a dependency, not a device.

The caller (jr/scorer.py) passes each of the repo's own texts on its own (name, description, README
title) and its topics, and admits only when exactly ONE board is named; several is `ambiguous_board`, a
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
# The only words that may come right after a board's name. Anything else is treated as the suffix of a
# sibling product nobody catalogued (see the module docstring): the list is closed so that the rule fails
# closed. Function words, and the nouns a sentence uses for the thing itself or for the software on it.
FOLLOW_OK = frozenset("""
    a an the and or nor but with without for from to on in at by via as of using
    is are was were be has have that which who it this
    board boards device devices hardware firmware software support supported supports
    based running port ports demo demos example examples build builds project projects app apps
""".split())
_FOLLOWER = re.compile(r"[-_ \t]*([a-z0-9][a-z0-9.+]*)")
_STRICT_SEP = r"[-_]"


def _parts(term: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (term or "").lower())


def _qualifies(parts: list[str]) -> bool:
    compact = "".join(parts)
    beyond_module = "".join(p for p in parts if p not in board_alias._GENERIC)
    return (len(compact) >= MIN_TERM and not board_alias.chip_only(compact)
            and bool(beyond_module) and not board_alias.chip_only(beyond_module))


BRANDED, COINED, CHIP_FIRST = "branded", "coined", "chip-first"


def _chip_first(parts: list[str]) -> bool:
    """A name that starts with a chip ("esp32-ethernet-kit", "esp32-s3-devkitc-1"): the rest is plain words."""
    return bool(parts) and (parts[0].startswith(("esp32", "esp8266")) or bool(board_alias.chip_only(parts[0])))


def _pattern(parts: list[str], spelling: str) -> re.Pattern:
    """Whole-word. BRANDED: a separator optional between EVERY character (the catalog writes
    "m5stick-cplus", a README "M5Stick C Plus" or "M5StickCPlus"; all three are the one board).
    COINED: a separator optional only between the catalog's own words ("papers3" stays one word).
    CHIP_FIRST: a hyphen or underscore REQUIRED between the catalog's own words ("ESP32-Ethernet-Kit";
    "ESP32 Ethernet kit" is English)."""
    if spelling == BRANDED:
        body = _SEP.join(map(re.escape, "".join(parts)))
    else:
        body = (_STRICT_SEP if spelling == CHIP_FIRST else _SEP).join(map(re.escape, parts))
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])")


def _terms(board: dict) -> list[tuple[list[str], str]]:
    """The (term part-list, spelling) pairs a board may be named by (see the module docstring)."""
    out: list[tuple[list[str], str]] = []
    bid, name, brand = board.get("id") or "", board.get("name") or "", board.get("brand") or ""
    prefixes = [p for p in sorted({brand, *board_alias._BRAND_PREFIXES.get(brand, set())}) if p]
    compact_prefixes = tuple("".join(_parts(p)) for p in prefixes)

    def bare(parts: list[str], otherwise: str) -> str:
        return CHIP_FIRST if _chip_first(parts) else otherwise

    out.append((_parts(bid), bare(_parts(bid), BRANDED)))
    for prefix in prefixes:
        out.append((_parts(prefix) + _parts(name), BRANDED))
    for aka in board.get("aka") or []:
        out.append((_parts(aka), bare(_parts(aka), COINED)))
    if re.search(r"\d", name):        # "Unexpected Maker TinyS3" carries its brand, "PaperS3" does not
        carries_brand = "".join(_parts(name)).startswith(compact_prefixes)
        out.append((_parts(name), bare(_parts(name), BRANDED if carries_brand else COINED)))
    seen, uniq = set(), []
    for p, spelling in out:
        key = tuple(p)
        if p and key not in seen and _qualifies(p):
            seen.add(key)
            uniq.append((p, spelling))
    return uniq


@lru_cache(maxsize=4)
def _table(root: Path | None) -> list[tuple[str, re.Pattern]]:
    boards = board_alias.atlas_boards(root)
    return [(bid, _pattern(p, spelling)) for bid, b in sorted(boards.items()) for p, spelling in _terms(b)]


@lru_cache(maxsize=4)
def _whole(root: Path | None) -> dict[str, frozenset[str]]:
    """{a term written without separators: the boards it is a term of}, for whole-topic matching."""
    out: dict[str, set[str]] = {}
    for bid, b in sorted(board_alias.atlas_boards(root).items()):
        for p, _ in _terms(b):
            out.setdefault("".join(p), set()).add(bid)
    return {k: frozenset(v) for k, v in out.items()}


def clear_caches() -> None:
    _table.cache_clear()
    _whole.cache_clear()


def _followed_by_a_plain_word_or_nothing(low: str, end: int) -> bool:
    """True when the text after a name cannot be the suffix of a sibling product: the end, punctuation, or
    a word of FOLLOW_OK. A separator and then any other word ("-supreme", " cc1101", " long") is False."""
    m = _FOLLOWER.match(low, end)
    return m is None or m.group(1).rstrip(".+") in FOLLOW_OK


def boards_named_in(text: str | None, root: Path | None = None, topics=()) -> list[str]:
    """Sorted ids of the catalogued boards named by `text` (ONE piece of prose: a repo name, a description,
    a README title — pass each on its own, never joined, so the end of one is not read as followed by the
    next) or by one of `topics` (whole-topic match). See the module docstring for the rules.
    `root` is the catalog root (default: the module's own repo), as board_alias.atlas_boards takes it."""
    named = set()
    whole = _whole(root)
    for topic in topics or ():
        named |= whole.get("".join(_parts(str(topic))), frozenset())
    low = autoreview._prose(text or "").lower()
    if not low.strip():
        return sorted(named)
    spans: list[tuple[int, int, str]] = []
    for bid, pat in _table(root):
        for m in pat.finditer(low):
            spans.append((m.start(), m.end(), bid))
    for s, e, bid in spans:
        inside = any(bid != o and os_ <= s and e <= oe and (oe - os_) > (e - s) for os_, oe, o in spans)
        if not inside and _followed_by_a_plain_word_or_nothing(low, e):
            named.add(bid)
    return sorted(named)
