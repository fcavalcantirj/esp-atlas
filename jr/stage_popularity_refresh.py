"""Refresh cited GitHub counts through the existing hourly Jr tick.

Each hour owns one deterministic catalog slice. A stable catalog of up to 168
distinct repositories gets a full pass in 24 hourly ticks, at most seven GitHub
repo calls per tick. Larger catalogs use more slices at the same call ceiling.
Failed calls are not retried in the same tick; their slice comes around again.
No request is made by a page view.
"""
from __future__ import annotations

import json
import math
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

import backfill_popularity
import pending_prs
import review_routing
from esp_atlas_core.floor import CURATED_EXEMPT, clears_popularity_floor

MAX_REPOS_PER_TICK = 7
MIN_REMAINING_CALLS = 10
MIN_REMAINING_SECONDS = 30
REFRESH_SECONDS = 24 * 60 * 60
# The catalog's Nyan URL currently identifies an unrelated Emacs repository.
# Keep it out of scheduled counts until the cited data correction lands.
QUARANTINED = {("nyan", "temporal/nyan-mode")}


def _observed_at(value) -> datetime | None:
    if isinstance(value, datetime):
        return value.replace(tzinfo=value.tzinfo or timezone.utc).astimezone(timezone.utc)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=timezone.utc)
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).astimezone(timezone.utc)


def _due(popularity, now: datetime) -> bool:
    observed = _observed_at(popularity.get("github_as_of")) if isinstance(popularity, dict) else None
    return observed is None or (now - observed).total_seconds() >= REFRESH_SECONDS


def _payload(raw: str, expected: str, old_id: int | None) -> dict | None:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("full_name"), str):
        return None
    if data["full_name"].lower() != expected.lower():
        return None
    stars, forks = data.get("stargazers_count"), data.get("forks_count")
    repo_id = backfill_popularity.stable_repo_id(data, {"github_repo_id": old_id} if old_id is not None else {})
    if repo_id is None:
        return None
    if any(type(v) is not int or v < 0 for v in (stars, forks)):
        return None
    return {"id": repo_id, "stars": stars, "forks": forks}


def _rewrite(original: str, stats: dict, now: datetime) -> str | None:
    try:
        fm, body = backfill_popularity._split(original)
    except (ValueError, yaml.YAMLError):
        return None
    if not isinstance(fm, dict) or not isinstance(fm.get("url"), str):
        return None
    if not isinstance(fm.get("popularity") or {}, dict):
        return None
    pop = dict(fm.get("popularity") or {})
    pop.update(stars=stats["stars"], forks=stats["forks"], github_repo_id=stats["id"],
               github_as_of=now.isoformat(timespec="seconds").replace("+00:00", "Z"))
    if "downloads" not in pop and "editorial_home" not in pop:
        pop["as_of"] = now.date().isoformat()
    fm["popularity"] = pop
    today = now.date().isoformat()
    fields = {"popularity.stars", "popularity.forks", "popularity.github_repo_id",
              "popularity.github_as_of"}
    sources = [s for s in fm.get("sources", []) if not (isinstance(s, dict) and s.get("field") in fields)]
    sources += [{"field": field, "url": fm["url"], "verified": today} for field in sorted(fields)]
    fm["sources"] = sources
    return backfill_popularity._render(fm, body)


def _atomic_write(path: Path, content: str) -> None:
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as tmp:
        tmp.write(content)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    try:
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _in_open_pr(pending, path: Path) -> bool:
    hold = pending.hold(path.parent.name)
    return hold is not None and hold.state == pending_prs.OPEN


