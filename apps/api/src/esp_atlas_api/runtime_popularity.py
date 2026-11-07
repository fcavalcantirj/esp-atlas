"""Read-only runtime observations; never used by catalog validation or Jr admission.

V1 contract: an atomic Redis JSON snapshot with schema_version, version,
catalog_revision, published_at and records keyed by firmware ID. Each record has
repository_url, github_repo_id, stars, forks and github_as_of. No GitHub or LLM
requests occur here. Disabled by default; storage errors retain the last valid
snapshot, then dated catalog fallback. Observation times are never fabricated.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import logging
import os
import re
import threading
import time
from urllib.parse import urlsplit

import httpx

KEY = "esp-atlas:popularity:v1:current"
CACHE_SECONDS = 30
logger = logging.getLogger(__name__)


def enabled():
    return os.environ.get("POPULARITY_RUNTIME_ENABLED") == "1"


def canonical_repository(url):
    if not isinstance(url, str):
        return None
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?", url)
    if not match:
        return None
    owner, repo = match.groups()
    repo = repo.removesuffix(".git")
    if owner in {".", ".."} or repo in {"", ".", ".."}:
        return None
    return f"https://github.com/{owner}/{repo}".lower()


def _date(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError, AttributeError):
        return None


def validate_snapshot(value, *, now=None):
    now = now or datetime.now(timezone.utc)
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported metrics snapshot")
    if not isinstance(value.get("version"), str) or not 1 <= len(value["version"]) <= 200:
        raise ValueError("missing snapshot version")
    if not re.fullmatch(r"[a-f0-9]{40}", str(value.get("catalog_revision", ""))):
        raise ValueError("missing catalog revision")
    published = _date(value.get("published_at"))
    if published is None or published > now + timedelta(minutes=5):
        raise ValueError("invalid publication date")
    if not isinstance(value.get("records"), dict):
        raise ValueError("missing snapshot records")
    for fid, row in value["records"].items():
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", fid) or not isinstance(row, dict):
            raise ValueError("invalid metrics record")
        if not canonical_repository(row.get("repository_url")):
            raise ValueError("invalid repository URL")
        for key, minimum in (("stars", 0), ("forks", 0), ("github_repo_id", 1)):
            if type(row.get(key)) is not int or not minimum <= row[key] <= 2**53-1:
                raise ValueError("invalid count or repository identity")
        observed = _date(row.get("github_as_of"))
        if observed is None or observed > published or observed > now + timedelta(minutes=5):
            raise ValueError("invalid observation date")
    return value


def _load():
    url = os.environ.get("POPULARITY_REDIS_REST_URL", "")
    token = os.environ.get("POPULARITY_REDIS_READ_TOKEN", "")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or not token:
        raise ValueError("runtime metrics store not configured")
    # POST transports a Redis GET, using a read-only credential. Never redirect
    # a credential-bearing request. Keep payloads and credentials out of logs.
    with httpx.Client(timeout=2.0, follow_redirects=False) as client:
        with client.stream("POST", url, headers={"Authorization": f"Bearer {token}"}, json=["GET", KEY]) as response:
            response.raise_for_status()
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 2_000_000:
                    raise ValueError("metrics snapshot exceeds size limit")
    result = json.loads(body).get("result")
    if not isinstance(result, str):
        raise ValueError("metrics snapshot unavailable")
    return json.loads(result)


class SnapshotReader:
    def __init__(self, *, load=_load, clock=time.monotonic, now=lambda: datetime.now(timezone.utc)):
        self.load, self.clock, self.now = load, clock, now
        self.snapshot = None
        self.next_read = float("-inf")
        self.lock = threading.Lock()

    def read(self):
        if not enabled():
            return None
        with self.lock:
            if self.clock() >= self.next_read:
                try:
                    candidate = validate_snapshot(self.load(), now=self.now())
                    if self.snapshot and _date(candidate["published_at"]) < _date(self.snapshot["published_at"]):
                        raise ValueError("snapshot publication regressed")
                    self.snapshot = deepcopy(candidate)
                except Exception:
                    logger.warning("Runtime popularity unavailable; retaining dated observations")
                self.next_read = self.clock() + CACHE_SECONDS
            return deepcopy(self.snapshot)


def resolve_records(records, snapshot, *, now=None):
    """Pure overlay; source equality and existing numeric identity must agree."""
    now = now or datetime.now(timezone.utc)
    resolved = []
    for record in records:
        result = deepcopy(record)
        pop = dict(result.get("popularity") or {})
        row = (snapshot or {}).get("records", {}).get(record["id"])
        source = canonical_repository(record.get("url"))
        catalog_date = _date(pop.get("github_as_of"))
        if row and source and source == canonical_repository(row["repository_url"]) and (
            pop.get("github_repo_id") is None or pop["github_repo_id"] == row["github_repo_id"]
        ) and (catalog_date is None or _date(row["github_as_of"]) >= catalog_date):
            pop.update({k: row[k] for k in ("stars", "forks", "github_repo_id", "github_as_of")})
            pop.update(origin="runtime", snapshot_version=snapshot["version"])
            fields = {f"popularity.{k}" for k in ("stars", "forks", "github_repo_id", "github_as_of")}
            result["sources"] = [s for s in result.get("sources", []) if s.get("field") not in fields]
            result["sources"] += [{"field": field, "url": row["repository_url"],
                                   "verified": _date(row["github_as_of"]).date().isoformat()} for field in sorted(fields)]
        elif pop:
            pop.update(origin="catalog")
        if pop:
            observed = _date(pop.get("github_as_of"))
            pop["stale"] = observed is None or now - observed > timedelta(hours=2)
            result["popularity"] = pop
        resolved.append(result)
    return resolved
