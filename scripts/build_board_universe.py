#!/usr/bin/env python3
"""Build `data/board_universe.json` — the canonical board universe esp-atlas ADOPTS (Pillar 1).

SPEC-firmware-boards.md §2: the set of ESP32 boards that exist is a solved, external source of
truth; esp-atlas grounds on it and does not invent its own list. This script materialises that
universe from the two official board registries plus the launcher's device categories, so the
Phase 4 resolver (jr/board_alias.py) can map a firmware's build signals to catalogued boards
by whole-token matching over REAL names — and so a reader can trace every entry to the line
that proves it (cite-or-omit, §3).

Sources, each pinned to a commit so the citation URL is stable:

  1. espressif/arduino-esp32 `boards.txt`  → id, name, build.mcu, build.variant, build.board
     url: https://github.com/espressif/arduino-esp32/blob/<sha>/boards.txt#L<line of X.name>
  2. pioarduino/platform-espressif32 `boards/*.json` → id, name, vendor, build.mcu, build.variant, url
     url: https://github.com/pioarduino/platform-espressif32/blob/<sha>/boards/<id>.json
  3. launcherhub `giveMeTheList` → per-category counts and chip (`esp`) histogram, so the alias
     table can learn which launcher category means which board. Counts only, no entries.

`mcu` is mapped to the atlas `soc` id (`esp32s3` → `esp32-s3`) ONLY when that soc record exists
under data/socs/; otherwise `soc` is null and `mcu` is kept verbatim. The artifact carries no
`atlas_id`: resolution is jr/board_alias.py's job and stays out of the data file, so a resolver
change never rewrites the universe.

Usage:
    python3 scripts/build_board_universe.py                       # live fetch, write data/board_universe.json
    python3 scripts/build_board_universe.py --out /tmp/u.json     # elsewhere
    python3 scripts/build_board_universe.py --offline --fixtures DIR   # boards.txt, pio/*.json, launcher.json from DIR

Deterministic: sorted keys, sorted entries, `generated` = --today or the UTC date. Never run in
the blocking CI job (network); intended for a manual/weekly refresh whose diff is reviewed.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))
from esp_atlas_core.validate import known_ids  # noqa: E402

OUT_DEFAULT = REPO / "data" / "board_universe.json"
ARDUINO_REPO = "espressif/arduino-esp32"
ARDUINO_BRANCH = "master"
PIO_REPO = "pioarduino/platform-espressif32"
PIO_BRANCH = "develop"
LAUNCHERHUB = "https://api.launcherhub.net/giveMeTheList"
USER_AGENT = "esp-atlas-board-universe/0.1"

# arduino/platformio `build.mcu` → atlas soc id (data/socs/<id>). The map is intentionally
# mechanical (insert the hyphen); the soc must ALSO exist in the catalog to be written.
_MCU_TO_SOC = {
    "esp32": "esp32", "esp32s2": "esp32-s2", "esp32s3": "esp32-s3", "esp32c2": "esp32-c2",
    "esp32c3": "esp32-c3", "esp32c5": "esp32-c5", "esp32c6": "esp32-c6", "esp32c61": "esp32-c61",
    "esp32h2": "esp32-h2", "esp32h4": "esp32-h4", "esp32p4": "esp32-p4",
}


# --- fetching ----------------------------------------------------------------------------------

def default_fetch(url: str, timeout: float = 60.0) -> bytes:
    headers = {"User-Agent": USER_AGENT}
    if "api.github.com" in url and os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _head_sha(repo: str, branch: str, fetch) -> str:
    data = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits/{branch}"))
    return data["sha"]


# --- parsing -----------------------------------------------------------------------------------

_BOARDS_TXT_LINE = re.compile(r"^([^.#=\s]+)\.(name|build\.mcu|build\.variant|build\.board)=(.*)$")


def parse_boards_txt(text: str) -> dict[str, dict]:
    """{board_id: {name, mcu, variant, board_define, line}} from arduino-esp32's boards.txt.
    Only top-level `X.name` / `X.build.*` lines count; menu entries (`X.menu.…`) and every other
    key are ignored. `line` is the 1-based line of `X.name=`, the citation anchor."""
    out: dict[str, dict] = {}
    for n, raw in enumerate(text.splitlines(), 1):
        m = _BOARDS_TXT_LINE.match(raw)
        if not m:
            continue
        bid, key, val = m.group(1), m.group(2), m.group(3).strip()
        rec = out.setdefault(bid, {})
        if key == "name":
            rec["name"] = val
            rec["line"] = n
        elif key == "build.mcu":
            rec["mcu"] = val
        elif key == "build.variant":
            rec["variant"] = val
        elif key == "build.board":
            rec["board_define"] = val
    return {bid: rec for bid, rec in out.items() if "name" in rec}


def soc_for(mcu: str | None, known_socs: set[str]) -> str | None:
    soc = _MCU_TO_SOC.get((mcu or "").lower())
    return soc if soc in known_socs else None


# --- assembling ------------------------------------------------------------------------------

def arduino_entries(text: str, sha: str, known_socs: set[str], today: str) -> list[dict]:
    entries = []
    for bid, rec in parse_boards_txt(text).items():
        entries.append({
            "key": f"arduino-esp32:{bid}",
            "source": "arduino-esp32",
            "id": bid,
            "name": rec["name"],
            "mcu": rec.get("mcu"),
            "soc": soc_for(rec.get("mcu"), known_socs),
            "variant": rec.get("variant"),
            "board_define": rec.get("board_define"),
            "url": f"https://github.com/{ARDUINO_REPO}/blob/{sha}/boards.txt#L{rec['line']}",
            "verified": today,
        })
    return entries


def pio_entry(board_id: str, data: dict, sha: str, known_socs: set[str], today: str) -> dict:
    build = data.get("build") or {}
    return {
        "key": f"pioarduino:{board_id}",
        "source": "pioarduino",
        "id": board_id,
        "name": data.get("name"),
        "vendor": data.get("vendor"),
        "mcu": build.get("mcu"),
        "soc": soc_for(build.get("mcu"), known_socs),
        "variant": build.get("variant"),
        "vendor_url": data.get("url"),
        "url": f"https://github.com/{PIO_REPO}/blob/{sha}/boards/{board_id}.json",
        "verified": today,
    }


def launcher_categories(entries: list[dict]) -> dict[str, dict]:
    """{category: {"count": n, "esp": {chip: n}}} — the launcher's own device buckets."""
    cats: dict[str, dict] = {}
    for e in entries:
        cat = (e.get("category") or "").strip().lower()
        if not cat:
            continue
        c = cats.setdefault(cat, {"count": 0, "esp": {}})
        c["count"] += 1
        esp = str(e.get("esp") or "").strip().lower() or "unknown"
        c["esp"][esp] = c["esp"].get(esp, 0) + 1
    return {k: {"count": v["count"], "esp": dict(sorted(v["esp"].items()))} for k, v in sorted(cats.items())}


