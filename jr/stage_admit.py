"""EspAtlas Jr — Track A stage: admit new firmware from the launcher catalog (jr/stage_admit.py).

Phase 3: the deterministic admission gate over tools.fetch_launcher_catalog() scored by
jr/scorer.score_entry — no LLM anywhere. One run admits up to `budget` firmware records;
every skip is recorded in memory with a TTL so the next run does not re-fetch it.

NOT registered in tick.STAGES until the Phase 6 cutover: driven by hand
(`python3 jr/tick.py --track A --budget N`), like Track B was. Dry-run scores and reports,
writes nothing (memory untouched).

A lone real --track A run admits bare firmware.md files, which scripts/validate.py rejects
as orphans (no recipe references them) — the tick's guard then discards the worktree. That
is the guard working as designed: admissions land composed with the boardmap stage at
cutover, which writes the recipes in the same tick.
"""
from __future__ import annotations

import json
from pathlib import Path

import memory
import scorer
import tools
import writers
from budget import BudgetExceeded
from esp_atlas_core.floor import clears_popularity_floor

DEFAULT_BUDGET = 3
MIN_CALLS_TO_CONTINUE = 5   # a repo-meta fetch costs >= 1 call; stop before stranding one

# Skip reason -> memory TTL (days). The floor/archived/unresolved gates have their own
# constants in jr/memory.py; every other skip is a "scored but skipped" note re-checked
# after SEEN_TTL_DAYS.
REJECT_TTLS = {
    "repo_unresolved": memory.UNRESOLVED_REJECT_DAYS,
    "archived": memory.ARCHIVED_REJECT_DAYS,
    "below_floor": memory.FLOOR_REJECT_DAYS,
}


def _meta_from_api(doc: dict) -> dict:
    """Map a `gh api repos/<owner>/<repo>` payload onto tools.fetch_github_repo's dict shape
    (the shape jr/scorer.score_entry reads). Same keys, same meanings."""
    source, parent = doc.get("source") or {}, doc.get("parent") or {}
    lic = doc.get("license") or {}
    return {
        "full_name": doc.get("full_name"), "description": doc.get("description"),
        "license": lic.get("spdx_id"), "topics": doc.get("topics", []),
        "homepage": doc.get("homepage"), "default_branch": doc.get("default_branch"),
        "stars": doc.get("stargazers_count"), "archived": doc.get("archived"),
        "forks": doc.get("forks_count"),
        "id": doc.get("id"), "fork": doc.get("fork"),
        "source_full_name": source.get("full_name"),
        "source_stars": source.get("stargazers_count"),
        "parent_full_name": parent.get("full_name"),
        "pushed_at": doc.get("pushed_at"), "language": doc.get("language"),
    }


def _fetch_meta(gh, owner_repo: str):
    """One charged `gh api repos/<owner>/<repo>`; (meta, fetched). Unparseable owner/repo or
    any gh failure maps to {"error": ...} without raising, so the scorer's repo_unresolved
    path (7-day TTL) covers renames, outages and 404s alike."""
    parts = (owner_repo or "").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return {"error": f"unparseable repo {owner_repo!r}"}, False
    try:
        p = gh("api", f"repos/{parts[0]}/{parts[1]}")
    except BudgetExceeded:
        raise
    except Exception as e:  # noqa: BLE001 — transient failure reads as unresolved, retried in 7 d
        return {"error": f"{type(e).__name__}: {str(e)[:120]}"}, False
    if getattr(p, "returncode", 1) != 0:
        return {"error": (getattr(p, "stderr", "") or "").strip()[:200]}, False
    try:
        return _meta_from_api(json.loads(p.stdout or "{}")), True
    except (json.JSONDecodeError, TypeError, AttributeError) as e:
        return {"error": f"unparseable api response: {e}"}, False


def _catalogued_ids(led: dict, now) -> dict:
    """{repo_id: firmware_id} over every memory record that has not expired — the rename-proof
    identity net behind the scorer's duplicate_of rule (a repo the catalog knows under an old
    path is still caught after a rename)."""
    out = {}
    for rid, fid in (led.get("by_repo_id") or {}).items():
        rec = (led.get("by_id") or {}).get(fid)
        if rec is not None and not memory.is_expired(rec, now):
            out[str(rid)] = fid
    return out


