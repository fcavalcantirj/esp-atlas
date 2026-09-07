"""EspAtlas Jr — Track B stage: map every cited board of a firmware as a recipe (jr/stage_boardmap.py).

Phase 4 (PLAN §4 "G1 backfill runs as Track B units, most under-mapped first"). One unit = one
firmware: read what its repo declares (jr/derive), resolve each signal to a catalogued board
(jr/board_alias, against the tree being written), write the missing recipes with their
citations (jr/writers), widen the firmware's `socs` to the cited union — one `field: socs`
source per page that proves an added chip — and persist the raw signals next to the record as
`data/firmware/<id>/signals.json` so the G1 audit can run offline in CI.

Selection is deterministic: a measured under-map first (persisted signals whose declared
boards still lack recipes), then fewest recipes, then oldest signals, then id; a firmware whose
signals.json is younger than `fresh_days` is skipped (its repo was read recently). A
signals.json with errors > 0 and no signals (a failed or degraded read) counts as unmeasured.
`budget` firmware per run.

Budget: every GitHub API call goes through the tick's wrapped `gh` and every raw fetch through
a wrapped `raw`, so each call is charged exactly once, as it happens. The stage stops BEFORE a
firmware it cannot afford; if the budget runs out mid-derivation (reads only — nothing is
written until derive returns) that firmware is skipped and what earlier firmware wrote is kept.

Honesty about reads: derive() reports the endpoints it could not reach. A read that hit
unavailable endpoints and saw nothing is not persisted (the firmware stays unmeasured and is
retried next run); a read that hit unavailable endpoints and came back narrower than the
persisted signals keeps the previous file. One firmware's failure never kills the stage: it is
counted, reported, and the tick's PR is flagged needs_human.

Everything is additive: recipes are only created, `socs` only widened, signals.json replaced.
A dry run reads the network (charged) but writes nothing. Until the Phase 6 cutover this stage
is driven by hand — `python3 jr/tick.py --track B --budget 3` — and its PRs are human-merged.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import board_alias
import derive
import tools
import writers
from budget import BudgetExceeded

DEFAULT_BUDGET = 3
FRESH_DAYS = 7
CALLS_PER_FIRMWARE = 35          # derive's max_calls (30) + headroom; the tick budget must afford it
SECONDS_PER_FIRMWARE = 60.0      # a derivation's worst case; the tick budget must afford it

_GH = re.compile(r"^https?://github\.com/([^/\s]+)/([^/\s#?]+)")


def owner_repo_of(url: str) -> str | None:
    m = _GH.match((url or "").strip())
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2).removesuffix('.git')}"


def _load_json(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def _measured_signals(path: Path) -> dict | None:
    """Persisted signals, or None when absent or unreadable. A file with errors > 0 and no
    signals (a failed or degraded read) counts as unmeasured."""
    doc = _load_json(path)
    if doc and int(doc.get("errors") or 0) > 0 and not doc.get("signals"):
        return None
    return doc


def _doc_age(doc: dict | None, now: datetime) -> float | None:
    if not doc:
        return None
    try:
        dt = datetime.strptime(doc.get("fetched"), "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None
    return (now - dt).total_seconds() / 86400


def _age_days(signals_json: Path, now: datetime) -> float | None:
    return _doc_age(_measured_signals(signals_json), now)


def select_firmware(root: Path, budget: int, now: datetime, fresh_days: int = FRESH_DAYS) -> list[str]:
    """Most under-mapped first: (-missing, recipe count, -signals age, id), where missing is
    the persisted resolved boards that still lack a recipe. Skips GitHub-less records and
    records whose signals were fetched < fresh_days ago."""
    cands = []
    for fmd in sorted((root / "data" / "firmware").glob("*/firmware.md")):
        fm = tools._frontmatter(fmd)
        fid = fm.get("id") or fmd.parent.name
        if not owner_repo_of(fm.get("url", "")):
            continue
        doc = _measured_signals(fmd.parent / "signals.json")
        age = _doc_age(doc, now)
        if age is not None and age < fresh_days:
            continue
        n_recipes = len(list((root / "data" / "recipes").glob(f"*__{fid}")))
        boards = ((doc or {}).get("resolved") or {}).get("boards") or []
        missing = sum(1 for b in boards
                      if not (root / "data" / "recipes" / f"{b}__{fid}" / "recipe.md").exists())
        cands.append((-missing, n_recipes, -(age if age is not None else 10**6), fid))
    cands.sort()
    return [fid for _, _, _, fid in cands[:budget]]


def _soc_proof_urls(soc: str, res: dict, refused: set[str], board_soc) -> list[str]:
    """The pages that prove `soc`: the best signal of every accepted board with that chip, plus
    the best chip-only signal for it. Distinct, in rank order."""
    urls = []
    for b, sigs in res["boards"].items():
        if b not in refused and board_soc(b) == soc:
            urls.append(writers.evidence_url(writers._best(sigs)))
    if res["socs"].get(soc):
        urls.append(writers.evidence_url(writers._best(res["socs"][soc])))
    return list(dict.fromkeys(u for u in urls if u))


def map_one(fid: str, *, root: Path, api, raw, today: str, dry_run: bool = False,
            max_calls: int = 30) -> dict:
    """Derive → resolve (against `root`'s boards) → write recipes → widen socs → persist signals
    for one firmware. Returns {"paths": [...], "written": [...], "existing": [...], "refused": [...],
    "socs_added": [...], "signals": n, "unresolved": n, "calls": n, "errors": n, "notes": [...]}
    plus "failed": True when the read hit unavailable endpoints and saw nothing (nothing persisted)."""
    fmd = root / "data" / "firmware" / fid / "firmware.md"
    fm = tools._frontmatter(fmd)
    owner_repo = owner_repo_of(fm.get("url", ""))
    board_soc = lambda b: tools.board_soc(b, repo=root)  # noqa: E731
    d = derive.derive(owner_repo, api=api, raw=raw, max_calls=max_calls, today=today)
    res = derive.resolve(d, boards=board_alias.atlas_boards(root))
    out = {"paths": [], "written": [], "existing": [], "refused": [], "socs_added": [],
           "signals": len(d["signals"]), "unresolved": len(res["unresolved"]), "calls": d["calls"],
           "errors": int(d.get("errors") or 0), "notes": list(d["notes"])}
    if out["errors"] and not d["signals"]:
        out["failed"] = True
        out["notes"].append(f"read failed ({out['errors']} unavailable endpoint(s)), nothing persisted")
        return out
    if dry_run:
        out["would_write"] = [f"{b}__{fid}" for b in res["boards"]
                              if not (root / "data" / "recipes" / f"{b}__{fid}" / "recipe.md").exists()]
        return out
    w = writers.write_recipes(fid, fm.get("url", ""), res, root=root, today=today, board_soc=board_soc)
    out.update(written=w["written"], existing=w["existing"], refused=w["refused"])
    out["paths"] += w["paths"]
    # socs: widen to the cited union, one source per page that proves an added chip
    before = set(fm.get("socs") or [])
    new_socs = sorted(set(w["socs"]) - before)
    if new_socs:
        refused = {b for b, _ in w["refused"]}
        urls: list[str] = []
        for soc in new_socs:
            urls += _soc_proof_urls(soc, res, refused, board_soc)
        urls = list(dict.fromkeys(urls))
        if not urls:
            out["notes"].append(f"socs not widened (+{','.join(new_socs)}): no citable signal")
        else:
            try:
                if writers.merge_socs(fmd, new_socs, urls, today):
                    out["socs_added"] = new_socs
                    out["paths"].append(str(fmd.relative_to(root)))
            except ValueError as e:
                out["notes"].append(f"socs not widened: {str(e)[:160]}")
    # signals.json: the evidence the G1 audit reads offline
    sig_path = fmd.parent / "signals.json"
    old = _load_json(sig_path)
    old_boards = set(((old or {}).get("resolved") or {}).get("boards") or [])
    new_boards = set(res["boards"])
    if out["errors"] and old and not new_boards >= old_boards:
        out["notes"].append(f"degraded read ({out['errors']} unavailable endpoint(s), "
                            f"{len(old_boards)} -> {len(new_boards)} boards): previous signals kept")
    else:
        payload = {**d, "resolved": {"boards": sorted(new_boards), "socs": sorted(res["socs"]),
                                     "unresolved": sorted({s["token"] for s in res["unresolved"]})}}
        sig_path.write_text(json.dumps(payload, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        out["paths"].append(str(sig_path.relative_to(root)))
    return out


def run(ctx, budget: int = DEFAULT_BUDGET, api=None, raw=None, fresh_days: int = FRESH_DAYS,
        only: list[str] | None = None):
    """The Track B stage for jr/tick.py: returns a tick.StageResult. `only` (the CLI's
    --firmware) names the firmware to map, in order, ignoring the selector and its freshness
    skip — the manual lane's way to point at a known under-mapped repo."""
    import tick
    now = ctx.now
    today = now.strftime("%Y-%m-%d")
    api = api or (lambda path: json.loads(ctx.gh("api", path).stdout))    # ctx.gh is budget-wrapped
    raw = ctx.budget.wrap(raw or derive.default_raw, "raw")
    paths, lines, admitted, rejects, needs_human = [], [], 0, {}, False
    if only:
        chosen = []
        for fid in only:
            fmd = ctx.root / "data" / "firmware" / fid / "firmware.md"
            if not fmd.exists() or not owner_repo_of(tools._frontmatter(fmd).get("url", "")):
                lines.append(f"{fid}: not a catalogued firmware with a GitHub url, skipped")
                continue
            chosen.append(fid)
    else:
        chosen = select_firmware(ctx.root, budget, now, fresh_days)

    def reject(key):
        rejects[key] = rejects.get(key, 0) + 1

    for fid in chosen:
        if ctx.budget.remaining_calls() < CALLS_PER_FIRMWARE or ctx.budget.remaining_seconds() < SECONDS_PER_FIRMWARE:
            lines.append(f"stopped before {fid}: tick budget low ({ctx.budget.remaining_calls()} calls, "
                         f"{ctx.budget.remaining_seconds():.0f}s left)")
            break
        try:
            r = map_one(fid, root=ctx.root, api=api, raw=raw, today=today, dry_run=ctx.dry_run)
        except BudgetExceeded as e:
            lines.append(f"stopped during {fid}: {e}")          # derive is read-only: nothing half-written
            break
        except Exception as e:  # noqa: BLE001 — one firmware must not kill the stage or the tick
            reject("error")
            needs_human = True
            lines.append(f"{fid}: failed {type(e).__name__}: {str(e)[:120]}")
            continue
        if r.get("failed"):
            reject("unreadable")
            lines.append(f"{fid}: {r['notes'][-1]}")
            continue
        paths += r["paths"]
        admitted += len(r["written"])
        for _, why in r["refused"]:
            reject("chip_clash" if "disagrees" in why else "no_soc")
        extra = "".join(f"; {n}" for n in r["notes"] if n.startswith(("socs not widened", "degraded read")))
        if ctx.dry_run:
            lines.append(f"{fid}: {r['signals']} signals, would write {len(r.get('would_write', []))} recipe(s), "
                         f"{r['unresolved']} unresolved{extra}")
        else:
            lines.append(f"{fid}: +{len(r['written'])} recipe(s), {len(r['existing'])} existing, "
                         f"{r['signals']} signals, {r['unresolved']} unresolved"
                         + (f", socs +{','.join(r['socs_added'])}" if r["socs_added"] else "") + extra)
    summary = "; ".join(lines) if lines else "no firmware selected"
    return tick.StageResult("boardmap", paths=paths, summary=summary, admitted=admitted, rejects=rejects,
                            needs_human=needs_human)