def build_universe(*, boards_txt: str, arduino_sha: str, pio_boards: dict[str, dict], pio_sha: str,
                   launcher: list[dict], today: str, known_socs: set[str] | None = None) -> dict:
    known_socs = known_ids()["soc"] if known_socs is None else known_socs
    boards = arduino_entries(boards_txt, arduino_sha, known_socs, today)
    boards += [pio_entry(bid, data, pio_sha, known_socs, today) for bid, data in pio_boards.items()]
    boards.sort(key=lambda b: b["key"])
    return {
        "generated": today,
        "sources": [
            {"name": "arduino-esp32 boards.txt", "repo": ARDUINO_REPO, "ref": arduino_sha,
             "url": f"https://github.com/{ARDUINO_REPO}/blob/{arduino_sha}/boards.txt",
             "count": sum(1 for b in boards if b["source"] == "arduino-esp32")},
            {"name": "pioarduino boards/*.json", "repo": PIO_REPO, "ref": pio_sha,
             "url": f"https://github.com/{PIO_REPO}/tree/{pio_sha}/boards",
             "count": sum(1 for b in boards if b["source"] == "pioarduino")},
            {"name": "launcherhub giveMeTheList", "url": LAUNCHERHUB, "count": len(launcher)},
        ],
        "boards": boards,
        "launcher_categories": launcher_categories(launcher),
    }