def run(ctx, budget: int = DEFAULT_BUDGET):
    """The Track A stage for jr/tick.py: returns a tick.StageResult."""
    import tick
    today = ctx.now.strftime("%Y-%m-%d")
    fetch_catalog = ctx.budget.wrap(tools.fetch_launcher_catalog, "https")
    try:
        catalog = fetch_catalog()
    except BudgetExceeded as e:
        return tick.StageResult("admit", paths=[], summary=f"stopped: {e}", admitted=0,
                                rejects={})
    except Exception as e:  # noqa: BLE001 — a blind stage flags a human, writes nothing
        return tick.StageResult("admit", paths=[], summary=f"catalog unreadable: {type(e).__name__}: {str(e)[:120]}",
                                admitted=0, rejects={}, needs_human=True)
    if not isinstance(catalog, list):
        return tick.StageResult("admit", paths=[], summary="catalog unreadable: not a list",
                                admitted=0, rejects={}, needs_human=True)

    led = memory.load(ctx.ledger_path)   # read-only here; writes below honor dry-run
    cat_repos, cat_toks = tools._catalogued_repos_and_tokens(ctx.root / "data" / "firmware")
    cat_ids = _catalogued_ids(led, ctx.now)
    paths, lines, admitted, rejects, needs_human = [], [], 0, {}, False
    would_admit, decided = 0, 0

    def reject(key):
        rejects[key] = rejects.get(key, 0) + 1

    def skip_reject(fid, owner_repo, reason, repo_id):
        key = reason.split(":")[0]
        reject(key)
        if not ctx.dry_run:
            memory.record_rejected(fid, owner_repo, reason,
                                   ttl_days=REJECT_TTLS.get(key, memory.SEEN_TTL_DAYS),
                                   repo_id=repo_id, path=ctx.ledger_path, now=ctx.now)
        return f"{fid}: skip {key}"

    for entry in sorted(catalog, key=lambda e: ((e.get("name") or ""), (e.get("github") or ""))):
        if admitted + would_admit >= budget:
            lines.append(f"stopped: budget reached ({admitted + would_admit} admitted)")
            break
        github = (entry.get("github") or "").strip()
        owner_repo = scorer._owner_repo(github)
        if memory.is_blocked(led, repo=owner_repo, now=ctx.now) or memory.is_seen(led, repo=owner_repo, now=ctx.now):
            decided += 1
            continue
        if ctx.budget.remaining_calls() < MIN_CALLS_TO_CONTINUE:
            lines.append(f"stopped before {owner_repo}: tick budget low "
                         f"({ctx.budget.remaining_calls()} calls left)")
            break
        try:
            meta, _fetched = _fetch_meta(ctx.gh, owner_repo)
        except BudgetExceeded as e:
            lines.append(f"stopped during {owner_repo}: {e}")   # meta fetch is read-only: nothing half-written
            break
        repo_id = meta.get("id")
        if repo_id is not None and (memory.is_blocked(led, repo_id=repo_id, now=ctx.now)
                                    or memory.is_seen(led, repo_id=repo_id, now=ctx.now)):
            decided += 1
            continue
        fid = scorer._slug(scorer._repo_name_from_url(github))
        # Popularity floor (SPEC-firmware-floor.md, via esp_atlas_core.floor — never re-typed):
        # below stars AND forks is filler, rejected for FLOOR_REJECT_DAYS.
        if not clears_popularity_floor(meta.get("stars"), meta.get("forks")):
            lines.append(skip_reject(fid, owner_repo,
                                     f"below_floor: {meta.get('stars')} stars / {meta.get('forks')} forks",
                                     repo_id))
            continue
        res = scorer.score_entry(entry, meta, cat_repos, cat_toks, cat_ids)
        if res["decision"] == "skip":
            lines.append(skip_reject(fid, owner_repo, res["reason"], repo_id))
            continue
        rec = res["record"]
        out_id = rec["id"]
        # Worktree check: the scorer derives the chip from this clone's boards; the tick writes
        # into a worktree. Refuse to write when the worktree disagrees (same bug class as the
        # Track B resolver reading the wrong tree).
        if tools.board_soc(rec["board"], repo=ctx.root) != rec["chip"]:
            lines.append(skip_reject(out_id, owner_repo,
                                     f"chip_family_mismatch: worktree disagrees on board '{rec['board']}'",
                                     repo_id))
            continue
        fmd = ctx.root / "data" / "firmware" / out_id / "firmware.md"
        if fmd.exists():
            lines.append(f"{out_id}: record exists, nothing written")
            continue
        if res.get("needs_human"):
            needs_human = True
        if ctx.dry_run:
            lines.append(f"{out_id}: would admit{' (needs_human)' if res.get('needs_human') else ''}")
            would_admit += 1
            continue
        repo_url = rec["url"]
        text = writers.render_firmware(rec, [{"field": "*", "url": repo_url},
                                             {"field": "popularity", "url": repo_url}],
                                       today, needs_human=bool(res.get("needs_human")))
        fmd.parent.mkdir(parents=True, exist_ok=True)
        fmd.write_text(text, encoding="utf-8")
        paths.append(str(fmd.relative_to(ctx.root)))
        memory.record_proposed(out_id, owner_repo, repo_id=repo_id, evidence_url=repo_url,
                               path=ctx.ledger_path, now=ctx.now)
        admitted += 1
        lines.append(f"{out_id}: +record{' (needs_human)' if res.get('needs_human') else ''}")
    summary = "; ".join(lines) if lines else "no candidates"
    if decided and lines:
        summary += f" ({decided} already decided, skipped)"
    elif decided:
        summary = f"{decided} already decided, skipped"
    return tick.StageResult("admit", paths=paths, summary=summary, admitted=admitted,
                            rejects=rejects, needs_human=needs_human)
