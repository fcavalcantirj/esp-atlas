#!/usr/bin/env python3
"""Derive `usb_serial` from the cited `usb.bridge` (scripts/derive_usb_serial.py).

Cheap cited win: a board whose `usb.bridge` names a chip the schema's `usb_serial` enum
already knows carries the answer — it just is not written as `usb_serial` yet. Rules:

  - `bridge` in {ch340, ch343, ch9102, cp2102, cp2102n} (schema/board.schema.json) →
    `usb_serial` is that same value;
  - `bridge == 'native'` → the soc (via the board's `soc`/`module`, exactly as
    jr/tools.board_soc resolves it) must have `usb.native: true` AND a `usb.type`
    containing 'serial-jtag' (esp32-s3's 'otg-full-speed + serial-jtag') → `usb_serial:
    native-usb-serial-jtag`. esp32 ('native: false') and esp32-s2 ('otg-full-speed',
    no serial-jtag) stay untouched;
  - any other bridge value (ft2232h, ch340g, ch9102f, …) → skipped, reported, left for a
    human (a variant suffix is a hardware claim no filename proves).

Source: the board's existing `sources[]` entry whose field is `usb.bridge` (else `usb`,
else `*`) is copied as a new `field: usb_serial` entry with today's verified date; `notes`
gains one line naming the derivation. Boards that already have `usb_serial`, or whose
bridge is uncited, are untouched.

Textual edit, never a YAML round-trip (see scripts/author_board_aka.py): insert
`usb_serial:` after the `usb:` block, append the source entry at the end of `sources:`,
append the notes line, then re-parse and verify (usb_serial set, exactly one source and at
most one note added, everything else identical) before writing. Idempotent: a second run
reports every board already set and writes nothing.

Usage:
    python3 scripts/derive_usb_serial.py --dry-run   # report, write nothing
    python3 scripts/derive_usb_serial.py             # rewrite data/boards/**/board.md in place
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "jr"))
import tools  # noqa: E402

# Values of usb.bridge that ARE usb_serial enum values (schema/board.schema.json) — the
# serial chip is named outright, so usb_serial repeats it verbatim.
DIRECT = {"ch340", "ch343", "ch9102", "cp2102", "cp2102n"}
NATIVE_SERIAL_JTAG = "native-usb-serial-jtag"

_FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def _split(text: str) -> tuple[str, str]:
    m = _FM.match(text)
    if not m:
        raise ValueError("no frontmatter")
    return m.group(1), text[m.end():]


def _qu(s: str) -> str:
    """Single-quoted YAML scalar (doubles internal quotes)."""
    return "'" + str(s).replace("'", "''") + "'"


def _usb_block_span(lines: list[str]) -> tuple[int, int]:
    """(start, end) of the top-level `usb:` block; raises on unknown layouts."""
    try:
        s = next(i for i, l in enumerate(lines) if re.match(r"^usb:\s*(#.*)?$", l))
    except StopIteration:
        raise ValueError("no top-level usb: block") from None
    e = s + 1
    while e < len(lines) and (lines[e].startswith(" ") or lines[e].startswith("\t") or lines[e] == ""):
        e += 1
    if e == s + 1:
        raise ValueError("empty usb: block")
    return s, e


def _bridge_of(fm: dict) -> str | None:
    usb = fm.get("usb") or {}
    return usb.get("bridge") if isinstance(usb, dict) else None


def _cite_url(fm: dict) -> str | None:
    """The URL that cites the bridge: field usb.bridge, else usb, else '*'."""
    sources = fm.get("sources") or []
    for want in ("usb.bridge", "usb", "*"):
        for s in sources:
            if isinstance(s, dict) and s.get("field") == want and s.get("url"):
                return s["url"]
    return None


def _soc_usb_type(soc: str | None) -> tuple[bool, str]:
    if not soc:
        return False, ""
    for chip in (REPO / "data" / "socs").glob(f"{soc}/chip.md"):
        try:
            fm = yaml.safe_load(chip.read_text(encoding="utf-8").split("---")[1])
        except (yaml.YAMLError, IndexError, OSError):
            return False, ""
        usb = (fm or {}).get("usb") or {}
        return bool(usb.get("native")), str(usb.get("type") or "")
    return False, ""


def wanted_serial(board_id: str, bridge: str) -> tuple[str | None, str]:
    """(usb_serial value or None, reason). Pure: no I/O beyond the soc records."""
    if bridge in DIRECT:
        return bridge, f"bridge names {bridge}"
    if bridge == "native":
        soc = tools.board_soc(board_id)
        native, utype = _soc_usb_type(soc)
        if native and "serial-jtag" in utype:
            return NATIVE_SERIAL_JTAG, f"native + soc usb.type {utype}"
        return None, f"native but soc {soc} usb is not serial-jtag (native={native}, type={utype!r})"
    return None, f"bridge {bridge!r} is not a usb_serial enum value"


def process_file(path: Path, today: str) -> str:
    """Derive usb_serial for one board.md. Returns a status line; writes only on change."""
    text = path.read_text(encoding="utf-8")
    head, rest = _split(text)
    fm = yaml.safe_load(head)
    if not isinstance(fm, dict) or not fm.get("id"):
        return f"{path}: skipped (unparseable frontmatter)"
    bid = fm["id"]
    if fm.get("usb_serial"):
        return f"{bid}: already has usb_serial"
    bridge = _bridge_of(fm)
    if not bridge:
        return f"{bid}: no usb.bridge"
    value, _reason = wanted_serial(bid, bridge)
    if value is None:
        return f"{bid}: skipped ({_reason})"
    url = _cite_url(fm)
    if not url:
        return f"{bid}: skipped (usb.bridge uncited)"
    note = f"usb_serial derived from usb.bridge ({bridge})"
    if value == NATIVE_SERIAL_JTAG:
        _native, utype = _soc_usb_type(tools.board_soc(bid))
        note += f" + soc usb.type {utype}"

    lines = head.split("\n")
    _s, e = _usb_block_span(lines)
    lines[e:e] = [f"usb_serial: {value}"]
    src_entries = [l for l in lines if re.match(r"^\s*- field:", l)]
    indent = src_entries[0][: len(src_entries[0]) - len(src_entries[0].lstrip())] if src_entries else None
    if indent is None:
        raise ValueError(f"{bid}: no sources entries to extend")
    try:
        src_idx = next(i for i, l in enumerate(lines) if re.match(r"^\s*sources:\s*(#.*)?$", l))
    except StopIteration:
        raise ValueError(f"{bid}: no sources: block") from None
    # end of the sources block: the run of `- field:` entries (plus continuations) after sources:
    at = src_idx + 1
    while at < len(lines) and (re.match(r"^\s*- field:", lines[at]) or _in_entry(lines, at)):
        at += 1
    new_source = [f"{indent}- field: usb_serial", f"{indent}  url: {url}", f"{indent}  verified: '{today}'"]
    lines[at:at] = new_source
    if fm.get("notes"):
        if note in (fm["notes"] or []):
            pass
        else:
            nidx = next(i for i, l in enumerate(lines) if re.match(r"^notes:\s*(#.*)?$", l))
            nend = nidx + 1
            while nend < len(lines) and (lines[nend].startswith(" ") or lines[nend].startswith("-")):
                nend += 1
            lines[nend:nend] = [f"- {_qu(note)}"]
    else:
        lines += ["notes:", f"- {_qu(note)}"]
    new_head = "\n".join(lines)
    # --- verify before writing ---------------------------------------------------------
    new_fm = yaml.safe_load(new_head)
    old_sources = fm.get("sources") or []
    ok = (isinstance(new_fm, dict)
          and new_fm.get("usb_serial") == value
          and new_fm.get("sources") == list(old_sources) + [{"field": "usb_serial", "url": url, "verified": today}]
          and {k: v for k, v in new_fm.items() if k not in ("usb_serial", "sources", "notes")}
              == {k: v for k, v in fm.items() if k not in ("usb_serial", "sources", "notes")})
    if fm.get("notes"):
        ok = ok and new_fm.get("notes") == list(fm["notes"]) + ([note] if note not in fm["notes"] else [])
    else:
        ok = ok and new_fm.get("notes") == [note]
    if not ok:
        raise ValueError(f"{bid}: rewrite verification failed; file left untouched")
    path.write_text("---\n" + new_head + "\n---\n" + rest, encoding="utf-8")
    return f"{bid}: usb_serial={value} (from bridge {bridge})"


def _in_entry(lines: list[str], at: int) -> bool:
    """True when lines[at] is a continuation (indented non-list) line of a `- field:` entry."""
    if not lines[at].startswith(" "):
        return False
    j = at - 1
    while j >= 0 and lines[j].startswith(" ") and not re.match(r"^\s*- field:", lines[j]):
        j -= 1
    return j >= 0 and bool(re.match(r"^\s*- field:", lines[j]))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args(argv)
    changed = 0
    for path in sorted((REPO / "data" / "boards").glob("*/*/board.md")):
        if args.dry_run:
            text = path.read_text(encoding="utf-8")
            try:
                head, _rest = _split(text)
                fm = yaml.safe_load(head)
            except (ValueError, yaml.YAMLError):
                print(f"{path}: skipped (unparseable frontmatter)")
                continue
            if not isinstance(fm, dict) or not fm.get("id"):
                print(f"{path}: skipped (unparseable frontmatter)")
                continue
            if fm.get("usb_serial"):
                continue
            bridge = _bridge_of(fm)
            if not bridge:
                continue
            value, reason = wanted_serial(fm["id"], bridge)
            print(f"{fm['id']}: {'usb_serial=' + value if value else 'skipped (' + reason + ')'}")
            continue
        try:
            line = process_file(path, args.today)
        except ValueError as e:
            line = f"{path}: REFUSED ({e})"
        print(line)
        changed += 1 if "usb_serial=" in line else 0
    print(f"changed {changed} board(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
