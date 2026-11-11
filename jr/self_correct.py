"""EspAtlas Jr: retract its own wrong recipes (SPEC-firmware-board-mapping.md section 4.1).

jr/derive.resolve() can learn that a board id only proves the chip. When that happens for a recipe Jr
already wrote, this module removes the recipe and writes the audited override `scripts/g2_guard.py`
requires, with the byte-exact original so it can be restored. Deterministic, and only on positive
evidence: a signal that was read and classified, never a signal that went missing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import tools
from review_routing import SELF_CORRECTION_AUTHOR, SELF_CORRECTION_CLASSES

_SHA = re.compile(r"[0-9a-f]{40}")


def plan(fid: str, resolved: dict, root: Path) -> tuple[list[dict], list[str]]:
    """(recipes to retract, notes). See the SPEC for every condition; any doubt retracts nothing."""
    recipes = root / "data" / "recipes"
    picks, seen = [], set()
    for s in resolved["unresolved"]:
        board, env = s.get("atlas_id"), str((s.get("extra") or {}).get("env") or "")
        if s.get("how") not in SELF_CORRECTION_CLASSES or not board or (board, env) in seen:
            continue
        seen.add((board, env))
        md = recipes / f"{board}__{fid}" / "recipe.md"
        if resolved["boards"].get(board) or not md.exists():
            continue
        fm = tools._frontmatter(md)
        if fm.get("status") == "unverified" and (fm.get("flash") or {}).get("env") == env:
            picks.append({"board": board, "recipe": f"{board}__{fid}", "env": env, "signal": s, "path": md})
    if not picks:
        return [], []
    if (root / "jr" / "overrides" / f"{fid}__edges.json").exists():
        return [], [f"retraction deferred: {fid} already has an edge override, a person decides"]
    if len(list(recipes.glob(f"*__{fid}"))) <= len(picks):
        return [], [f"retraction deferred: it would orphan {fid}, a person decides"]
    return picks, []


def apply(fid: str, repo: str, picks: list[dict], root: Path, today: str, base_sha: str) -> list[str]:
    """Write the override, delete the recipes, return the repo-relative paths changed."""
    deletes, originals, sources, reasons = [], {}, [], []
    for p in picks:
        rel = str(p["path"].relative_to(root))
        s = p["signal"]
        deletes.append(rel)
        originals[rel] = p["path"].read_bytes().decode("utf-8")
        sources.append(s["url"])
        markers = ", ".join((s.get("extra") or {}).get("product_markers") or []) or "the env name"
        reasons.append(f"`board = {s['token']}` under env `{p['env']}` names the base of a product build "
                       f"({markers}), so it proves the chip and not {p['board']}.")
    how = picks[0]["signal"]["how"]
    record = {"firmware": fid, "repo": repo, "action": "edge_correction", "deletes": deletes,
              "classification": SELF_CORRECTION_CLASSES[how], "why": " ".join(reasons),
              "sources": list(dict.fromkeys(sources)), "historical_parent_sha": base_sha,
              "directed_by": SELF_CORRECTION_AUTHOR, "date": today, "originals": originals}
    override = root / "jr" / "overrides" / f"{fid}__edges.json"
    override.parent.mkdir(parents=True, exist_ok=True)
    override.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for p in picks:
        p["path"].unlink()
        p["path"].parent.rmdir()
    return [*deletes, str(override.relative_to(root))]


def valid_base(sha) -> bool:
    return isinstance(sha, str) and bool(_SHA.fullmatch(sha))