# --- live + offline inputs ---------------------------------------------------------------------

def gather_live(fetch=default_fetch, log=print) -> dict:
    arduino_sha = _head_sha(ARDUINO_REPO, ARDUINO_BRANCH, fetch)
    boards_txt = fetch(f"https://raw.githubusercontent.com/{ARDUINO_REPO}/{arduino_sha}/boards.txt").decode("utf-8", "replace")
    log(f"arduino-esp32 boards.txt @ {arduino_sha[:7]}: {len(boards_txt)} bytes")
    pio_sha = _head_sha(PIO_REPO, PIO_BRANCH, fetch)
    listing = json.loads(fetch(f"https://api.github.com/repos/{PIO_REPO}/contents/boards?ref={pio_sha}"))
    names = sorted(item["name"][:-5] for item in listing if item.get("name", "").endswith(".json"))
    log(f"pioarduino boards @ {pio_sha[:7]}: {len(names)} files")
    pio_boards = {}
    for i, bid in enumerate(names, 1):
        pio_boards[bid] = json.loads(fetch(f"https://raw.githubusercontent.com/{PIO_REPO}/{pio_sha}/boards/{bid}.json"))
        if i % 50 == 0:
            log(f"  {i}/{len(names)}")
    launcher = json.loads(fetch(LAUNCHERHUB))
    if isinstance(launcher, dict):
        launcher = launcher.get("data") or launcher.get("list") or []
    log(f"launcher entries: {len(launcher)}")
    return {"boards_txt": boards_txt, "arduino_sha": arduino_sha, "pio_boards": pio_boards,
            "pio_sha": pio_sha, "launcher": launcher}


def gather_offline(fixtures: Path) -> dict:
    """DIR/boards.txt, DIR/pio/<id>.json, DIR/launcher.json, DIR/refs.json {arduino_sha, pio_sha}."""
    refs = json.loads((fixtures / "refs.json").read_text()) if (fixtures / "refs.json").exists() else {}
    pio = {p.stem: json.loads(p.read_text()) for p in sorted((fixtures / "pio").glob("*.json"))}
    launcher = json.loads((fixtures / "launcher.json").read_text()) if (fixtures / "launcher.json").exists() else []
    return {"boards_txt": (fixtures / "boards.txt").read_text(), "arduino_sha": refs.get("arduino_sha", "offline"),
            "pio_boards": pio, "pio_sha": refs.get("pio_sha", "offline"), "launcher": launcher}


def write_universe(universe: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(universe, indent=1, sort_keys=True, ensure_ascii=False) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--offline", action="store_true", help="read inputs from --fixtures instead of the network")
    ap.add_argument("--fixtures", type=Path, default=None)
    ap.add_argument("--today", default=None, help="YYYY-MM-DD for `generated`/`verified` (default: UTC today)")
    args = ap.parse_args(argv)
    today = args.today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if args.offline:
        if not args.fixtures:
            ap.error("--offline needs --fixtures DIR")
        inputs = gather_offline(args.fixtures)
    else:
        inputs = gather_live()
    universe = build_universe(today=today, **inputs)
    write_universe(universe, args.out)
    n = len(universe["boards"])
    with_soc = sum(1 for b in universe["boards"] if b["soc"])
    print(f"wrote {args.out} — {n} boards ({with_soc} with a catalogued soc), "
          f"{len(universe['launcher_categories'])} launcher categories")
    return 0


if __name__ == "__main__":
    sys.exit(main())
