"""EspAtlas Jr — fork -> canonical-source resolution.

A launcher-catalog entry's repo can itself be a GitHub fork of another (often better-known,
more-starred) project. Authoring the fork's own thin stats under its own identity misrepresents
popularity and risks a duplicate entry once the canonical source is later drained too.
`resolve_source()` walks a repo to its canonical, non-fork origin so a caller (jr/drain.py's
candidate selection, jr/catalog_migrate.py's sweep) can author/rewrite THAT repo's identity
(url/maintainer/stars/forks) instead of the fork's.

`api` is injected — `api(owner, repo) -> raw GitHub repo API shape` (full_name, fork,
stargazers_count, forks_count, and — for a fork — source/parent, mirroring `gh api
repos/OWNER/REPO`'s real response shape) — so every function here is a pure orchestration over
that call: offline-testable with a fake api, zero network in tests. `default_api` is the one
real, network-touching implementation, used only by a live run.
"""
from __future__ import annotations
import json
import subprocess


def default_api(owner: str, repo: str) -> dict:
    """Real GitHub API client (`gh api repos/OWNER/REPO`, authed through `gh` for a higher rate
    limit) — the one network-touching function in this module. Returns {} if unresolved."""
    p = subprocess.run(["gh", "api", f"repos/{owner}/{repo}"], capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        return {}
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {}


def _stats(data: dict, fallback_full_name: str) -> dict:
    return {
        "full_name": data.get("full_name") or fallback_full_name,
        "stars": data.get("stargazers_count") or 0,
        "forks": data.get("forks_count") or 0,
    }


def resolve_source(owner: str, repo: str, api) -> dict:
    """Given a repo, resolve it to its canonical, non-fork SOURCE.

    A non-fork repo resolves to itself. A fork resolves via its own `.source.full_name`
    (GitHub's network-root pointer) when present; otherwise walks `.parent` (the immediate
    fork-from repo, itself possibly a fork) one hop at a time via `api` until a non-fork is
    reached — a multi-level fork chain (fork of a fork of the root) still resolves all the way
    to the root, not just one hop up. Returns {full_name, stars, forks} of the source (or of the
    original repo if it isn't a fork, or if resolution can't proceed any further)."""
    fallback = f"{owner}/{repo}"
    data = api(owner, repo) or {}
    if not data.get("fork"):
        return _stats(data, fallback)

    source = data.get("source")
    if source and source.get("full_name"):
        return _stats(source, source["full_name"])

    current = data
    while current.get("fork") and (current.get("parent") or {}).get("full_name"):
        parent_full = current["parent"]["full_name"]
        p_owner, p_repo = parent_full.split("/", 1)
        current = api(p_owner, p_repo) or {}
        if not current:
            return {"full_name": parent_full, "stars": 0, "forks": 0}
    return _stats(current, fallback)
