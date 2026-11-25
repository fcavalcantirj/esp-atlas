"""EspAtlas Jr — the build-target producer (jr/build_targets.py; Jr redesign plan, step 8, shadow).

Turns catalog firmware repos into build-target recipes ("At commit S, PlatformIO V resolves env E of repo R to the
board option B") with jr/claims_pio.py + jr/claims_pio_sources.py, and publishes them in ONE separate PR labelled
`jr-data` on a `jr/tick-<stamp>-bt` branch. That PR is judged by the trusted `claims` job and decided by
scripts/data_merge.py; during the shadow `build_target_automerge` stays false, so nothing merges.

Rules:
  - both switches must allow: jr/autonomy.json `build_target_shadow` (ships false) and env JR_BUILD_TARGETS != 0;
  - repos come from the catalog's own firmware records (github.com urls), N per run, round robin; the position
    lives in the runner's state dir (JR_STATE_DIR), never in the repo;
  - a fact is written only when it links to a catalog board through platformio_definitions (board_for) and the
    pair <board>__<firmware> is NOT already a recipe and was NOT removed by a person (jr/overrides, e.g. the
    owner-directed removal of m5stamp-s3__adversary on 2026-11-11): an existing record is never touched;
  - one recipe per pair (the first env in file order), at most MAX_FACTS per PR;
  - the recipe's chip_family is the board's own soc (tools.board_soc); no flash; its source cites the env's
    section line at the pinned commit.

    python3 jr/build_targets.py               # dry run: compute and print the facts, write nothing
    python3 jr/build_targets.py --publish     # write the recipes and open the jr-data PR (switches permitting)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
FLAG, VARIABLE = "build_target_shadow", "JR_BUILD_TARGETS"
MAX_FACTS = 10
REPOS_PER_RUN = 5
LABEL = "jr-data"
_GITHUB = re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s#?]+)")


def enabled(autonomy: dict, env: dict) -> tuple[bool, str]:
    if not (autonomy or {}).get(FLAG):
        return False, f"switch off: jr/autonomy.json {FLAG} is not true"
    if str((env or {}).get(VARIABLE, "")).strip() == "0":
        return False, f"switch off: {VARIABLE}=0"
    return True, "both switches on"


def pick(repos: list[str], cursor: str | None, n: int) -> tuple[list[str], str | None]:
    """The next `n` repos after `cursor` (round robin, wrapping), and the new cursor."""
    if not repos:
        return [], cursor
    start = (repos.index(cursor) + 1) % len(repos) if cursor in repos else 0
    out = [repos[(start + i) % len(repos)] for i in range(min(n, len(repos)))]
    return out, out[-1]


def render(board: str, firmware: str, chip_family: str, claim: dict, today: str) -> tuple[str, str]:
    """(recipe id, recipe.md text) for one build-target fact."""
    rid = f"{board}__{firmware}"
    sec = next((s for s in claim["sections"] if s["name"] == f"env:{claim['env']}"), claim["sections"][0])
    url = f"https://github.com/{claim['repo']['slug']}/blob/{claim['sha']}/{sec['file']}#L{sec['line']}"
    fm = {"id": rid, "type": "recipe", "board": board, "firmware": firmware, "status": "build-target",
          "chip_family": chip_family, "claim": claim,
          "sources": [{"field": "claim", "url": url, "verified": today}]}
    body = (f"# {board} x {firmware}\n\n"
            f"At commit `{claim['sha'][:7]}`, PlatformIO {claim['platformio_version']} resolves the environment "
            f"`{claim['env']}` of `{claim['repo']['slug']}` to the board option `{claim['board_id']}`, which is this "
            f"board's definition. Configuration only: not built or tested on hardware.\n")
    return rid, "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True) + "---\n\n" + body


def blocked_ids(firmware: str, root: Path):
    """The recipe ids a person removed for `firmware` (jr/overrides/<firmware>__edges.json, current and history,
    via writers.removed_recipes): never written back. None when the override exists but cannot be read; the
    caller then writes nothing for that firmware (a broken override never re-enables what a person removed)."""
    import writers
    removed = writers.removed_recipes(firmware, root)
    if removed is writers.UNREADABLE:
        return None
    return {Path(p).parent.name for p in removed}


def plan(per_repo, link, existing: set, cap: int = MAX_FACTS) -> list[tuple]:
    """[(recipe id, board, firmware, claim)] to write. `per_repo`: [(firmware id, slug, [claims])];
    `link(board_id, manifest_digest)` -> catalog board or None; `existing`: recipe ids already in the catalog."""
    out, seen = [], set(existing)
    for firmware, _slug, claims in per_repo:
        for c in claims:
            board = link(c["board_id"], c["platform"]["manifest_digest"])
            rid = f"{board}__{firmware}" if board else None
            if not board or rid in seen:
                continue
            seen.add(rid)
            out.append((rid, board, firmware, c))
            if len(out) >= cap:
                return out
    return out


# --- live run ----------------------------------------------------------------------------------------------

def _catalog(root: Path) -> tuple[list[tuple[str, str]], dict, set]:
    sys.path[:0] = [str(root / "apps" / "core" / "src")]
    from esp_atlas_core.frontmatter import iter_data_files, parse_frontmatter
    firmware, boards, recipes = [], {}, set()
    for kind, path in iter_data_files(root / "data"):
        if kind == "recipe":
            recipes.add(path.parent.name)
            continue
        if kind not in ("firmware", "board"):
            continue
        fm, _ = parse_frontmatter(path)
        if kind == "firmware" and (m := _GITHUB.match(str(fm.get("url") or ""))):
            firmware.append((fm["id"], f"{m.group(1)}/{m.group(2).removesuffix('.git')}"))
        if kind == "board" and fm.get("platformio_definitions"):
            boards[fm["id"]] = fm["platformio_definitions"]
    return sorted(firmware), boards, recipes


def facts_for(slug: str, http, index, workdir: Path) -> list[dict]:
    """Every linked-or-not build-target claim of `slug` at its default branch's commit."""
    import claims_pio as cp
    import claims_pio_sources as src
    proj = src.fetch_project(http, slug, workdir)
    resolved = cp.resolve_project(workdir)
    facts, _refusals = cp.judge(resolved, index)
    return [{"kind": "pio-env", "repo": proj["repo"], "sha": proj["sha"], "env": f["env"], "board_id": f["board_id"],
             "platformio_version": src.platformio_version(), "platform": f["platform"],
             "files": [{"path": p, "blob": proj["blobs"][p]} for p in resolved["loaded"]], "sections": f["sections"]}
            for f in facts]


