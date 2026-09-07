#!/usr/bin/env python3
"""Build `data/board_universe.json` — the external board universe esp-atlas ADOPTS (Pillar 1).

SPEC-firmware-boards.md §2: the set of ESP32 boards that exist is a solved, external source of
truth; esp-atlas grounds on it and does not invent its own list. This script materialises that
universe from the two board registries the Arduino/PlatformIO toolchains actually build from,
so the Phase 4 resolver (jr/board_alias.py) can map a firmware's build signals to catalogued
boards by whole-token matching over REAL names — and so a reader can trace every entry to the
file and line that proves it (cite-or-omit, §3).

Sources, each pinned to a commit so the citation is stable and reproducible:

  1. espressif/arduino-esp32 `boards.txt`  → id, name, build.mcu, build.variant, build.board
     url:  https://raw.githubusercontent.com/espressif/arduino-esp32/<sha>/boards.txt
     line: the 1-based line of `<id>.name=` in that file (GitHub cannot render the 3 MB blob,
           so the citation is the raw file plus a line number: `sed -n <line>p` verifies it)
  2. pioarduino/platform-espressif32 `boards/*.json` → id, name, vendor, build.mcu, build.variant, url
     url:  https://github.com/pioarduino/platform-espressif32/blob/<sha>/boards/<id>.json
           (small files; the blob page renders)

`mcu` is mapped to the atlas `soc` id (`esp32s3` → `esp32-s3`) ONLY when that soc record exists
under data/socs/; otherwise `soc` is null and `mcu` is kept verbatim. The artifact carries no
`atlas_id`: resolution is jr/board_alias.py's job and stays out of the data file, so a resolver
change never rewrites the universe. Dates live on `sources[].fetched` (one per source), not on
every entry, so a refresh only rewrites entries whose upstream text changed.

The launcher catalog (giveMeTheList) is deliberately NOT an input: SPEC-flash-catalog.md §3
says it may serve as a popularity signal only, never as a data source.

Usage:
    python3 scripts/build_board_universe.py                       # live fetch, write data/board_universe.json
    python3 scripts/build_board_universe.py --out /tmp/u.json     # elsewhere
    python3 scripts/build_board_universe.py --offline --fixtures DIR   # boards.txt, pio/*.json, refs.json from DIR

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
    """GET `url`. GH_TOKEN goes ONLY to api.github.com (rate limit), never to raw file hosts."""
    headers = {"User-Agent": USER_AGENT}
    if url.startswith("https://api.github.com/") and os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {os.environ['GH_TOKEN']}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _head_sha(repo: str, branch: str, fetch) -> str:
    data = json.loads(fetch(f"https://api.github.com/repos/{repo}/commits/{branch}"))
    return data["sha"]


def arduino_raw_url(sha: str) -> str:
    return f"https://raw.githubusercontent.com/{ARDUINO_REPO}/{sha}/boards.txt"


def pio_blob_url(sha: str, board_id: str) -> str:
    return f"https://github.com/{PIO_REPO}/blob/{sha}/boards/{board_id}.json"


# --- parsing -----------------------------------------------------------------------------------

# STRICT top-level keys only: `<id>.name=` / `<id>.build.mcu=` … where <id> has no dot. A nested
# key such as `esp32s3.menu.PartitionScheme.custom.build.mcu=` or `x.y.name=` must never match.
_BOARDS_TXT_LINE = re.compile(r"^([^.#=\s]+)\.(name|build\.mcu|build\.variant|build\.board)=(.*)$")


def parse_boards_txt(text: str) -> dict[str, dict]:
    """{board_id: {name, mcu, variant, board_define, line}} from arduino-esp32's boards.txt.
    Only top-level `X.name` / `X.build.*` lines count; menu entries (`X.menu.…`) and every other
    key are ignored. `line` is the 1-based line of `X.name=` counted on '\\n' only (what
    `sed -n` and editors count), the citation anchor."""
    out: dict[str, dict] = {}
    for n, raw in enumerate(text.split("\n"), 1):
        m = _BOARDS_TXT_LINE.match(raw.rstrip("\r"))
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

def arduino_entries(text: str, sha: str, known_socs: set[str]) -> list[dict]:
    url = arduino_raw_url(sha)
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
            "url": url,
            "line": rec["line"],
        })
    return entries


def pio_entry(board_id: str, data: dict, sha: str, known_socs: set[str]) -> dict:
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
        "url": pio_blob_url(sha, board_id),
    }


def build_universe(*, boards_txt: str, arduino_sha: str, pio_boards: dict[str, dict], pio_sha: str,
                   today: str, known_socs: set[str] | None = None) -> dict:
    known_socs = known_ids()["soc"] if known_socs is None else known_socs
    boards = arduino_entries(boards_txt, arduino_sha, known_socs)
    boards += [pio_entry(bid, data, pio_sha, known_socs) for bid, data in pio_boards.items()]
    boards.sort(key=lambda b: b["key"])
    return {
        "generated": today,
        "sources": [
            {"name": "arduino-esp32 boards.txt", "repo": ARDUINO_REPO, "ref": arduino_sha,
             "url": arduino_raw_url(arduino_sha), "fetched": today,
             "count": sum(1 for b in boards if b["source"] == "arduino-esp32")},
            {"name": "pioarduino boards/*.json", "repo": PIO_REPO, "ref": pio_sha,
             "url": f"https://github.com/{PIO_REPO}/tree/{pio_sha}/boards", "fetched": today,
             "count": sum(1 for b in boards if b["source"] == "pioarduino")},
        ],
        "boards": boards,
    }


# --- live + offline inputs ---------------------------------------------------------------------

def gather_live(fetch=default_fetch, log=print) -> dict:
    arduino_sha = _head_sha(ARDUINO_REPO, ARDUINO_BRANCH, fetch)
    boards_txt = fetch(arduino_raw_url(arduino_sha)).decode("utf-8")
    log(f"arduino-esp32 boards.txt @ {arduino_sha[:7]}: {len(boards_txt)} bytes")
    pio_sha = _head_sha(PIO_REPO, PIO_BRANCH, fetch)
    listing = json.loads(fetch(f"https://api.github.com/repos/{PIO_REPO}/contents/boards?ref={pio_sha}"))
    names = sorted(item["name"][:-5] for item in listing
                   if item.get("type", "file") == "file" and item.get("name", "").endswith(".json"))
    log(f"pioarduino boards @ {pio_sha[:7]}: {len(names)} files")
    pio_boards = {}
    for i, bid in enumerate(names, 1):
        pio_boards[bid] = json.loads(fetch(f"https://raw.githubusercontent.com/{PIO_REPO}/{pio_sha}/boards/{bid}.json"))
        if i % 50 == 0:
            log(f"  {i}/{len(names)}")
    return {"boards_txt": boards_txt, "arduino_sha": arduino_sha, "pio_boards": pio_boards, "pio_sha": pio_sha}


def gather_offline(fixtures: Path) -> dict:
    """DIR/boards.txt, DIR/pio/<id>.json, DIR/refs.json {arduino_sha, pio_sha}."""
    refs = json.loads((fixtures / "refs.json").read_text(encoding="utf-8")) if (fixtures / "refs.json").exists() else {}
    pio = {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in sorted((fixtures / "pio").glob("*.json"))}
    return {"boards_txt": (fixtures / "boards.txt").read_text(encoding="utf-8"),
            "arduino_sha": refs.get("arduino_sha", "offline"),
            "pio_boards": pio, "pio_sha": refs.get("pio_sha", "offline")}


def write_universe(universe: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(universe, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    ap.add_argument("--offline", action="store_true", help="read inputs from --fixtures instead of the network")
    ap.add_argument("--fixtures", type=Path, default=None)
    ap.add_argument("--today", default=None, help="YYYY-MM-DD for `generated`/`fetched` (default: UTC today)")
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
    print(f"wrote {args.out} — {n} boards ({with_soc} with a catalogued soc)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
