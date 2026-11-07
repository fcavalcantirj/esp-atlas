"""Bounded detail-page GitHub counts; never changes the cited catalog snapshot.

The Postgres tables are created by migrations/20261106_live_popularity.sql. Without a
configured primary connection or that migration this endpoint fails closed: no GitHub call.
See SPEC-firmware-floor.md, On-view GitHub counts.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote, urlsplit

import httpx

_REPO_PART = re.compile(r"[A-Za-z0-9_.-]+")
_CACHE_AGE = timedelta(hours=1)
_STALE_AGE = timedelta(days=7)
_LEASE = timedelta(seconds=10)
_HOURLY_BUDGET = 20
_FETCH_DEADLINE = 5


@dataclass(frozen=True)
class Identity:
    firmware_id: str
    full_name: str
    source_url: str
    repo_id: int
    github_as_of: datetime | date
    stars: int | None
    forks: int | None


@dataclass(frozen=True)
class Snapshot:
    stars: int
    forks: int
    observed_at: datetime
    full_name: str
    repo_id: int


@dataclass(frozen=True)
class Claim:
    action: str
    snapshot: Snapshot | None = None
    token: str | None = None
    retry_after_seconds: int | None = None


def _count(value):
    return value if type(value) is int and value >= 0 else None


def _date(value):
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except ValueError:
        return None


def _cited(record: dict, field: str, url: str) -> bool:
    return any(s.get("field") == field and s.get("url") == url
               for s in record.get("sources", []) if isinstance(s, dict))


def identity_from_record(record: dict) -> Identity | None:
    url = record.get("url")
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    if (parsed.scheme != "https" or parsed.netloc.lower() != "github.com" or
            parsed.query or parsed.fragment or parsed.username or parsed.password):
        return None
    parts = parsed.path.removeprefix("/").split("/")
    if len(parts) != 2 or not all(_REPO_PART.fullmatch(part) and part not in (".", "..") for part in parts):
        return None
    popularity = record.get("popularity") or {}
    if not isinstance(popularity, dict):
        return None
    repo_id = popularity.get("github_repo_id")
    observed = _date(popularity.get("github_as_of"))
    if (type(repo_id) is not int or repo_id <= 0 or observed is None or
            not _cited(record, "popularity.github_repo_id", url) or
            not _cited(record, "popularity.github_as_of", url)):
        return None
    return Identity(record["id"], "/".join(parts), url, repo_id, observed,
                    _count(popularity.get("stars")), _count(popularity.get("forks")))


def _newer(snapshot: Snapshot | None, identity: Identity) -> bool:
    if snapshot is None or snapshot.repo_id != identity.repo_id or snapshot.full_name.casefold() != identity.full_name.casefold():
        return False
    observed = snapshot.observed_at.astimezone(timezone.utc)
    catalog = identity.github_as_of
    if isinstance(catalog, datetime):
        return observed > catalog
    return observed.date() > catalog


def _snapshot_json(snapshot: Snapshot | None, identity: Identity):
    if not _newer(snapshot, identity):
        return None
    return {"stars": snapshot.stars, "forks": snapshot.forks,
            "observed_at": snapshot.observed_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "source_url": identity.source_url, "repo_id": identity.repo_id}


def _response(record: dict, identity: Identity | None, outcome: str,
              snapshot: Snapshot | None = None, retry_after: int | None = None):
    popularity = record.get("popularity") or {}
    catalog = {"stars": _count(popularity.get("stars")), "forks": _count(popularity.get("forks")),
               "github_as_of": popularity.get("github_as_of"), "source_url": record.get("url"),
               "repo_id": identity.repo_id if identity else
               (popularity.get("github_repo_id") if type(popularity.get("github_repo_id")) is int else None)}
    overlay = _snapshot_json(snapshot, identity) if identity else None
    if outcome in ("fresh", "cached", "stale") and overlay is None:
        outcome = "unavailable"
    return {"firmware_id": record["id"], "outcome": outcome, "catalog": catalog,
            "github": overlay, "retry_after_seconds": retry_after}


def _seconds(until: datetime | None, now: datetime) -> int | None:
    return max(1, math.ceil((until - now).total_seconds())) if until and until > now else None


class PostgresPopularityStore:
    """One primary-only coordinator; claim commits before network I/O."""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self):
        import psycopg
        from psycopg.rows import dict_row
        return psycopg.connect(self.dsn, connect_timeout=2, autocommit=True, row_factory=dict_row)

    def claim(self, identity: Identity, token: str) -> Claim:
        with self._connect() as conn, conn.transaction():
            conn.execute("SET LOCAL statement_timeout = '2000ms'")
            now = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
            budget = conn.execute("SELECT * FROM popularity_refresh_budget WHERE singleton = true FOR UPDATE").fetchone()
            if budget is None:
                raise RuntimeError("popularity coordinator migration missing")
            conn.execute("INSERT INTO popularity_refresh_repo (repo_id, full_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                         (identity.repo_id, identity.full_name))
            repo = conn.execute("SELECT * FROM popularity_refresh_repo WHERE repo_id = %s FOR UPDATE",
                                (identity.repo_id,)).fetchone()
            snapshot = None
            if (repo["full_name"].casefold() == identity.full_name.casefold() and
                    _count(repo["stars"]) is not None and _count(repo["forks"]) is not None and
                    repo["observed_at"] is not None and now - repo["observed_at"] <= _STALE_AGE):
                snapshot = Snapshot(repo["stars"], repo["forks"], repo["observed_at"],
                                    repo["full_name"], identity.repo_id)
            if snapshot and _newer(snapshot, identity) and now - snapshot.observed_at <= _CACHE_AGE:
                return Claim("cached", snapshot)
            hour = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
            used = budget["used"] if budget["hour_start"] == hour else 0
            waits = [budget["lease_until"], budget["cooldown_until"], repo["lease_until"], repo["retry_after"]]
            retry = max((_seconds(t, now) or 0 for t in waits), default=0)
            if used >= _HOURLY_BUDGET:
                return Claim("budget", snapshot, retry_after_seconds=max(retry, _seconds(hour + timedelta(hours=1), now)))
            if retry:
                return Claim("wait", snapshot, retry_after_seconds=retry)
            until = now + _LEASE
            if repo["full_name"].casefold() != identity.full_name.casefold():
                # A newly cited URL for this stable ID invalidates old-name counts.
                # Do this under the same global/repo locks before granting a lease.
                conn.execute("UPDATE popularity_refresh_repo SET full_name=%s, stars=NULL, forks=NULL, observed_at=NULL WHERE repo_id=%s",
                             (identity.full_name, identity.repo_id))
            conn.execute("UPDATE popularity_refresh_budget SET hour_start=%s, used=%s, lease_token=%s, lease_until=%s WHERE singleton=true",
                         (hour, used + 1, token, until))
            conn.execute("UPDATE popularity_refresh_repo SET lease_token=%s, lease_until=%s WHERE repo_id=%s",
                         (token, until, identity.repo_id))
            return Claim("fetch", snapshot, token)

    def publish(self, identity: Identity, token: str, stars: int, forks: int) -> Snapshot | None:
        if _count(stars) is None or _count(forks) is None:
            return None
        with self._connect() as conn, conn.transaction():
            conn.execute("SET LOCAL statement_timeout = '2000ms'")
            now = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
            budget = conn.execute("SELECT * FROM popularity_refresh_budget WHERE singleton=true FOR UPDATE").fetchone()
            repo = conn.execute("SELECT * FROM popularity_refresh_repo WHERE repo_id=%s FOR UPDATE",
                                (identity.repo_id,)).fetchone()
            if not (budget and repo and budget["lease_token"] == token and repo["lease_token"] == token and
                    budget["lease_until"] > now and repo["lease_until"] > now and
                    repo["full_name"].casefold() == identity.full_name.casefold()):
                return None
            conn.execute("UPDATE popularity_refresh_repo SET full_name=%s, stars=%s, forks=%s, observed_at=%s, lease_token=NULL, lease_until=NULL, retry_after=NULL WHERE repo_id=%s",
                         (identity.full_name, stars, forks, now, identity.repo_id))
            conn.execute("UPDATE popularity_refresh_budget SET lease_token=NULL, lease_until=NULL WHERE singleton=true")
            return Snapshot(stars, forks, now, identity.full_name, identity.repo_id)

    def fail(self, identity: Identity, token: str, *, global_cooldown: int = 0, repo_backoff: int = 0) -> None:
        with self._connect() as conn, conn.transaction():
            conn.execute("SET LOCAL statement_timeout = '2000ms'")
            now = conn.execute("SELECT clock_timestamp() AS t").fetchone()["t"]
            budget = conn.execute("SELECT * FROM popularity_refresh_budget WHERE singleton=true FOR UPDATE").fetchone()
            repo = conn.execute("SELECT * FROM popularity_refresh_repo WHERE repo_id=%s FOR UPDATE",
                                (identity.repo_id,)).fetchone()
            if global_cooldown:
                until = now + timedelta(seconds=global_cooldown)
                conn.execute("UPDATE popularity_refresh_budget SET cooldown_until=GREATEST(coalesce(cooldown_until, %s), %s) WHERE singleton=true",
                             (until, until))
            if budget and repo and budget["lease_token"] == token and repo["lease_token"] == token:
                if repo_backoff:
                    conn.execute("UPDATE popularity_refresh_repo SET retry_after=%s, lease_token=NULL, lease_until=NULL WHERE repo_id=%s",
                                 (now + timedelta(seconds=repo_backoff), identity.repo_id))
                else:
                    conn.execute("UPDATE popularity_refresh_repo SET lease_token=NULL, lease_until=NULL WHERE repo_id=%s",
                                 (identity.repo_id,))
                conn.execute("UPDATE popularity_refresh_budget SET lease_token=NULL, lease_until=NULL WHERE singleton=true")


async def fetch_github(identity: Identity):
    """A single bounded complete read; timeout includes connect, headers and body."""
    url = "https://api.github.com/repos/" + "/".join(quote(p, safe="") for p in identity.full_name.split("/"))
    async with asyncio.timeout(_FETCH_DEADLINE):
        async with httpx.AsyncClient(timeout=httpx.Timeout(4.5), follow_redirects=False) as client:
            async with client.stream("GET", url, headers={"Accept": "application/vnd.github+json",
                                                            "User-Agent": "esp-atlas-on-view"}) as response:
                body = bytearray()
                async for chunk in response.aiter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ValueError("GitHub response too large")
                return response.status_code, bytes(body), dict(response.headers)


def _cooldown(headers: dict) -> int:
    now = datetime.now(timezone.utc)
    values = []
    retry = headers.get("retry-after")
    if retry:
        try:
            values.append(max(1, math.ceil(float(retry))))
        except ValueError:
            try:
                values.append(max(1, math.ceil((parsedate_to_datetime(retry) - now).total_seconds())))
            except (TypeError, ValueError, OverflowError):
                pass
    reset = headers.get("x-ratelimit-reset")
    if reset:
        try:
            values.append(max(1, math.ceil(float(reset) - now.timestamp())))
        except ValueError:
            pass
    return max(values) if values else 60


async def live_popularity(record: dict, *, store=None, fetch=None):
    identity = identity_from_record(record)
    if identity is None:
        return _response(record, None, "ineligible")
    if store is None:
        dsn = os.environ.get("POPULARITY_DATABASE_URL")
        if not dsn:
            return _response(record, identity, "unavailable")
        store = PostgresPopularityStore(dsn)
    token = uuid.uuid4().hex
    try:
        claim = await asyncio.to_thread(store.claim, identity, token)
    except Exception:
        return _response(record, identity, "unavailable")
    if claim.action == "cached":
        return _response(record, identity, "cached", claim.snapshot)
    if claim.action != "fetch":
        return _response(record, identity, "stale", claim.snapshot, claim.retry_after_seconds)
    try:
        status, body, headers = await (fetch or fetch_github)(identity)
        if status == 200:
            doc = json.loads(body)
            if not isinstance(doc, dict) or type(doc.get("id")) is not int or doc["id"] != identity.repo_id or not isinstance(doc.get("full_name"), str) or doc["full_name"].casefold() != identity.full_name.casefold():
                raise ValueError("GitHub repository identity changed")
            stars, forks = _count(doc.get("stargazers_count")), _count(doc.get("forks_count"))
            if stars is None or forks is None:
                raise ValueError("GitHub counts missing or invalid")
            try:
                published = await asyncio.to_thread(store.publish, identity, token, stars, forks)
            except Exception:
                published = None
            return _response(record, identity, "fresh" if published else "stale",
                             published or claim.snapshot)
        cooldown = _cooldown(headers) if status in (403, 429) else 0
        backoff = 3600 if status == 404 else 300 if status >= 500 else 60
        try:
            await asyncio.to_thread(store.fail, identity, token, global_cooldown=cooldown,
                                    repo_backoff=backoff)
        except Exception:
            pass
        return _response(record, identity, "stale", claim.snapshot, cooldown or backoff)
    except Exception:
        try:
            await asyncio.to_thread(store.fail, identity, token, repo_backoff=60)
        except Exception:
            pass
        return _response(record, identity, "stale", claim.snapshot, 60)
