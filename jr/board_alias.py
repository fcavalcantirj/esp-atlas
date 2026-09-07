"""EspAtlas Jr — board alias resolver (jr/board_alias.py): universe/build-signal token → atlas board.

Phase 4 (SPEC-firmware-boards.md §1-§2). A firmware's build signals name boards the way the
toolchains do — `m5stack_cardputer` (arduino-esp32 boards.txt id), `lolin_s3_mini` (PlatformIO
board id), `M5StickCPlus2` (a boards.txt display name), `esp32s3` (a chip, not a board). The
catalog names them its own way (`m5cardputer`, `lolin-s3-mini`, `m5stick-cplus2`). This module
is the ONE place that translation lives, and it is deterministic: no model, no fuzzy scoring.

Resolution order for a universe entry (data/board_universe.json) or a raw token:

  1. an explicit alias in jr/board_aliases.json — hand-curated, each with the universe key it
     maps and the atlas id, so a reader can open both records and see they are the same board;
  2. COMPACT equality — lower-case, every non-alphanumeric removed — between any of the atlas
     board's {id, name, aka} and the universe entry's {id, name} (never its Arduino `variant`,
     which siblings share);
  3. COMPACT containment — the atlas board's compact name (or an aka) appears inside the entry's
     compact id/name ("tdeck" in "lilygotdeck") with only the board's own vendor as prefix and
     only a memory SKU as suffix, is ≥ MIN_CONTAIN characters, is not a chip-only token, and
     exactly ONE atlas board matches. A foreign vendor prefix is a clone, a product suffix is a
     sibling: both refused.

Every rule additionally requires the SOC to agree: the universe entry's `soc` (mapped from
`build.mcu`) must equal the atlas board's soc (tools.board_soc, which reads the record and its
module). A name match with a different chip is the CatHack class of bug (DECISION-LOG #71) and
is refused, not scored. Chip-only tokens (`esp32s3`, `esp32-c6`) resolve to a SOC, never a board.

The resolver never writes. `report()` measures coverage over the real tree; the aka-authoring
step and the firmware derivation stages consume `resolve_*` results and cite the universe entry.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

import tools

REPO = tools.REPO
UNIVERSE_PATH = REPO / "data" / "board_universe.json"
ALIASES_PATH = Path(__file__).resolve().parent / "board_aliases.json"
MIN_CONTAIN = 5

# A token that names only a chip family. Resolves to a soc id, never to a board.
_CHIP_TOKENS = {
    "esp32": "esp32", "esp32s2": "esp32-s2", "esp32s3": "esp32-s3", "esp32c2": "esp32-c2",
    "esp32c3": "esp32-c3", "esp32c5": "esp32-c5", "esp32c6": "esp32-c6", "esp32c61": "esp32-c61",
    "esp32h2": "esp32-h2", "esp32h4": "esp32-h4", "esp32p4": "esp32-p4",
}
# Compact strings too generic to ever identify a board on their own (containment rule).
_GENERIC = {"esp32", "devmodule", "devkit", "board", "module", "wroom", "wrover", "mini", "pro", "lite", "plus"}

# Containment is allowed only when the text AROUND the atlas name is one of two things:
#  - a prefix that is empty or the board's own vendor (`lilygo` in "lilygotdeck", `espressif` in
#    "espressifesp32c6devkitc1") — a foreign vendor prefix means a clone (`rymcu…devkitc1`,
#    `azdelivery…devkitcv4`) and is refused;
#  - a suffix that is empty or a memory SKU (`n16r8`, `n4`, `4mb`, `8mbnopsram`) — a product
#    suffix means a sibling (`lolins3pro`, `m5stackatoms3u`, `heltec…trackerv2`) and is refused.
_BRAND_PREFIXES = {
    "lolin": {"wemos", "lolin"}, "lilygo": {"lilygo", "ttgo"}, "seeed": {"seeed", "seeedstudio"},
    "unexpected-maker": {"unexpectedmaker", "um"}, "m5stack": {"m5stack", "m5"},
}
_SKU_SUFFIX = re.compile(r"^(n\d+(r\d+)?v?|\d+mb(nopsram|psram)?|)$")


def compact(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def chip_only(token: str) -> str | None:
    """'esp32-s3' / 'ESP32S3' / 'esp32s3' → 'esp32-s3'; anything else → None."""
    return _CHIP_TOKENS.get(compact(token))


# --- inputs ------------------------------------------------------------------------------------

@lru_cache(maxsize=1)
def atlas_boards() -> dict[str, dict]:
    """{atlas_id: {id, name, aka[], soc, brand}} read from the real records (tools.board_soc
    resolves soc through the module, exactly like esp_atlas_core.validate)."""
    out = {}
    for bmd in sorted((REPO / "data" / "boards").glob("*/*/board.md")):
        fm = tools._frontmatter(bmd)
        out[fm["id"]] = {"id": fm["id"], "name": fm.get("name") or "", "aka": list(fm.get("aka") or []),
                         "soc": tools.board_soc(fm["id"]), "brand": fm.get("brand") or bmd.parent.parent.name}
    return out


@lru_cache(maxsize=1)
def universe(path: Path = UNIVERSE_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))["boards"]


@lru_cache(maxsize=1)
def explicit_aliases(path: Path = ALIASES_PATH) -> dict[str, dict]:
    """{universe_key: {"atlas_id", "why"}} from jr/board_aliases.json, or {} when absent."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in (data.get("aliases") or {}).items()}


