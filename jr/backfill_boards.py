"""EspAtlas Jr — firmware->board audit + backfill driver (jr/backfill_boards.py).

Phase 3 (SPEC-firmware-board-mapping.md §6-§7). Builds on jr/board_declared.extract_declared_boards
(the multi-source raw-ref reader — manifest tree + README device table) and jr/board_resolver (raw
ref -> catalog board id). board_resolver.resolve_boards() is hardwired to the REAL catalog
(data/boards/, read live — same binding its own oracle relies on), so chip_family lookups here use
tools.board_soc()'s own default (`repo=tools.REPO`, the real catalog) too: resolution and chip
lookup read the same source of truth. Only the firmware/recipe TREE being audited or backfilled is
parameterised by `root` — the real repo in production, a tmp copy in tests.

Three surfaces, one report shape:

  1. audit(root, fids=None, ...) / audit_one(fid, ...) — for one firmware or every catalogued
     firmware with a GitHub url, diff its freshly-extracted declared boards against its CURRENT
     recipes (data/recipes/<board>__<fid>/):
       added                  declared+resolved boards that lack a recipe
       present                declared+resolved boards that already have a recipe
       stale_seed             a recipe exists but no declared source names that board (SPEC §0's
                              genesis-seed problem — a mapping frozen without a repo source)
       unresolved_candidates  declared raw refs that did not resolve to a catalog board id
       socs_delta             declared socs not yet in the firmware record's own `socs:`
       resolved               board_id -> {source_url, source_type}, apply()'s provenance
     Plus a catalog coverage metric: % of considered firmware with >=1 declared-sourced board.
  2. dry_run(...) — audit()'s report; writes nothing (audit() itself never writes — this name
     exists so a caller matches SPEC §7's "dry-run diff report" vocabulary).
  3. apply(report, root, today) — for every ADDED resolved edge, writes
     data/recipes/<board>__<firmware>/recipe.md (status: declared, one `field: boards` source
     citing where the board was declared). Widens each touched firmware's `socs:` to the union
     with its socs_delta (writers.merge_socs — never narrows, verifies its own rewrite). Never
     writes a recipe for an unresolved candidate (those come back as a ranked `candidates` report
     instead — SPEC §4's "growth lever, not an error to swallow"); never touches a stale_seed
     recipe (flagged in the audit report only). Additive + idempotent: an existing recipe dir is
     never rewritten, and merge_socs is itself a no-op once the socs are already merged — a
     second apply() over the same report, or a fresh audit() of the result, writes nothing further.

Never touches the network itself — `manifest_api`/`readme_fetch` are the same injected callables
board_declared.py's own oracle uses; a real run wires them to derive.default_api /
tools.fetch_github_readme (board_declared.extract_declared_boards' own defaults, via `None`).
"""
from __future__ import annotations

from pathlib import Path

import board_declared
import stage_boardmap
import tools
import writers


def _current_recipe_boards(root: Path, fid: str) -> list[str]:
    return sorted(p.name[: -(len(fid) + 2)] for p in (root / "data" / "recipes").glob(f"*__{fid}") if p.is_dir())


def audit_one(fid: str, *, root: Path, manifest_api, readme_fetch, ref: str | None = None) -> dict:
    """One firmware's declared-vs-mapped diff. `ref` defaults to the repo's default branch
    (resolved by board_declared.extract_declared_boards itself via `manifest_api`). Returns
    {"firmware": fid, "skipped": <reason>} when the record has no GitHub url — nothing to read."""
    fmd = root / "data" / "firmware" / fid / "firmware.md"
    fm = tools._frontmatter(fmd)
    owner_repo = stage_boardmap.owner_repo_of(fm.get("url", ""))
    if not owner_repo:
        return {"firmware": fid, "skipped": "no GitHub url"}

    declared = board_declared.extract_declared_boards(owner_repo, ref, manifest_api=manifest_api, readme_fetch=readme_fetch)
    declared_boards = set(declared["resolved"])
    current = set(_current_recipe_boards(root, fid))
    current_socs = set(fm.get("socs") or [])

    return {
        "firmware": fid,
        "owner_repo": owner_repo,
        "added": sorted(declared_boards - current),
        "present": sorted(declared_boards & current),
        "stale_seed": sorted(current - declared_boards),
        "unresolved_candidates": sorted(declared["unresolved"]),
        "socs_delta": sorted(set(declared["socs"]) - current_socs),
        "resolved": declared["resolved"],
    }


def audit(root: Path, fids: list[str] | None = None, *, manifest_api, readme_fetch) -> dict:
    """Every considered firmware's audit_one() report, plus the catalog coverage metric (SPEC §6:
    "% firmware with >=1 declared-sourced board"). `fids` narrows to specific ids; None audits
    every catalogued firmware with a `firmware.md`."""
    if fids is None:
        fids = sorted(p.parent.name for p in (root / "data" / "firmware").glob("*/firmware.md"))
    reports = {fid: audit_one(fid, root=root, manifest_api=manifest_api, readme_fetch=readme_fetch) for fid in fids}
    considered = [r for r in reports.values() if not r.get("skipped")]
    with_declared = sum(1 for r in considered if r["resolved"])
    coverage = {
        "considered": len(considered),
        "with_declared_board": with_declared,
        "pct": round(100 * with_declared / len(considered), 1) if considered else 0.0,
    }
    return {"firmware": reports, "coverage": coverage}


