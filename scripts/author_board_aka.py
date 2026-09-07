#!/usr/bin/env python3
"""Author `aka:` on every catalogued board from the board universe — cited, textual, idempotent.

Phase 4 (SPEC-firmware-boards.md §2, PLAN 'Author aka on 82/82 boards in one bot PR, cited to
the boards.txt raw URL'). For each atlas board, jr/board_alias.py says which universe entries
(data/board_universe.json) are that board. Their ids and `build.board` defines are the strings
firmware repos actually use for the board, so they become the record's `aka` list,
and every one is traceable: a `sources[]` entry `field: aka` points at the universe entry's
source file (the raw boards.txt at its pinned sha, or the pioarduino board JSON) with the
universe's `generated` date as `verified`.

Textual edit, never a YAML round-trip (scripts/strip_downloads.py learned that a round-trip
escapes non-ASCII names and re-folds hand-written fields):

  - the `aka:` block (if any) is replaced in place; otherwise it is inserted right after the
    `name:` line;
  - the `sources:` block keeps every existing entry and gains one `field: aka` entry per
    distinct citation URL (existing `field: aka` entries are replaced);
  - a board with no resolved universe entry is left untouched (cite-or-omit).

Usage:
    python3 scripts/author_board_aka.py --dry-run     # report, write nothing
    python3 scripts/author_board_aka.py               # rewrite data/boards/**/board.md in place
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "jr"))
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))
import board_alias  # noqa: E402

UNIVERSE_PATH = REPO / "data" / "board_universe.json"


# --- deriving ----------------------------------------------------------------------------------

def aka_for(atlas_id: str, board: dict, entries: dict[str, dict], table: dict[str, dict]) -> tuple[list[str], list[str]]:
    """(aka strings, citation urls) for one board: the BUILD IDENTIFIERS of every universe
    entry that resolves to it — its id and its `build.board` define, i.e. the strings a
    platformio.ini `board =`, an arduino-cli FQBN or a `-DARDUINO_<BOARD>` flag actually
    contains — minus anything equal (compact) to the board's own id or name, minus chip-only
    tokens, deduped by compact form, in a stable sorted order. Neither display names nor the
    Arduino `variant` are aka: names are matched through the universe at run time, and a
    variant is shared by sibling products (AtomS3/AtomS3U), so it would alias the wrong board."""
    own = {board_alias.compact(board["id"]), board_alias.compact(board["name"])}
    # a `build.board` define is an alias only when it is UNIQUE in the universe: DFRobot's
    # Beetle reuses the generic ESP32C3_DEV, which names a chip's dev module, not the Beetle.
    define_count: dict[str, int] = {}
    for e in entries.values():
        d = e.get("board_define")
        if d:
            define_count[d] = define_count.get(d, 0) + 1
    seen: dict[str, str] = {}
    urls: list[str] = []
    for key, res in table.items():
        if res["atlas_id"] != atlas_id:
            continue
        e = entries[key]
        candidates = [e.get("id")]
        if e.get("board_define") and define_count.get(e["board_define"], 0) == 1:
            candidates.append(e["board_define"])
        for s in candidates:
            c = board_alias.compact(s)
            if s and c and c not in own and c not in seen and not board_alias.chip_only(s):
                seen[c] = s
        if e.get("url") and e["url"] not in urls:
            urls.append(e["url"])
    return sorted(seen.values(), key=lambda s: (s.lower(), s)), urls


# --- textual frontmatter surgery -------------------------------------------------------------

_FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def _split(text: str) -> tuple[str, str]:
    m = _FM.match(text)
    if not m:
        raise ValueError("no frontmatter")
    return m.group(1), text[m.end():]


def _yaml_str(s: str) -> str:
    """A YAML double-quoted scalar; keeps non-ASCII verbatim, escapes only what YAML needs."""
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _drop_block(lines: list[str], key: str) -> list[str]:
    """Remove a top-level `key:` line and its indented/list continuation lines."""
    out, i = [], 0
    while i < len(lines):
        if re.match(rf"^{re.escape(key)}:\s*(\[.*\])?\s*$", lines[i]):
            i += 1
            while i < len(lines) and (lines[i].startswith(" ") or lines[i].startswith("-") or lines[i] == ""):
                if lines[i] == "" and (i + 1 >= len(lines) or not (lines[i + 1].startswith(" ") or lines[i + 1].startswith("-"))):
                    break
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def _drop_aka_sources(lines: list[str]) -> list[str]:
    """Remove existing `- field: aka` entries (3 lines each) from the sources block."""
    out, i = [], 0
    while i < len(lines):
        if re.match(r"^- field:\s*'?\"?aka'?\"?\s*$", lines[i]):
            i += 1
            while i < len(lines) and lines[i].startswith("  "):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return out


def rewrite(text: str, aka: list[str], urls: list[str], verified: str) -> str:
    fm, body = _split(text)
    lines = fm.split("\n")
    lines = _drop_block(lines, "aka")
    lines = _drop_aka_sources(lines)
    # insert aka after name:
    name_idx = next(i for i, l in enumerate(lines) if l.startswith("name:"))
    block = ["aka:"] + [f"- {_yaml_str(a)}" for a in aka]
    lines[name_idx + 1:name_idx + 1] = block
    # append citations at the end of the sources block (sources is top-level; find its extent)
    src_idx = next((i for i, l in enumerate(lines) if l.startswith("sources:")), None)
    entries = [f"- field: aka\n  url: {u}\n  verified: '{verified}'" for u in urls]
    if src_idx is None:
        lines += ["sources:"] + entries
    else:
        end = src_idx + 1
        while end < len(lines) and (lines[end].startswith("-") or lines[end].startswith(" ")):
            end += 1
        lines[end:end] = entries
    return "---\n" + "\n".join(lines) + "\n---\n" + body


# --- driver ------------------------------------------------------------------------------------

def _read_boards(boards_dir: Path) -> dict[str, dict]:
    """Like board_alias.atlas_boards() but over an arbitrary boards dir (tests use a tmp copy)."""
    out = {}
    for bmd in sorted(boards_dir.glob("*/*/board.md")):
        fm = board_alias.tools._frontmatter(bmd)
        out[fm["id"]] = {"id": fm["id"], "name": fm.get("name") or "", "aka": list(fm.get("aka") or []),
                         "soc": fm.get("soc") or board_alias.tools.board_soc(fm["id"]),
                         "brand": fm.get("brand") or bmd.parent.parent.name, "_path": bmd}
    return out


def one_pass(boards_dir: Path, universe: dict, dry_run: bool) -> dict:
    entries = {e["key"]: e for e in universe["boards"]}
    verified = universe["generated"]
    boards = _read_boards(boards_dir)
    table = board_alias.build_table(boards, universe["boards"])
    written, skipped, unchanged = [], [], []
    for fm_id, board in boards.items():
        aka, urls = aka_for(fm_id, board, entries, table)
        if not aka:
            skipped.append(fm_id)
            continue
        bmd = board["_path"]
        before = bmd.read_text(encoding="utf-8")
        after = rewrite(before, aka, urls, verified)
        if after == before:
            unchanged.append(fm_id)
            continue
        written.append((fm_id, aka, urls))
        if not dry_run:
            bmd.write_text(after, encoding="utf-8")
    return {"written": written, "unchanged": unchanged, "skipped": skipped}


def run(dry_run: bool = False, universe_path: Path = UNIVERSE_PATH, out=print,
        boards_dir: Path | None = None, max_passes: int = 5) -> dict:
    """Author aka to a FIXED POINT. An aka written in one pass is a new match key for the next
    (an explicit alias gives a board the arduino id; the pioarduino entry with that same id then
    matches by equality and adds its citation), so passes repeat until a pass changes nothing.
    A dry run reports the first pass only (it cannot see what the next pass would see)."""
    universe = json.loads(universe_path.read_text(encoding="utf-8"))
    boards_dir = (REPO / "data" / "boards") if boards_dir is None else boards_dir
    total_written: dict[str, tuple] = {}
    passes = 0
    for passes in range(1, max_passes + 1):
        res = one_pass(boards_dir, universe, dry_run)
        for fid, aka, urls in res["written"]:
            total_written[fid] = (aka, urls)
        if dry_run or not res["written"]:
            break
    out(f"aka: {len(total_written)} board(s) {'would be ' if dry_run else ''}rewritten in {passes} pass(es), "
        f"{len(res['unchanged'])} unchanged, {len(res['skipped'])} without a resolved universe entry (left alone)")
    for fid, (aka, urls) in sorted(total_written.items()):
        out(f"  {fid}: {aka} ← {len(urls)} citation(s)")
    return {"written": sorted(total_written), "unchanged": res["unchanged"], "skipped": res["skipped"], "passes": passes}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    run(dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
