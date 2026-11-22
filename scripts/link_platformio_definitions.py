#!/usr/bin/env python3
"""Link catalog boards to the PlatformIO board definitions that ARE them (scripts/link_platformio_definitions.py).

Jr redesign plan, step 3 (2026-11-22). A build-target fact ("at commit S, PlatformIO V resolves env E to the
board option B") reaches a board page only through the board's cited `platformio_definitions`. This resolver
derives those entries from evidence, never from name similarity:

  R1  the board record already cites the definition's manifest file (`.../platform-espressif32/blob/<ref>/
      boards/<id>.json`): the record's authors linked it. Several definitions may link this way (the memory
      variants of one dev-kit, each cited).
  R2  the definition's own manifest `url` (its product page) is one of the board's cited source URLs
      (scheme, `www.` and a trailing slash ignored). R2 alone links at most ONE definition to a board.
  Refused, always: a definition that would link to more than one board; a manifest whose build.mcu disagrees
  with the board's soc; a board with more than one R2-only definition.

Identity is the manifest's bytes. Measured 2026-11-22: a definition's manifest is byte-identical across every
release of its lineage (official v6.9.0 = v6.12.0 = v8.0.0; pioarduino 55.03.37 = 55.03.313 = 61.04.00) and
differs between the two lineages. So each linked lineage gets one entry {id, platform_package, manifest_digest
(sha256 of the manifest file)} and one `platformio_definitions` source citing that manifest at the pinned tag.

    python3 scripts/link_platformio_definitions.py            # plan only: what would link, what is refused
    python3 scripts/link_platformio_definitions.py --apply    # write the entries (verify-before-write)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))
sys.path.insert(0, str(REPO / "jr"))

from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter  # noqa: E402
from writers import _FENCE, _block_span, _key_line  # noqa: E402

# lineage -> (GitHub repo, pinned tag, the package spec an env names)
LINEAGES = {
    "official": ("platformio/platform-espressif32", "v8.0.0", "platformio/espressif32@8.0.0"),
    "pioarduino": ("pioarduino/platform-espressif32", "61.04.00",
                   "https://github.com/pioarduino/platform-espressif32/releases/download/61.04.00/platform-espressif32.zip"),
}
_MANIFEST_REF = re.compile(r"github\.com/(platformio|pioarduino)/platform-espressif32/blob/[^/]+/boards/([^/]+)\.json$")


def norm(url: str | None) -> str:
    u = (url or "").strip().lower()
    u = re.sub(r"^https?://(www\.)?", "", u)
    return u.rstrip("/")


def _soc(value: str | None) -> str:
    return (value or "").replace("-", "").lower()


def plan(boards: dict, manifests: dict) -> tuple[dict, list]:
    """(links {board_id: [definition_id, ...]}, refusals [(board_id, reason)]). Pure.

    `boards`: {id: {"soc": str, "urls": [cited urls]}}; `manifests`: {definition_id: {lineage: {"url", "mcu",
    "digest"}}}."""
    r1, r2 = {}, {}
    by_url: dict[str, set] = {}
    for did, lines in manifests.items():
        for m in lines.values():
            if m.get("url"):
                by_url.setdefault(norm(m["url"]), set()).add(did)
    for bid, b in boards.items():
        cited = [u or "" for u in b.get("urls") or []]
        r1[bid] = {m.group(2) for u in cited if (m := _MANIFEST_REF.search(u)) and m.group(2) in manifests}
        r2[bid] = set().union(*(by_url.get(norm(u), set()) for u in cited)) if cited else set()
    claimed: dict[str, set] = {}
    for bid in boards:
        for did in r1[bid] | r2[bid]:
            claimed.setdefault(did, set()).add(bid)
    links, refusals = {}, []
    for bid, b in sorted(boards.items()):
        r2_only = r2[bid] - r1[bid]
        if len(r2_only) > 1 or (r2_only and r1[bid]):
            refusals.append((bid, f"several definitions by product url only: {sorted(r2_only)}"))
            continue
        ids = []
        for did in sorted(r1[bid] | r2[bid]):
            if len(claimed[did]) > 1:
                refusals.append((bid, f"{did} would link to several boards: {sorted(claimed[did])}"))
                continue
            mcus = {_soc(m.get("mcu")) for m in manifests[did].values()}
            if b.get("soc") and _soc(b["soc"]) not in mcus:
                refusals.append((bid, f"{did} mcu {sorted(mcus)} != board soc {b['soc']}"))
                continue
            ids.append(did)
        if ids:
            links[bid] = ids
    return links, refusals


def entries_for(ids: list[str], manifests: dict) -> tuple[list[dict], list[str]]:
    """(platformio_definitions entries, manifest urls to cite) for the linked definition ids."""
    entries, urls = [], []
    for did in ids:
        for lineage, (repo, tag, package) in LINEAGES.items():
            m = manifests[did].get(lineage)
            if not m:
                continue
            entries.append({"id": did, "platform_package": package, "manifest_digest": m["digest"]})
            urls.append(f"https://github.com/{repo}/blob/{tag}/boards/{did}.json")
    return entries, urls


def write_definitions(board_md: Path, entries: list[dict], urls: list[str], today: str) -> bool:
    """Set `platformio_definitions` and append one `field: platformio_definitions` source per manifest url.
    Verify-before-write: the result is re-parsed; every other key must be byte-identical and the new values
    exact, or ValueError and the file is untouched. Returns True when the file changed."""
    with open(board_md, encoding="utf-8", newline="") as f:
        text = f.read()
    m = _FENCE.match(text)
    if not m:
        raise ValueError(f"{board_md}: no frontmatter fence")
    head, rest = m.group(1), text[m.end():]
    old = yaml.safe_load(head)
    if old.get("platformio_definitions") == entries:
        return False
    if "platformio_definitions" in old:
        raise ValueError(f"{board_md}: already has different platformio_definitions; refusing to overwrite")
    lines = head.split("\n")
    s = _key_line(lines, "sources")
    if s is None or not re.match(r"^\s*(#.*)?$", lines[s][len("sources:"):]):
        raise ValueError(f"{board_md}: sources is not a block list")
    end, ind = _block_span(lines, s)
    new_sources = []
    for u in urls:
        new_sources += [f"{ind}- field: platformio_definitions", f"{ind}  url: {u}", f"{ind}  verified: '{today}'"]
    lines[end:end] = new_sources
    block = ["platformio_definitions:"]
    for e in entries:
        block += [f"- id: {e['id']}", f"  platform_package: {e['platform_package']}", f"  manifest_digest: {e['manifest_digest']}"]
    lines[s:s] = block
    new_head = "\n".join(lines)
    new = yaml.safe_load(new_head)
    expect = dict(old, platformio_definitions=entries)
    expect["sources"] = list(old["sources"]) + [{"field": "platformio_definitions", "url": u, "verified": today} for u in urls]
    if new != expect:
        raise ValueError(f"{board_md}: the edit would change more than platformio_definitions and its sources")
    out = text[:m.start(1)] + new_head + text[m.end(1):]
    with open(board_md, "w", encoding="utf-8", newline="") as f:
        f.write(out)
    return True


def fetch_manifests() -> dict:
    def ls(repo, tag):
        req = urllib.request.Request(f"https://api.github.com/repos/{repo}/contents/boards?ref={tag}",
                                     headers={"Accept": "application/vnd.github+json", "User-Agent": "esp-atlas"})
        tok = __import__("os").environ.get("GH_TOKEN") or __import__("os").environ.get("GITHUB_TOKEN")
        if tok:
            req.add_header("Authorization", f"Bearer {tok}")
        with urllib.request.urlopen(req, timeout=60) as r:
            return [x["name"] for x in json.load(r) if x["name"].endswith(".json")]

    def one(job):
        lineage, repo, tag, name = job
        with urllib.request.urlopen(f"https://raw.githubusercontent.com/{repo}/{tag}/boards/{name}", timeout=60) as r:
            raw = r.read()
        d = json.loads(raw)
        return name[:-5], lineage, {"url": d.get("url"), "mcu": (d.get("build") or {}).get("mcu"),
                                    "digest": hashlib.sha256(raw).hexdigest()}

    jobs = [(lin, repo, tag, n) for lin, (repo, tag, _pkg) in LINEAGES.items() for n in ls(repo, tag)]
    out: dict = {}
    with ThreadPoolExecutor(12) as ex:
        for did, lineage, m in ex.map(one, jobs):
            out.setdefault(did, {})[lineage] = m
    return out


def catalog_boards() -> dict:
    out = {}
    for kind, path in iter_data_files():
        if kind == "board":
            fm, _ = parse_frontmatter(path)
            out[fm["id"]] = {"soc": fm.get("soc"), "urls": [s.get("url") for s in fm.get("sources") or []], "path": path}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--today", default=dt.date.today().isoformat())
    args = ap.parse_args(argv)
    manifests = fetch_manifests()
    boards = catalog_boards()
    links, refusals = plan(boards, manifests)
    print(f"{len(manifests)} definitions read ({', '.join(f'{k} {v[1]}' for k, v in LINEAGES.items())}); "
          f"{len(boards)} boards; {len(links)} linked; {len(refusals)} refused")
    changed = 0
    for bid, ids in sorted(links.items()):
        entries, urls = entries_for(ids, manifests)
        print(f"  link {bid}: {', '.join(ids)} ({len(entries)} entries)")
        if args.apply and write_definitions(boards[bid]["path"], entries, urls, args.today):
            changed += 1
    for bid, why in refusals:
        print(f"  refuse {bid}: {why}")
    if args.apply:
        print(f"{changed} board record(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
