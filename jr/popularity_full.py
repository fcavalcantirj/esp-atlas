"""Deterministic, bounded full-catalog GitHub popularity pass.

This runs separately from Jr's growth tick. One GraphQL query carries at most
25 repository aliases; every canonical, non-quarantined repository is either
queried once or explicitly recorded as unattempted. No LLM or same-run retry.

A record an OPEN Jr tick PR already changes (jr/pending_prs.py, the index the runner
passes on ctx) is deferred_open_tick_pr: never queried, never rewritten, and the attempt
is not complete while one is deferred. A veto is no edit hold for a catalogued record's
counts (the same rule as stage_popularity_refresh).
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import yaml

import backfill_popularity
import pending_prs
import review_routing
import stage_popularity_refresh as legacy
from esp_atlas_core.floor import CURATED_EXEMPT, clears_popularity_floor

BATCH_SIZE = 25
MIN_GRAPHQL_POINTS = 50  # leave headroom for other consumers of Jr's token
MIN_REMAINING_SECONDS = 20
RECEIPT_DIR = Path("docs/telemetry/popularity")
DEFERRED_OPEN = "deferred_open_tick_pr"


def _next_batch_cost_bound(repos: list[str]) -> int:
    """Scalar-only repository lookup has no connections; GitHub's minimum is 1 point.

    Keep this explicit so the admission check reserves points *after* the next
    query, not merely before it. If fields/connections change, revise the
    bound and its boundary tests before raising the query's cost ceiling.
    """
    return 1 if repos else 0


def _age_seconds(value, now: datetime) -> int | None:
    observed = legacy._observed_at(value)
    return int((now - observed).total_seconds()) if observed else None


def _query(repos: list[str]) -> str:
    aliases = []
    for index, repo in enumerate(repos):
        owner, name = repo.split("/", 1)
        aliases.append(
            f'r{index}:repository(owner:{json.dumps(owner)},name:{json.dumps(name)})'
            '{nameWithOwner databaseId fullDatabaseId stargazerCount forkCount}'
        )
    return "query { rateLimit { cost remaining resetAt } " + " ".join(aliases) + " }"


def _call(ctx, query: str) -> tuple[dict | None, dict[str, str], int | None]:
    response = ctx.gh("api", "graphql", "-i", "-f", f"query={query}")
    raw = getattr(response, "stdout", "") or ""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    stderr = getattr(response, "stderr", "") or ""
    if isinstance(stderr, bytes):
        stderr = stderr.decode("utf-8", "replace")
    headers: dict[str, str] = {}
    status = None
    if raw.startswith("HTTP/"):
        head, separator, body = raw.partition("\n\n")
        if not separator:
            head, separator, body = raw.partition("\r\n\r\n")
        match = re.match(r"HTTP/\S+\s+(\d{3})", head)
        status = int(match.group(1)) if match else None
        for line in head.splitlines()[1:]:
            if ":" in line:
                key, value = line.split(":", 1)
                headers[key.casefold().strip()] = value.strip()
        raw = body if separator else ""
    if status is None:
        match = re.search(r"HTTP\s+(403|429)", stderr)
        status = int(match.group(1)) if match else None
    try:
        doc = json.loads(raw)
    except (TypeError, ValueError):
        return None, headers, status
    if not isinstance(doc, dict):
        return None, headers, status
    if getattr(response, "returncode", 1) == 124:
        return None, headers, status
    # gh exits nonzero for GraphQL errors even when HTTP is 200 and the JSON
    # contains valid sibling aliases. Preserve that envelope so per-alias
    # successes and an HTTP-200 RATE_LIMITED error are both handled. A transport
    # failure or non-200 HTTP response cannot publish data.
    if getattr(response, "returncode", 1) != 0 and status != 200:
        return None, headers, status
    if status is not None and status != 200:
        return None, headers, status
    return doc, headers, status


def _cooldown_until(now: datetime, headers: dict[str, str], quota: dict | None = None) -> datetime:
    """Honor valid longer GitHub delays; malformed replies get a one-hour floor."""
    until = now + timedelta(hours=1)
    retry = headers.get("retry-after")
    if retry:
        try:
            seconds = float(retry)
            if math.isfinite(seconds) and 0 < seconds <= 86400:
                until = max(until, now + timedelta(seconds=seconds))
        except ValueError:
            try:
                target = parsedate_to_datetime(retry)
                if target.tzinfo and now < target <= now + timedelta(days=1):
                    until = max(until, target.astimezone(timezone.utc))
            except (TypeError, ValueError, OverflowError):
                pass
    reset = headers.get("x-ratelimit-reset")
    if reset:
        try:
            seconds = float(reset)
            if math.isfinite(seconds) and now.timestamp() < seconds <= now.timestamp() + 86400:
                until = max(until, datetime.fromtimestamp(seconds, timezone.utc))
        except (ValueError, OverflowError):
            pass
    if isinstance(quota, dict):
        parsed = legacy._observed_at(quota.get("resetAt"))
        if parsed and now < parsed <= now + timedelta(days=1):
            until = max(until, parsed)
    return until


def _limited(doc: dict | None, status: int | None) -> bool:
    errors = (doc.get("errors") or []) if isinstance(doc, dict) else []
    return status in (403, 429) or any(
        isinstance(error, dict) and (error.get("type") == "RATE_LIMITED" or
                                     "rate limit" in str(error.get("message", "")).casefold())
        for error in errors
    )


def _quota(doc: dict | None, headers: dict[str, str]) -> dict | None:
    data = doc.get("data") if isinstance(doc, dict) else None
    quota = data.get("rateLimit") if isinstance(data, dict) else None
    quota = dict(quota) if isinstance(quota, dict) else {}
    raw_remaining = headers.get("x-ratelimit-remaining")
    if raw_remaining and raw_remaining.isdecimal():
        remaining = int(raw_remaining)
        if type(quota.get("remaining")) is int:
            quota["remaining"] = min(quota["remaining"], remaining)
        else:
            quota["remaining"] = remaining
    raw_reset = headers.get("x-ratelimit-reset")
    if "resetAt" not in quota and raw_reset and raw_reset.isdecimal():
        try:
            quota["resetAt"] = datetime.fromtimestamp(int(raw_reset), timezone.utc).isoformat()
        except (ValueError, OverflowError):
            pass
    return quota or None


def _charge_cost(result, quota: dict | None) -> None:
    cost = quota.get("cost") if isinstance(quota, dict) else None
    if type(cost) is int and cost >= 0:
        result.graphql_cost_spent += cost
    else:
        result.graphql_cost_unknown_requests += 1


def _repo_id(node: dict) -> int | None:
    full = node.get("fullDatabaseId")
    if isinstance(full, str) and full.isdecimal():
        value = int(full)
        short = node.get("databaseId")
        if short is not None and (type(short) is not int or short != value):
            return None
    else:
        value = node.get("databaseId")
    return value if type(value) is int and value > 0 else None


def _stats(node, repo: str, old_id: object) -> dict | None:
    if not isinstance(node, dict) or not isinstance(node.get("nameWithOwner"), str):
        return None
    if node["nameWithOwner"].casefold() != repo.casefold():
        return None
    repo_id = _repo_id(node)
    if old_id is not None and (type(old_id) is not int or old_id <= 0):
        return None
    if repo_id is None or (old_id is not None and repo_id != old_id):
        return None
    stars, forks = node.get("stargazerCount"), node.get("forkCount")
    if any(type(n) is not int or n < 0 for n in (stars, forks)):
        return None
    return {"id": repo_id, "stars": stars, "forks": forks}


def _inventory(ctx, now: datetime):
    pending = pending_prs.of(ctx)
    grouped: dict[str, list[tuple[Path, dict, str]]] = {}
    outcomes: dict[str, dict] = {}
    for path in sorted((ctx.root / "data" / "firmware").glob("*/firmware.md")):
        fid = path.parent.name
        original = path.read_text(encoding="utf-8")
        try:
            fm, _ = backfill_popularity._split(original)
        except (ValueError, yaml.YAMLError):
            outcomes[fid] = {"firmware_id": fid, "repository": None,
                             "outcome": "excluded_invalid_record", "attempted": False,
                             "age_before_seconds": None}
            continue
        pair = backfill_popularity.repo_owner_and_name(fm.get("url")) if isinstance(fm, dict) else None
        repo = "/".join(pair).lower() if pair else None
        pop = fm.get("popularity") if isinstance(fm, dict) else None
        outcomes[fid] = {"firmware_id": fid, "repository": repo, "outcome": "unattempted",
                         "attempted": False,
                         "age_before_seconds": _age_seconds((pop or {}).get("github_as_of"), now)
                         if isinstance(pop, dict) else None}
        if repo is None:
            outcomes[fid]["outcome"] = "excluded_invalid_url"
        elif (fid, repo) in legacy.QUARANTINED:
            outcomes[fid]["outcome"] = "excluded_wrong_source"
        elif legacy._in_open_pr(pending, path):
            outcomes[fid]["outcome"] = DEFERRED_OPEN
        else:
            grouped.setdefault(repo, []).append((path, fm, original))
    return grouped, outcomes


def _mark(outcomes: dict, grouped: dict, repos: list[str], outcome: str, *, attempted: bool):
    for repo in repos:
        for path, _, _ in grouped[repo]:
            outcomes[path.parent.name].update(outcome=outcome, attempted=attempted)


def _receipt(ctx, now: datetime, result, outcomes: dict, *, quota: dict | None,
             attempted_repos: int, successful_repos: int) -> None:
    rows = [outcomes[fid] for fid in sorted(outcomes)]
    counts = Counter(row["outcome"] for row in rows)
    queryable = [row for row in rows if not row["outcome"].startswith("excluded_") and
                 row["outcome"] != DEFERRED_OPEN]
    receipt = {
        "schema": 1,
        "run_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_revision": getattr(ctx, "base_sha", None),
        "state": "proposed_not_deployed",
        "eligible_repositories": len({row["repository"] for row in queryable if row["repository"]}),
        "attempted_repositories": attempted_repos,
        DEFERRED_OPEN: counts[DEFERRED_OPEN],
        "validated_repositories": successful_repos,
        "outcomes": dict(sorted(counts.items())),
        "graphql_rate": quota,
        "graphql_http_requests": ctx.budget.calls,
        "graphql_cost_spent_known": result.graphql_cost_spent,
        "graphql_cost_unknown_requests": result.graphql_cost_unknown_requests,
        "records": rows,
    }
    result.items.append({"coverage": {"eligible_repositories": receipt["eligible_repositories"],
                                      "attempted_repositories": attempted_repos,
                                      "validated_repositories": successful_repos,
                                      DEFERRED_OPEN: counts[DEFERRED_OPEN]}})
    relative = RECEIPT_DIR / (now.strftime("%Y-%m-%dT%H") + ".json")
    if ctx.dry_run:
        result.would_write.append({"path": str(relative), "field": "*", "value": receipt})
    else:
        target = ctx.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        legacy._atomic_write(target, json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        result.paths.append(str(relative))
    result.summary = (f"GitHub popularity full: {attempted_repos}/{receipt['eligible_repositories']} "
                      f"repos attempted, {successful_repos} validated; "
                      + ", ".join(f"{name} {count}" for name, count in sorted(counts.items())))


def run(ctx):
    """Attempt every eligible mapped repository once; keep last-good on any failure."""
    from tick import StageResult

    now = ctx.now.astimezone(timezone.utc)
    grouped, outcomes = _inventory(ctx, now)
    repos = sorted(grouped)
    result = StageResult("popularity_full")
    result.graphql_cost_spent = 0
    result.graphql_cost_unknown_requests = 0
    attempted_repos = successful_repos = 0
    quota = None
    if not repos:
        _receipt(ctx, now, result, outcomes, quota=quota, attempted_repos=0, successful_repos=0)
        return result
    cooldown = legacy._observed_at(getattr(ctx, "cooldown_until", None))
    if cooldown and cooldown > now:
        _mark(outcomes, grouped, repos, "unattempted_cooldown", attempted=False)
        result.items.append({"cooldown_until": cooldown.isoformat()})
        _receipt(ctx, now, result, outcomes, quota=quota, attempted_repos=0, successful_repos=0)
        return result
    if ctx.budget.remaining_calls() < 1 or ctx.budget.remaining_seconds() < MIN_REMAINING_SECONDS:
        _mark(outcomes, grouped, repos, "unattempted_budget", attempted=False)
        _receipt(ctx, now, result, outcomes, quota=quota, attempted_repos=0, successful_repos=0)
        return result
    probe, headers, status = _call(ctx, "query { rateLimit { cost remaining resetAt } }")
    quota = _quota(probe, headers)
    _charge_cost(result, quota)
    if _limited(probe, status):
        _mark(outcomes, grouped, repos, "unattempted_rate_limit", attempted=False)
        result.items.append({"cooldown_until": _cooldown_until(now, headers, quota).isoformat()})
        _receipt(ctx, now, result, outcomes, quota=quota, attempted_repos=0, successful_repos=0)
        return result
    if not isinstance(quota, dict) or type(quota.get("remaining")) is not int:
        limited = _limited(probe, status)
        _mark(outcomes, grouped, repos, "unattempted_rate_limit" if limited else "unattempted_quota_unknown",
              attempted=False)
        if limited:
            result.items.append({"cooldown_until": _cooldown_until(now, headers).isoformat()})
        _receipt(ctx, now, result, outcomes, quota=None, attempted_repos=0, successful_repos=0)
        return result
    if quota["remaining"] - _next_batch_cost_bound(repos[:BATCH_SIZE]) < MIN_GRAPHQL_POINTS:
        _mark(outcomes, grouped, repos, "unattempted_rate_limit", attempted=False)
        result.items.append({"cooldown_until": _cooldown_until(now, headers, quota).isoformat()})
        _receipt(ctx, now, result, outcomes, quota=quota, attempted_repos=0, successful_repos=0)
        return result

    for start in range(0, len(repos), BATCH_SIZE):
        batch = repos[start:start + BATCH_SIZE]
        tail = repos[start:]
        if ctx.budget.remaining_calls() < 1 or ctx.budget.remaining_seconds() < MIN_REMAINING_SECONDS:
            _mark(outcomes, grouped, tail, "unattempted_budget", attempted=False)
            break
        if quota["remaining"] - _next_batch_cost_bound(batch) < MIN_GRAPHQL_POINTS:
            _mark(outcomes, grouped, tail, "unattempted_rate_limit", attempted=False)
            result.items.append({"cooldown_until": _cooldown_until(now, {}, quota).isoformat()})
            break
        doc, headers, status = _call(ctx, _query(batch))
        next_quota = _quota(doc, headers)
        _charge_cost(result, next_quota)
        attempted_repos += len(batch)
        if doc is None or not isinstance(doc.get("data"), dict):
            limited = _limited(doc, status)
            _mark(outcomes, grouped, batch, "attempted_rate_limited" if limited else "attempted_query_failure",
                  attempted=True)
            _mark(outcomes, grouped, repos[start + len(batch):],
                  "unattempted_rate_limit" if limited else "unattempted_query_failure", attempted=False)
            if limited:
                result.items.append({"cooldown_until": _cooldown_until(now, headers, quota).isoformat()})
            break
        data = doc["data"]
        error_aliases = {path[0] for error in doc.get("errors") or [] if isinstance(error, dict)
                         for path in [error.get("path")] if isinstance(path, list) and path
                         and isinstance(path[0], str)}
        if isinstance(next_quota, dict) and type(next_quota.get("remaining")) is int:
            quota = next_quota
        else:
            quota = None
        batch_valid = 0
        for index, repo in enumerate(batch):
            node = data.get(f"r{index}")
            records = grouped[repo]
            repo_valid = False
            for path, fm, original in records:
                row = outcomes[path.parent.name]
                row["attempted"] = True
                old = fm.get("popularity") if isinstance(fm.get("popularity"), dict) else {}
                old_id = old.get("github_repo_id")
                stats = _stats(node, repo, old_id)
                if stats is None:
                    row["outcome"] = ("attempted_graphql_error" if f"r{index}" in error_aliases else
                                      "attempted_invalid_identity_or_counts")
                    continue
                repo_valid = True
                if path.parent.name not in CURATED_EXEMPT and not clears_popularity_floor(
                        stats["stars"], stats["forks"], old.get("editorial_home"), old.get("downloads")):
                    row["outcome"] = "attempted_below_floor"
                    continue
                rewritten = legacy._rewrite(original, stats, now)
                if rewritten is None:
                    row["outcome"] = "attempted_rewrite_failure"
                    continue
                relative = str(path.relative_to(ctx.root))
                route = review_routing.classify([review_routing.Change(relative, "M", original, rewritten)])
                if route.review:
                    row["outcome"] = "attempted_review_deferred"
                    continue
                row.update(outcome="validated_update", observed_after=now.isoformat(timespec="seconds").replace("+00:00", "Z"))
                if ctx.dry_run:
                    result.would_write.append({"path": relative, "field": "popularity",
                                               "value": {"stars": stats["stars"], "forks": stats["forks"]}})
                else:
                    legacy._atomic_write(path, rewritten)
                    result.paths.append(relative)
            if repo_valid:
                batch_valid += 1
        successful_repos += batch_valid
        limited = _limited(doc, status)
        if limited or quota is None:
            reason = "unattempted_rate_limit" if limited else "unattempted_quota_unknown"
            _mark(outcomes, grouped, repos[start + len(batch):], reason, attempted=False)
            if limited:
                result.items.append({"cooldown_until": _cooldown_until(now, headers, quota).isoformat()})
            break

    _receipt(ctx, now, result, outcomes, quota=quota, attempted_repos=attempted_repos,
             successful_repos=successful_repos)
    return result


run.produces_review = False
