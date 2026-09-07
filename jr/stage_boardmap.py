"""EspAtlas Jr — Track B stage: map every cited board of a firmware as a recipe (jr/stage_boardmap.py).

Phase 4 (PLAN §4 "G1 backfill runs as Track B units, most under-mapped first"). One unit = one
firmware: read what its repo declares (jr/derive), resolve each signal to a catalogued board
(jr/board_alias), write the missing recipes with their citations (jr/writers), widen the
firmware's `socs` to the cited union, and persist the raw signals next to the record as
`data/firmware/<id>/signals.json` so the G1 audit can run offline in CI.

Selection is deterministic: firmware with the FEWEST recipes first, then oldest signals, then
id; a firmware whose signals.json is younger than `fresh_days` is skipped (its repo was read
recently). `budget` firmware per run. The stage stops early when the tick's GitHub-call budget
cannot afford another derivation.

Everything is additive: recipes are only created, `socs` only widened, signals.json replaced.
A dry run computes and reports but writes nothing. Until the Phase 6 cutover this stage is
driven by hand — `python3 jr/tick.py --track B --budget 3` — and its PRs are human-merged.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import derive
import tools
import writers

DEFAULT_BUDGET = 3
FRESH_DAYS = 7
CALLS_PER_FIRMWARE = 35          # derive's max_calls (30) + headroom; the tick budget must afford it

_GH = re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s#?]+)")


def owner_repo_of(url: str) -> str | None:
    m = _GH.match((url or "").strip())
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2).removesuffix('.git')}"


def _age_days(signals_json: Path, now: datetime) -> float | None:
    if not signals_json.exists():
        return None
    try:
        fetched = json.loads(signals_json.read_text(encoding="utf-8")).get("fetched")
        dt = datetime.strptime(fetched, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None
    return (now - dt).total_seconds() / 86400


def select_firmware(root: Path, budget: int, now: datetime, fresh_days: int = FRESH_DAYS) -> list[str]:
    """Most under-mapped first: (recipe count, -signals age, id). Skips GitHub-less records and
    records whose signals were fetched < fresh_days ago."""
    cands = []
    for fmd in sorted((root / "data" / "firmware").glob("*/firmware.md")):
        fm = tools._frontmatter(fmd)
        fid = fm.get("id") or fmd.parent.name
        if not owner_repo_of(fm.get("url", "")):
            continue
        age = _age_days(fmd.parent / "signals.json", now)
        if age is not None and age < fresh_days:
            continue
        n_recipes = len(list((root / "data" / "recipes").glob(f"*__{fid}")))
        cands.append((n_recipes, -(age if age is not None else 10**6), fid))
    cands.sort()
    return [fid for _, _, fid in cands[:budget]]


def map_one(fid: str, *, root: Path, api, raw, today: str, dry_run: bool = False,
            max_calls: int = 30) -> dict:
    """Derive → resolve → write recipes → widen socs → persist signals for one firmware.
    Returns {"paths": [...], "written": [...], "existing": [...], "refused": [...],
             "socs_added": [...], "signals": n, "unresolved": n, "calls": n, "notes": [...]}."""
    fmd = root / "data" / "firmware" / fid / "firmware.md"
    fm = tools._frontmatter(fmd)
    owner_repo = owner_repo_of(fm.get("url", ""))
    d = derive.derive(owner_repo, api=api, raw=raw, max_calls=max_calls, today=today)
    res = derive.resolve(d)
    out = {"paths": [], "written": [], "existing": [], "refused": [], "socs_added": [],
           "signals": len(d["signals"]), "unresolved": len(res["unresolved"]), "calls": d["calls"], "notes": list(d["notes"])}
    if dry_run:
        out["would_write"] = [f"{b}__{fid}" for b in res["boards"]
                              if not (root / "data" / "recipes" / f"{b}__{fid}" / "recipe.md").exists()]
        return out
    w = writers.write_recipes(fid, fm.get("url", ""), res, root=root, today=today)
    out.update(written=w["written"], existing=w["existing"], refused=w["refused"])
    out["paths"] += w["paths"]
    before = set(fm.get("socs") or [])
    cite = next((s["url"] for s in sorted(d["signals"], key=lambda s: s["rank"])), fm.get("url", ""))
    if w["socs"] and set(w["socs"]) - before:
        if writers.merge_socs(fmd, w["socs"], cite, today):
            out["socs_added"] = sorted(set(w["socs"]) - before)
            out["paths"].append(str(fmd.relative_to(root)))
    sig_path = fmd.parent / "signals.json"
    payload = {**d, "resolved": {"boards": sorted(res["boards"]), "socs": sorted(res["socs"]),
                                 "unresolved": sorted({s["token"] for s in res["unresolved"]})}}
    sig_path.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    out["paths"].append(str(sig_path.relative_to(root)))
    return out


def run(ctx, budget: int = DEFAULT_BUDGET, api=None, raw=None, fresh_days: int = FRESH_DAYS):
    """The Track B stage for jr/tick.py: returns a tick.StageResult."""
    import tick
    now = ctx.now
    today = now.strftime("%Y-%m-%d")
    api = api or (lambda path: json.loads(ctx.gh("api", path).stdout))
    raw = raw or derive.default_raw
    chosen = select_firmware(ctx.root, budget, now, fresh_days)
    paths, lines, admitted, rejects = [], [], 0, {}
    for fid in chosen:
        if ctx.budget.remaining_calls() < CALLS_PER_FIRMWARE:
            lines.append(f"stopped before {fid}: tick budget low ({ctx.budget.remaining_calls()} calls left)")
            break
        r = map_one(fid, root=ctx.root, api=api, raw=raw, today=today, dry_run=ctx.dry_run)
        if not ctx.dry_run:
            ctx.budget.charge(r["calls"], f"derive {fid}")
        paths += r["paths"]
        admitted += len(r["written"])
        for _, why in r["refused"]:
            key = "chip_clash" if "disagrees" in why else "no_soc"
            rejects[key] = rejects.get(key, 0) + 1
        if ctx.dry_run:
            lines.append(f"{fid}: {r['signals']} signals, would write {len(r.get('would_write', []))} recipe(s), {r['unresolved']} unresolved")
        else:
            lines.append(f"{fid}: +{len(r['written'])} recipe(s), {len(r['existing'])} existing, "
                         f"{r['signals']} signals, {r['unresolved']} unresolved"
                         + (f", socs +{','.join(r['socs_added'])}" if r["socs_added"] else ""))
    summary = "; ".join(lines) if lines else "no firmware selected"
    return tick.StageResult("boardmap", paths=paths, summary=summary, admitted=admitted, rejects=rejects)
