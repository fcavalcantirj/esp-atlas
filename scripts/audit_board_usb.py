#!/usr/bin/env python3
"""Board USB-field AUDIT — read-only (owner mandate G3, 2026-11-04; SPEC-board-grounding.md).

The PlatformIO manifests and the Arduino-ESP32 boards.txt are corroboration only now: they may not
write `usb_serial` or `download_mode` (jr/board_corroboration.py). Values written before that rule
are NOT changed by it. This script lists every existing `usb_serial` / `download_mode` in
data/boards with what supports it, for the owner to review, and prints the counts. It decides
nothing and writes nothing.

Classes, first match wins:
  conflict                 a pinned toolchain source states a different usb_serial
  board_evidence           a field-specific citation that is not a toolchain source (the vendor
                           page / schematic; for usb_serial also a `usb` / `usb.bridge` citation)
  toolchain_corroboration  only a toolchain citation (any commit) or an agreeing pinned toolchain
                           value supports it
  none                     nothing does (a blanket '*' citation does not count)

LIVE by default: usb_serial is checked against the pinned PlatformIO manifest and boards.txt, one
fetch per URL for the whole run. `--offline` classifies from the citations alone. download_mode is
never checked against a toolchain: neither states it.

    python3 scripts/audit_board_usb.py
    python3 scripts/audit_board_usb.py --offline
    python3 scripts/audit_board_usb.py --json

Always exits 0.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
for _p in (REPO_ROOT / "apps" / "core" / "src", REPO_ROOT / "jr"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import board_backfill  # noqa: E402
import board_corroboration  # noqa: E402
from esp_atlas_core.frontmatter import parse_frontmatter  # noqa: E402
from esp_atlas_core.paths import DATA_DIR  # noqa: E402

CONFLICT = "conflict"
BOARD_EVIDENCE = "board_evidence"
TOOLCHAIN_CORROBORATION = "toolchain_corroboration"
NONE = "none"
CLASSES = (BOARD_EVIDENCE, TOOLCHAIN_CORROBORATION, CONFLICT, NONE)

AUDITED_FIELDS = ("usb_serial", "download_mode")
# The `sources[].field` keys that cite each audited field. A blanket '*' is deliberately absent:
# it cites the record, not a statement about the USB connection or the download mode.
CITATION_KEYS = {"usb_serial": ("usb_serial", "usb", "usb.bridge"),
                 "download_mode": ("download_mode",)}
_TOOLCHAIN_URL_RE = re.compile(
    r"github(?:usercontent)?\.com/(?:platformio/platform-espressif32|espressif/arduino-esp32)/")


def audit(data_dir=None, fetch=None) -> dict:
    """{"entries": [...], "unreadable": [paths], "counts": {field: {class: n}}} over every board's
    existing usb_serial / download_mode (a board.md whose frontmatter cannot be parsed is listed
    under "unreadable", never fatal). `fetch(url) -> {"ok", "text"}` reads the pinned toolchain sources (None =
    offline, citations only)."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    fetch = _memo(fetch) if fetch is not None else None
    report: dict = {"entries": [], "unreadable": [],
                    "counts": {f: {c: 0 for c in CLASSES} for f in AUDITED_FIELDS}}
    for path in sorted(root.glob("boards/*/*/board.md")):
        try:
            fm, _ = parse_frontmatter(path)
        except (ValueError, OSError):
            report["unreadable"].append(str(path))
            continue
        fm = fm or {}
        for field in AUDITED_FIELDS:
            if not board_backfill._is_present(fm.get(field)):
                continue
            entry = _entry(path, fm, field, root, fetch)
            report["entries"].append(entry)
            report["counts"][field][entry["class"]] += 1
    return report


def _entry(path: Path, fm: dict, field: str, root: Path, fetch) -> dict:
    board_cites, toolchain_cites = _citations(fm, field)
    checks = _toolchain_checks(fm, path, field, root, fetch)
    verdicts = {c["verdict"] for c in checks}
    if board_corroboration.CONFLICTS in verdicts:
        cls = CONFLICT
    elif board_cites:
        cls = BOARD_EVIDENCE
    elif toolchain_cites or board_corroboration.CORROBORATES in verdicts:
        cls = TOOLCHAIN_CORROBORATION
    else:
        cls = NONE
    return {"board": fm.get("id") or path.parent.name, "brand": path.parent.parent.name,
            "field": field, "value": fm[field], "class": cls,
            "corroborated": bool(checks) and verdicts == {board_corroboration.CORROBORATES},
            "board_citations": board_cites, "toolchain_citations": toolchain_cites,
            "checks": checks}


def _citations(fm: dict, field: str) -> tuple[list[str], list[str]]:
    urls = [s.get("url") or "" for s in fm.get("sources") or []
            if isinstance(s, dict) and s.get("field") in CITATION_KEYS[field]]
    toolchain = [u for u in urls if _TOOLCHAIN_URL_RE.search(u)]
    return [u for u in urls if u not in toolchain], toolchain


def _toolchain_checks(fm: dict, path: Path, field: str, root: Path, fetch) -> list[dict]:
    if fetch is None or field not in board_corroboration.CORROBORATED_FIELDS:
        return []
    soc = board_backfill.resolve_soc(fm, root)
    if not soc:
        return []
    board_id = fm.get("id") or path.parent.name
    toolchain = board_corroboration.consult(fm, board_id, soc, root, [field], fetch)
    return board_corroboration.assess({field: fm[field]}, toolchain)[field]["checks"]


def _memo(fetch):
    cache: dict = {}

    def fetch_once(url: str) -> dict:
        if url not in cache:
            cache[url] = fetch(url)
        return cache[url]
    return fetch_once


def render(report: dict) -> str:
    lines = []
    for e in report["entries"]:
        value = e["value"]["mode"] if isinstance(e["value"], dict) else e["value"]
        line = f"{e['class']}  {e['brand']}/{e['board']}  {e['field']}={value}"
        detail = [f"board {u}" for u in e["board_citations"]]
        detail += [f"toolchain-cited {u}" for u in e["toolchain_citations"]]
        detail += [f"{c['source']} {c['value']} {c['verdict']} {c['url']}" for c in e["checks"]]
        if detail:
            line += f"  ({'; '.join(detail)})"
        lines.append(line)
    lines += [f"unreadable  {p}" for p in report["unreadable"]]
    lines.append("")
    for field, counts in report["counts"].items():
        lines.append(f"{field}: " + ", ".join(f"{c} {counts[c]}" for c in CLASSES))
    return "\n".join(lines)


def main(argv=None, fetch=board_backfill.default_fetch) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--data-dir", default=None, help="data root (default: the repo's data/)")
    ap.add_argument("--offline", action="store_true", help="classify from citations only")
    ap.add_argument("--json", action="store_true", help="print the report as JSON")
    args = ap.parse_args(argv)
    report = audit(args.data_dir, fetch=None if args.offline else fetch)
    print(json.dumps(report, indent=2, default=str) if args.json else render(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