def run(ctx):
    """Return a StageResult; `ctx.gh` is already charged by the tick Budget."""
    from tick import StageResult

    now = ctx.now.astimezone(timezone.utc)
    pending = pending_prs.of(ctx)
    grouped: dict[str, list[tuple[Path, dict, str]]] = {}
    for path in sorted((ctx.root / "data" / "firmware").glob("*/firmware.md")):
        original = path.read_text(encoding="utf-8")
        try:
            fm, _ = backfill_popularity._split(original)
        except (ValueError, yaml.YAMLError):
            continue
        owner_repo = backfill_popularity.repo_owner_and_name(fm.get("url")) if isinstance(fm, dict) else None
        if not owner_repo:
            continue
        repo = "/".join(owner_repo).lower()
        if (path.parent.name, repo) in QUARANTINED:
            continue
        grouped.setdefault(repo, []).append((path, fm, original))

    repos = sorted(grouped)
    slots = max(24, math.ceil(len(repos) / MAX_REPOS_PER_TICK))
    hour = int(now.timestamp() // 3600)
    selected = [repo for i, repo in enumerate(repos) if i % slots == hour % slots]
    result = StageResult("popularity_refresh")
    refreshed = unchanged = skipped = floor_deferred = review_deferred = pending_deferred = 0
    for repo in selected:
        if ctx.budget.remaining_calls() < MIN_REMAINING_CALLS or \
                ctx.budget.remaining_seconds() < MIN_REMAINING_SECONDS:
            skipped += len(grouped[repo])
            continue
        due = [(p, fm, original) for p, fm, original in grouped[repo]
               if _due(fm.get("popularity"), now)]
        # An OPEN Jr tick PR already changes this record (jr/pending_prs.py): a second edit of the
        # same firmware.md would conflict with it. The refresh waits for that PR; a veto does not
        # block it (the veto rejected a proposal, not the catalogued record's counts).
        held = [d for d in due if _in_open_pr(pending, d[0])]
        pending_deferred += len(held)
        due = [d for d in due if d not in held]
        if not due:
            unchanged += len(grouped[repo]) - len(held)
            continue
        response = ctx.gh("api", f"repos/{repo}")
        if getattr(response, "returncode", 1) != 0:
            skipped += len(due)
            # A missing repo must not starve later repos in this slice. A rate
            # or transport failure stops the slice; the next pass is our
            # backoff, with no immediate retries or fabricated zero counts.
            if "HTTP 404" in (getattr(response, "stderr", "") or ""):
                continue
            break
        for path, fm, original in due:
            old = fm.get("popularity") if isinstance(fm.get("popularity"), dict) else {}
            old_id = old.get("github_repo_id")
            stats = _payload(getattr(response, "stdout", ""), repo, old_id)
            if stats is None:
                skipped += 1
                continue
            if path.parent.name not in CURATED_EXEMPT and not clears_popularity_floor(
                    stats["stars"], stats["forks"], old.get("editorial_home"), old.get("downloads")):
                # A true count can move a record below the catalog's CI floor.
                # Preserve the published last-good record and surface the
                # decision for human data review instead of aborting the whole
                # tick's unrelated work in its guard.
                floor_deferred += 1
                continue
            rewritten = _rewrite(original, stats, now)
            if rewritten is None:
                skipped += 1
                continue
            if rewritten == original:
                unchanged += 1
                continue
            relative = str(path.relative_to(ctx.root))
            route = review_routing.classify([review_routing.Change(relative, "M", original, rewritten)])
            if route.review:
                # A legacy record with unusual provenance must not sneak a
                # new jr-review PR past the cap via this AUTO-only stage.
                review_deferred += 1
                continue
            if ctx.dry_run:
                result.would_write.append({"path": relative, "field": "popularity",
                                           "value": {"stars": stats["stars"], "forks": stats["forks"]}})
            else:
                _atomic_write(path, rewritten)
                result.paths.append(relative)
            refreshed += 1
    result.summary = (f"GitHub popularity: {refreshed} {'would refresh' if ctx.dry_run else 'refreshed'}, "
                      f"{unchanged} current, {skipped} skipped, {floor_deferred} below-floor deferred, "
                      f"{review_deferred} provenance deferred"
                      + (f", {pending_deferred} pending deferred" if pending_deferred else "") + "; "
                      f"{len(selected)} repos in slot")
    return result


run.produces_review = False