def clear_caches() -> None:
    atlas_boards.cache_clear()
    universe.cache_clear()
    explicit_aliases.cache_clear()


# --- the rules ---------------------------------------------------------------------------------

def _atlas_compact_keys(board: dict) -> set[str]:
    return {compact(board["id"]), compact(board["name"]), *(compact(a) for a in board["aka"])} - {""}


def _entry_compact_keys(entry: dict) -> set[str]:
    """id and display name only. The Arduino `variant` is deliberately NOT a key: siblings share
    one variant (AtomS3 and AtomS3U both build with `m5stack_atoms3`), so matching on it maps a
    sibling onto the catalogued board."""
    return {compact(entry.get("id")), compact(entry.get("name"))} - {""}


def resolve_entry(entry: dict, boards: dict[str, dict] | None = None,
                  aliases: dict[str, dict] | None = None) -> dict | None:
    """Map one universe entry to an atlas board. Returns {"atlas_id", "how", "evidence"} or None.
    `how` ∈ {"alias", "compact", "contain"}; `evidence` is the universe entry's key + url (+line)."""
    boards = atlas_boards() if boards is None else boards
    aliases = explicit_aliases() if aliases is None else aliases
    soc = entry.get("soc")
    evidence = {"key": entry["key"], "url": entry.get("url"), **({"line": entry["line"]} if entry.get("line") else {})}

    alias = aliases.get(entry["key"])
    if alias:
        target = boards.get(alias["atlas_id"])
        if target and target["soc"] == soc:
            return {"atlas_id": alias["atlas_id"], "how": "alias", "evidence": evidence}
        return None                      # an alias to a missing board or a different chip is refused
    if soc is None:
        return None                      # no chip family → nothing to agree with

    ekeys = _entry_compact_keys(entry)
    exact = [b for b in boards.values() if b["soc"] == soc and _atlas_compact_keys(b) & ekeys]
    if len(exact) == 1:
        return {"atlas_id": exact[0]["id"], "how": "compact", "evidence": evidence}
    if len(exact) > 1:
        return None                      # ambiguous exact match: refuse, a human adds an alias

    contained = []
    for b in boards.values():
        if b["soc"] != soc:
            continue
        allowed_prefixes = {""} | _BRAND_PREFIXES.get(b["brand"], set()) | {compact(b["brand"])}
        for k in {compact(b["name"]), *(compact(a) for a in b["aka"])} - {""}:
            if len(k) < MIN_CONTAIN or k in _GENERIC or chip_only(k):
                continue
            if any(_contains_as_same_board(e, k, allowed_prefixes) for e in ekeys):
                contained.append(b)
                break
    if len(contained) == 1:
        return {"atlas_id": contained[0]["id"], "how": "contain", "evidence": evidence}
    return None


