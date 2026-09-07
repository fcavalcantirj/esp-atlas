#!/usr/bin/env python3
"""Derive `getting_started` from an already-cited vendor guide URL (scripts/derive_getting_started.py).

Cheap cited win: a board without `getting_started` whose own `sources[]` already cites a
vendor documentation page that IS a getting-started/user-guide page gets that URL as its
`getting_started`. Candidates are the board's own sources[] URLs whose host is a vendor
documentation domain already used in the catalog AND whose path names a guide:

  hosts: docs.espressif.com, docs.m5stack.com, learn.adafruit.com, www.wemos.cc,
         wiki.dfrobot.com, documentation.espressif.com (never github.com)
  path fragments: getting-started, get-started, get_started, getting_started, user-guide,
                  user_guide, quickstart, quick-start

The path rule is the deterministic stand-in for the schema's "the board's OFFICIAL
getting-started / user-guide page" — anything it cannot prove is omitted. Each candidate is
HEADed live (redirects followed, 10 s timeout); only an HTTP 200 writes. The source entry
`field: getting_started` cites the URL with today's verified date.

Textual edit, never a YAML round-trip (see scripts/author_board_aka.py): insert
`getting_started:` right before the `sources:` line, append the source entry at the end of
`sources:`, then re-parse and verify (getting_started set, exactly one source added,
everything else identical) before writing. Idempotent: a second run reports every board
already set or without a live candidate and writes nothing.

Usage:
    python3 scripts/derive_getting_started.py --dry-run   # report (HEADS the network), write nothing
    python3 scripts/derive_getting_started.py             # rewrite data/boards/**/board.md in place
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import yaml

REPO = Path(__file__).resolve().parent.parent

VENDOR_DOC_HOSTS = ("docs.espressif.com", "docs.m5stack.com", "learn.adafruit.com",
                    "www.wemos.cc", "wiki.dfrobot.com", "documentation.espressif.com")
GUIDE_PATH_BITS = ("getting-started", "get-started", "get_started", "getting_started",
                   "user-guide", "user_guide", "quickstart", "quick-start")

_FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def _split(text: str) -> tuple[str, str]:
    m = _FM.match(text)
    if not m:
        raise ValueError("no frontmatter")
    return m.group(1), text[m.end():]


def candidates(fm: dict) -> list[str]:
    """The board's own sources[] URLs that are vendor-doc guide pages, in sources order."""
    out = []
    for s in fm.get("sources") or []:
        u = (s.get("url") or "") if isinstance(s, dict) else ""
        p = urlparse(u)
        if p.netloc in VENDOR_DOC_HOSTS and any(k in p.path for k in GUIDE_PATH_BITS):
            if u not in out:
                out.append(u)
    return out


def head_ok(url: str, timeout: float = 10.0) -> bool:
    """True when a live HEAD of the URL answers HTTP 200 (redirects followed)."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "esp-atlas-derive/1.0"})
        return urllib.request.urlopen(req, timeout=timeout).status == 200
    except Exception:  # noqa: BLE001 — any failure (DNS, 404, 405, timeout) means "not proven"
        return False


def process_file(path: Path, today: str, head=head_ok) -> str:
    """Derive getting_started for one board.md. Returns a status line; writes only on change."""
    text = path.read_text(encoding="utf-8")
    head_text, rest = _split(text)
    fm = yaml.safe_load(head_text)
    if not isinstance(fm, dict) or not fm.get("id"):
        return f"{path}: skipped (unparseable frontmatter)"
    bid = fm["id"]
    if fm.get("getting_started"):
        return f"{bid}: already has getting_started"
    live = next((u for u in candidates(fm) if head(u)), None)
    if live is None:
        return f"{bid}: skipped (no live vendor guide URL in sources)"

    lines = head_text.split("\n")
    try:
        src_idx = next(i for i, l in enumerate(lines) if re.match(r"^\s*sources:\s*(#.*)?$", l))
    except StopIteration:
        raise ValueError(f"{bid}: no sources: block") from None
    lines[src_idx:src_idx] = [f"getting_started: {live}"]
    src_entries = [l for l in lines if re.match(r"^\s*- field:", l)]
    if not src_entries:
        raise ValueError(f"{bid}: no sources entries to extend")
    indent = src_entries[0][: len(src_entries[0]) - len(src_entries[0].lstrip())]
    at = src_idx + 2   # past the inserted getting_started line and the sources: line
    while at < len(lines) and (re.match(r"^\s*- field:", lines[at]) or _in_entry(lines, at)):
        at += 1
    lines[at:at] = [f"{indent}- field: getting_started", f"{indent}  url: {live}",
                    f"{indent}  verified: '{today}'"]
    new_head = "\n".join(lines)
    # --- verify before writing ---------------------------------------------------------
    new_fm = yaml.safe_load(new_head)
    old_sources = fm.get("sources") or []
    ok = (isinstance(new_fm, dict)
          and new_fm.get("getting_started") == live
          and new_fm.get("sources") == list(old_sources) + [{"field": "getting_started", "url": live, "verified": today}]
          and {k: v for k, v in new_fm.items() if k not in ("getting_started", "sources")}
              == {k: v for k, v in fm.items() if k not in ("getting_started", "sources")})
    if not ok:
        raise ValueError(f"{bid}: rewrite verification failed; file left untouched")
    path.write_text("---\n" + new_head + "\n---\n" + rest, encoding="utf-8")
    return f"{bid}: getting_started={live}"


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
    ap.add_argument("--dry-run", action="store_true", help="report (HEADS the network), write nothing")
    ap.add_argument("--today", default=date.today().isoformat())
    args = ap.parse_args(argv)
    changed = 0
    for path in sorted((REPO / "data" / "boards").glob("*/*/board.md")):
        if args.dry_run:
            try:
                head_text, _rest = _split(path.read_text(encoding="utf-8"))
                fm = yaml.safe_load(head_text)
            except (ValueError, yaml.YAMLError):
                print(f"{path}: skipped (unparseable frontmatter)")
                continue
            if not isinstance(fm, dict) or not fm.get("id"):
                print(f"{path}: skipped (unparseable frontmatter)")
                continue
            if fm.get("getting_started"):
                continue
            live = next((u for u in candidates(fm) if head_ok(u)), None)
            print(f"{fm['id']}: {'getting_started=' + live if live else 'skipped (no live vendor guide URL in sources)'}")
            continue
        try:
            line = process_file(path, args.today)
        except ValueError as e:
            line = f"{path}: REFUSED ({e})"
        print(line)
        changed += 1 if "getting_started=" in line and "already has" not in line else 0
    print(f"changed {changed} board(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