def main(argv=None) -> int:
    sys.path[:0] = [str(REPO / "jr")]
    import claims_pio_sources as src
    import tools
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--publish", action="store_true", help="write the recipes and open the jr-data PR")
    ap.add_argument("--repos", type=int, default=REPOS_PER_RUN)
    args = ap.parse_args(argv)
    autonomy = json.loads((REPO / "jr" / "autonomy.json").read_text(encoding="utf-8"))
    on, why = enabled(autonomy, dict(os.environ))
    if args.publish and not on:
        print(f"build-targets: {why}; nothing published")
        return 0
    state_dir = Path(os.environ.get("JR_STATE_DIR", Path.home() / ".local" / "state" / "esp-atlas-jr"))
    cursor_file = state_dir / "build_targets_cursor"
    firmware, boards, recipes = _catalog(REPO)
    cursor = cursor_file.read_text().strip() if cursor_file.exists() else None
    batch, new_cursor = pick([f"{fid}\t{slug}" for fid, slug in firmware], cursor, args.repos)
    http = src.Http()
    index = src.PlatformIndex(http)
    per_repo = []
    for item in batch:
        fid, slug = item.split("\t")
        removed = blocked_ids(fid, REPO)
        if removed is None:
            print(f"  {slug}: skipped (its jr/overrides file cannot be read)")
            continue
        recipes |= removed
        try:
            with tempfile.TemporaryDirectory(prefix="bt-") as tmp:
                claims = facts_for(slug, http, index, Path(tmp) / "tree")
        except (src.Unreadable, RuntimeError) as e:
            print(f"  {slug}: skipped ({str(e)[:120]})")
            continue
        print(f"  {slug}: {len(claims)} fact(s)")
        per_repo.append((fid, slug, claims))
    picked = plan(per_repo, lambda bid, dig: src.board_for(bid, dig, boards), recipes)
    today = dt.date.today().isoformat()
    print(f"build-targets {'publish' if args.publish else 'dry run'}: {len(picked)} new linked fact(s) from {len(batch)} repo(s)")
    for rid, board, fid, c in picked:
        print(f"    {rid}  (env {c['env']} -> {c['board_id']} @ {c['sha'][:7]})")
    if args.publish and picked:
        import publish
        wt = publish.add_worktree()
        try:
            paths = []
            for rid, board, fid, c in picked:
                rid, text = render(board, fid, tools.board_soc(board, wt.path), c, today)
                p = Path(wt.path) / "data" / "recipes" / rid / "recipe.md"
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(text, encoding="utf-8")
                paths.append(str(p.relative_to(wt.path)))
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d-%H%M")
            res = publish.publish(wt, paths, f"feat(jr): build-target facts {stamp} ({len(paths)})",
                                  "Build-target facts (configuration only), re-proved by the claims job. Shadow: "
                                  "jr-data-merge decides in dry run; nothing merges.\n",
                                  branch=f"jr/tick-{stamp}-bt", auto_merge=False)
            print(f"  published: {getattr(res, 'pr_url', res)}")
            if getattr(res, "pr_url", None):
                publish.default_gh("pr", "edit", res.pr_url, "--add-label", LABEL)
        finally:
            publish.remove_worktree(wt)
    if new_cursor:
        state_dir.mkdir(parents=True, exist_ok=True)
        cursor_file.write_text(new_cursor)
    return 0


if __name__ == "__main__":
    sys.exit(main())