def dry_run(root: Path, fids: list[str] | None = None, *, manifest_api, readme_fetch) -> dict:
    """SPEC §7's dry-run diff report: audit()'s output, guaranteed read-only."""
    return audit(root, fids, manifest_api=manifest_api, readme_fetch=readme_fetch)


def _render_declared_recipe(board: str, firmware: str, chip_family: str, source_url: str, source_type: str, today: str) -> str:
    what = source_type.replace("_", " ")
    return (
        "---\n"
        f"id: {board}__{firmware}\n"
        "type: recipe\n"
        f"board: {board}\n"
        f"firmware: {firmware}\n"
        "status: declared\n"
        f"chip_family: {chip_family}\n"
        "sources:\n"
        "- field: boards\n"
        f"  url: {source_url}\n"
        f"  verified: '{today}'\n"
        "---\n\n"
        f"# {board} x {firmware}\n\n"
        f"`{firmware}` declares `{board}` ({chip_family}) in its {what}. "
        "Status `declared` until a build/flasher manifest or a human confirms it on hardware.\n"
    )


def _candidate_boards_report(report: dict) -> list[dict]:
    """Unresolved raw refs across every audited firmware, ranked by how many firmware reference
    them (SPEC §4: "a growth lever for the board catalog, not an error to swallow")."""
    by_name: dict[str, set[str]] = {}
    for fid, r in report.get("firmware", {}).items():
        if r.get("skipped"):
            continue
        for raw in r["unresolved_candidates"]:
            by_name.setdefault(raw, set()).add(fid)
    return sorted(
        ({"name": name, "firmware": sorted(fids), "count": len(fids)} for name, fids in by_name.items()),
        key=lambda c: (-c["count"], c["name"]),
    )


def apply(report: dict, *, root: Path, today: str) -> dict:
    """Write the missing recipes for every ADDED resolved edge in an audit()/dry_run() report,
    widen each firmware's socs to the union with its socs_delta. Returns
    {"written": [recipe_id, ...], "socs_widened": {fid: [soc, ...]}, "candidates": [...]}."""
    written: list[str] = []
    socs_widened: dict[str, list[str]] = {}

    for fid, r in report.get("firmware", {}).items():
        if r.get("skipped"):
            continue
        fmd = root / "data" / "firmware" / fid / "firmware.md"
        for board in r["added"]:
            rid = f"{board}__{fid}"
            rdir = root / "data" / "recipes" / rid
            if (rdir / "recipe.md").exists():
                continue                              # idempotent: already written by an earlier apply()
            chip = tools.board_soc(board)
            if not chip:
                continue                              # never write an unresolvable chip_family
            prov = r["resolved"][board]
            rdir.mkdir(parents=True, exist_ok=True)
            (rdir / "recipe.md").write_text(
                _render_declared_recipe(board, fid, chip, prov["source_url"], prov["source_type"], today),
                encoding="utf-8",
            )
            written.append(rid)
        if r["socs_delta"]:
            urls = list(dict.fromkeys(
                r["resolved"][b]["source_url"]
                for b in r["added"] + r["present"]
                if r["resolved"].get(b) and tools.board_soc(b) in r["socs_delta"]
            ))
            if urls and writers.merge_socs(fmd, r["socs_delta"], urls, today):
                socs_widened[fid] = r["socs_delta"]

    return {"written": written, "socs_widened": socs_widened, "candidates": _candidate_boards_report(report)}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import derive

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--firmware", nargs="*", help="one or more firmware ids (default: every catalogued firmware)")
    ap.add_argument("--apply", action="store_true", help="write recipes + widen socs (default: dry-run, no writes)")
    ap.add_argument("--today", default=None, help="YYYY-MM-DD to stamp new sources with (default: today, UTC)")
    args = ap.parse_args(argv)

    from datetime import datetime, timezone
    today = args.today or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    report = audit(tools.REPO, args.firmware, manifest_api=derive.default_api, readme_fetch=None)
    cov = report["coverage"]
    print(f"coverage: {cov['with_declared_board']}/{cov['considered']} firmware ({cov['pct']}%) have >=1 declared-sourced board")
    for fid, r in sorted(report["firmware"].items()):
        if r.get("skipped"):
            print(f"{fid}: skipped ({r['skipped']})")
            continue
        print(f"{fid}: +{len(r['added'])} added, {len(r['present'])} present, "
              f"{len(r['stale_seed'])} stale_seed, {len(r['unresolved_candidates'])} unresolved, "
              f"socs +{r['socs_delta']}")

    if args.apply:
        out = apply(report, root=tools.REPO, today=today)
        print(f"applied: {len(out['written'])} recipe(s) written, socs widened for {len(out['socs_widened'])} firmware")
        if out["candidates"]:
            print(f"candidate boards ({len(out['candidates'])}):")
            for c in out["candidates"][:20]:
                print(f"  {c['name']} — referenced by {c['count']} firmware: {', '.join(c['firmware'])}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
