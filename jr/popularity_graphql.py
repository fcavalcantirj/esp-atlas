"""GitHub GraphQL popularity helpers shared by Jr's popularity lanes.

Extracted verbatim from jr/popularity_full.py on the halted R3 branch
(dasbrow/r3ab-recovery-coverage-20261107, b34446dc), which never reached main: query
batching, the `gh api graphql -i` envelope parser, rate-limit/quota/cooldown handling and
repository identity validation. Behaviour is unchanged; keep it that way. No PR
inventory, no catalog writes and no floors live here.
"""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import stage_popularity_refresh as legacy

BATCH_SIZE = 25
MIN_GRAPHQL_POINTS = 50  # leave headroom for other consumers of Jr's token
MIN_REMAINING_SECONDS = 20


def _next_batch_cost_bound(repos: list[str]) -> int:
    """Scalar-only repository lookup has no connections; GitHub's minimum is 1 point.

    Keep this explicit so the admission check reserves points *after* the next
    query, not merely before it. If fields/connections change, revise the
    bound and its boundary tests before raising the query's cost ceiling.
    """
    return 1 if repos else 0


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
