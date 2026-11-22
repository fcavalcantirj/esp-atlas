#!/usr/bin/env python3
"""Re-prove every build-target claim a change adds (scripts/check_claims.py; Jr redesign plan, step 5).

A build-target recipe says: "At commit S, PlatformIO V resolves env E of repo R to the board option B". This
checker trusts nothing in the record. For each added or changed build-target recipe it:

  1. re-reads repo R's numeric id from the API, and the numeric id of the repo the recipe's FIRMWARE record
     points at; both must equal the claim's (a claim about repo A never sits on firmware B);
  2. re-derives the whole claim from R, S and E alone (jr/claims_pio_sources.claim_for: the tree at S, the
     config files and their blob shas, PlatformIO's own hermetic resolution, every refusal rule, the platform
     package verified against the vendor's digest, the manifest from inside it), and requires it to equal the
     recorded claim field by field, PlatformIO version included;
  3. requires the recipe's board to be the one catalog board whose cited platformio_definitions list exactly
     (board_id, manifest_digest), and the recipe to be status build-target with no flash.

Verdicts: PASS (all hold) · FAIL (any differs) · INCONCLUSIVE (a source could not be read; never a pass).
Exit 0 only when every checked recipe PASSes; 1 on any FAIL; 3 on INCONCLUSIVE without FAIL.

    python3 scripts/check_claims.py                  # recipes the branch adds/changes vs origin/main
    python3 scripts/check_claims.py --all            # every build-target recipe in the catalog
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(REPO / "jr"), str(REPO / "apps" / "core" / "src")]

import claims_pio_sources as src  # noqa: E402

PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"
_GITHUB = re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s#?]+)")


def check_recipe(recipe: dict, firmware: dict, catalog: dict, http, platform_index, workdir=None) -> dict:
    """{"id", "verdict", "reasons"} for one build-target recipe."""
    reasons, rid = [], recipe.get("id")
    claim = recipe.get("claim") or {}
    if recipe.get("status") != "build-target":
        reasons.append(f"status is {recipe.get('status')!r}, not build-target")
    if "flash" in recipe:
        reasons.append("a build-target never carries flash")
    try:
        slug, sha, env = claim["repo"]["slug"], claim["sha"], claim["env"]
        meta = http.json(f"https://api.github.com/repos/{slug}")
        if meta.get("id") != claim["repo"]["id"]:
            reasons.append(f"repo id: {slug} is {meta.get('id')}, the claim says {claim['repo']['id']}")
        m = _GITHUB.match(str(firmware.get("url") or ""))
        if not m:
            reasons.append(f"repo id: firmware {firmware.get('id')} has no github.com url")
        else:
            fw = http.json(f"https://api.github.com/repos/{m.group(1)}/{m.group(2).removesuffix('.git')}")
            if fw.get("id") != claim["repo"]["id"]:
                reasons.append(f"repo id: firmware {firmware.get('id')} is repo {fw.get('id')}, the claim's is {claim['repo']['id']}")
        with tempfile.TemporaryDirectory(prefix="check-claims-") as tmp:
            try:
                again = src.claim_for(http, slug, sha, env, platform_index, Path(workdir or tmp) / "tree")
            except ValueError as e:
                again = None
                reasons.append(f"env {env} is refused at {sha[:7]}: {e}")
        if again is not None:
            for key in ("board_id", "platformio_version", "files", "sections"):
                if again[key] != claim.get(key):
                    label = "platformio version" if key == "platformio_version" else key.replace("_id", "")
                    reasons.append(f"{label} differs: recorded {claim.get(key)!r:.120}, re-derived {again[key]!r:.120}")
            for key in ("spec", "package_digest", "manifest_digest"):
                if again["platform"][key] != (claim.get("platform") or {}).get(key):
                    label = {"package_digest": "package", "manifest_digest": "manifest", "spec": "platform"}[key]
                    reasons.append(f"{label} digest/spec differs: recorded {(claim.get('platform') or {}).get(key)!r}, re-derived {again['platform'][key]!r}")
        page = src.board_for(claim.get("board_id"), (claim.get("platform") or {}).get("manifest_digest"), catalog)
        if page != recipe.get("board"):
            reasons.append(f"board page: the definition links to {page!r}, the recipe names {recipe.get('board')!r}")
    except src.Unreadable as e:
        return {"id": rid, "verdict": INCONCLUSIVE, "reasons": reasons + [str(e)]}
    except (KeyError, TypeError) as e:
        reasons.append(f"claim is malformed: {e!r}")
    return {"id": rid, "verdict": FAIL if reasons else PASS, "reasons": reasons}


def _catalog(data_dir: Path) -> tuple[dict, dict]:
    from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter
    boards, firmware = {}, {}
    for kind, path in iter_data_files(data_dir):
        if kind in ("board", "firmware"):
            fm, _ = parse_frontmatter(path)
            if kind == "board" and fm.get("platformio_definitions"):
                boards[fm["id"]] = fm["platformio_definitions"]
            if kind == "firmware":
                firmware[fm["id"]] = fm
    return boards, firmware


def _targets(all_: bool, base: str, pr_dir: Path) -> list[Path]:
    if all_:
        return sorted((pr_dir / "data" / "recipes").glob("*/recipe.md"))
    out = subprocess.run(["git", "diff", "--name-only", "--diff-filter=AM", f"{base}...HEAD", "--", "data/recipes"],
                         cwd=pr_dir, capture_output=True, text=True, check=True).stdout.split()
    return [pr_dir / p for p in out if p.endswith("recipe.md")]


def main(argv=None) -> int:
    from esp_atlas_core.frontmatter import parse_frontmatter
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--base", default="origin/main")
    ap.add_argument("--data-dir", default=str(REPO / "data"), help="catalog the board links are read from (trusted: main's)")
    ap.add_argument("--pr-dir", default=str(REPO), help="checkout whose recipes and firmware are judged (CI: the PR, as data)")
    args = ap.parse_args(argv)
    boards, _ = _catalog(Path(args.data_dir))
    _, firmware = _catalog(Path(args.pr_dir) / "data")
    http, index = src.Http(), None
    index = src.PlatformIndex(http)
    results = []
    for path in _targets(args.all, args.base, Path(args.pr_dir)):
        fm, _ = parse_frontmatter(path)
        if fm.get("status") != "build-target" and "claim" not in fm:
            continue
        results.append(check_recipe(fm, firmware.get(fm.get("firmware")) or {}, boards, http, index))
    for r in results:
        print(f"{r['verdict']:12s} {r['id']}" + "".join(f"\n    {x}" for x in r["reasons"]))
    counts = {v: sum(1 for r in results if r["verdict"] == v) for v in (PASS, FAIL, INCONCLUSIVE)}
    print(f"\n{len(results)} build-target recipe(s): {counts[PASS]} PASS, {counts[FAIL]} FAIL, {counts[INCONCLUSIVE]} INCONCLUSIVE")
    return 1 if counts[FAIL] else 3 if counts[INCONCLUSIVE] else 0


if __name__ == "__main__":
    sys.exit(main())