def _contains_as_same_board(entry_compact: str, atlas_compact: str, allowed_prefixes: set[str]) -> bool:
    """`atlas_compact` inside `entry_compact` with only a vendor prefix and/or a memory-SKU
    suffix around it — the shape of "the same board, named by its vendor or its memory
    option", never "a clone" or "a sibling product"."""
    start = 0
    while True:
        i = entry_compact.find(atlas_compact, start)
        if i < 0:
            return False
        prefix, suffix = entry_compact[:i], entry_compact[i + len(atlas_compact):]
        if prefix in allowed_prefixes and _SKU_SUFFIX.match(suffix):
            return True
        start = i + 1


def build_table(boards: dict[str, dict] | None = None, entries: list[dict] | None = None,
                aliases: dict[str, dict] | None = None) -> dict[str, dict]:
    """{universe_key: resolution} for every universe entry that resolves."""
    entries = universe() if entries is None else entries
    out = {}
    for e in entries:
        r = resolve_entry(e, boards, aliases)
        if r:
            out[e["key"]] = r
    return out


def resolve_token(token: str, soc: str | None = None, boards: dict[str, dict] | None = None,
                  entries: list[dict] | None = None, aliases: dict[str, dict] | None = None) -> dict | None:
    """Map a build-signal token (a PlatformIO board id, a boards.txt id, a `build.board` define,
    a display name) to an atlas board. A chip-only token returns {"soc": ...} and no board.
    `soc`, when the caller knows it (from `build.mcu`), must agree; the universe entry's own soc
    always must. Returns {"atlas_id", "how", "evidence"} | {"soc"} | None."""
    c = compact(token)
    if not c:
        return None
    chip = chip_only(token)
    if chip:
        return {"soc": chip}
    entries = universe() if entries is None else entries
    boards = atlas_boards() if boards is None else boards
    matches = [e for e in entries if c in _entry_compact_keys(e) and (soc is None or e.get("soc") == soc)]
    resolved = {}
    for e in matches:
        r = resolve_entry(e, boards, aliases)
        if r:
            resolved[r["atlas_id"]] = r
    if len(resolved) == 1:
        return next(iter(resolved.values()))
    if resolved or matches:
        return None                      # ambiguous, or the universe knows the token but refused it
    # NO universe entry carries this exact string (release assets and manifests use their own
    # short names: `tbeam`, `m5cardputer`). Fall back to the catalog itself: compact equality
    # against an atlas id / name / aka, chip family agreeing when the caller knows it.
    direct = [b for b in boards.values() if c in _atlas_compact_keys(b) and (soc is None or b["soc"] == soc)]
    if len(direct) == 1:
        return {"atlas_id": direct[0]["id"], "how": "direct", "evidence": {"key": None, "url": None}}
    return None                          # unknown token, or two atlas boards claim it


# --- reporting ---------------------------------------------------------------------------------

def report(boards: dict[str, dict] | None = None, entries: list[dict] | None = None,
           aliases: dict[str, dict] | None = None) -> dict:
    """Coverage over the atlas: which boards have ≥ 1 universe entry, by rule, and which have none."""
    boards = atlas_boards() if boards is None else boards
    table = build_table(boards, entries, aliases)
    by_board: dict[str, list] = {}
    for key, r in table.items():
        by_board.setdefault(r["atlas_id"], []).append((key, r["how"]))
    unresolved = sorted(b for b in boards if b not in by_board)
    how = {}
    for hits in by_board.values():
        for _, h in hits:
            how[h] = how.get(h, 0) + 1
    return {"atlas_boards": len(boards), "resolved": len(by_board), "unresolved": unresolved,
            "universe_entries_mapped": len(table), "by_rule": how, "by_board": by_board}


if __name__ == "__main__":
    rep = report()
    print(f"atlas boards {rep['atlas_boards']} · resolved {rep['resolved']} · "
          f"universe entries mapped {rep['universe_entries_mapped']} · by rule {rep['by_rule']}")
    for b in rep["unresolved"]:
        print("  unresolved:", b)
