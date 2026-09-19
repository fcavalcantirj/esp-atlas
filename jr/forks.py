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

THE CONCEPTUAL-PORT GAP (the RogueDuck audit). `resolve_source()` only catches a real git
button-fork (`repo_meta.fork is True`). A repo with `fork=False` that CONCEPTUALLY reimplements
a more-canonical, not-yet-catalogued upstream sharing the same core name-token — never clicked
GitHub's Fork button, so `fork` is False — sailed through as a brand-new original: thin stats
now, a future duplicate once the real upstream is later drained too. `resolve_canonical()`
closes that gap: for a non-fork, it searches (an injected `search`, `gh search repositories`)
the candidate's SIGNIFICANT core name-token(s) and resolves away ONLY to a repo that shares an
EXACT core token and clears a deliberately strict bar (>=5x the candidate's own stars AND above
STAR_FLOOR) — conservative on purpose, so a genuine original (RogueDuck: 6 stars, nothing else
shares its tokens) never gets swept away by a coincidental token match or a marginally bigger
sibling. A real git fork still resolves exactly as `resolve_source()` always has; `resolve_
canonical()` is a superset entry point, not a behavior change to the fork path.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
from pathlib import Path

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
from tools import GENERIC_NAME_TOKENS  # noqa: E402

from esp_atlas_core.floor import STAR_FLOOR  # noqa: E402

# How many stars a non-fork's own search-discovered "upstream" must clear over the candidate's
# own star count to count as MEANINGFULLY more canonical — a marginally bigger same-named
# sibling is not evidence the candidate is a port, just that two similar projects both exist.
CONCEPTUAL_PORT_STAR_MULTIPLE = 5


def default_api(owner: str, repo: str) -> dict:  # pragma: no cover — real network call, exercised manually
    """Real GitHub API client (`gh api repos/OWNER/REPO`, authed through `gh` for a higher rate
    limit) — the one network-touching function in this module. Returns {} if unresolved."""
    p = subprocess.run(["gh", "api", f"repos/{owner}/{repo}"], capture_output=True, text=True, timeout=30)
    if p.returncode != 0:
        return {}
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {}


def default_search(name_token: str) -> list[dict]:  # pragma: no cover — real network call, see default_api
    """Real GitHub repo search client (`gh search repos <token> --match name`, authed through
    `gh`) — the one network-touching search implementation in this module, used only by a live
    run. Returns [{full_name, stars, fork}, ...] (empty on any failure or no results)."""
    p = subprocess.run(
        ["gh", "search", "repos", name_token, "--match", "name", "--sort", "stars",
         "--limit", "10", "--json", "fullName,stargazersCount,isFork"],
        capture_output=True, text=True, timeout=30,
    )
    if p.returncode != 0:
        return []
    try:
        raw = json.loads(p.stdout)
    except json.JSONDecodeError:
        return []
    return [
        {"full_name": r["fullName"], "stars": r.get("stargazersCount") or 0, "fork": bool(r.get("isFork"))}
        for r in raw if isinstance(r, dict) and r.get("fullName")
    ]


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
    return _resolve_fork(data, fallback, api)


def _resolve_fork(data: dict, fallback: str, api) -> dict:
    """The fork-walk `resolve_source()` has always done, factored out so `resolve_canonical()`
    can reach the SAME behavior for a real git fork from a `data` dict it already has in hand
    (no redundant fetch) — resolve_source() itself is unchanged, just now a thin wrapper."""
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


def _core_tokens(repo_name: str) -> set[str]:
    """The SIGNIFICANT core name-token(s) of a bare repo name (not owner/repo) — split on
    `-`/`_`/whitespace, lowercased, at least 4 chars (mirrors jr/scorer.py's own significant-
    token split), with GENERIC_NAME_TOKENS (jr/tools.py's stoplist: esp32/esp8266/m5stack/...)
    removed so a token too generic to mean anything on its own (shared by thousands of
    unrelated repos) never counts as evidence of a shared identity."""
    tokens = {t for t in re.split(r"[-_\s]", (repo_name or "").lower()) if len(t) >= 4}
    return tokens - GENERIC_NAME_TOKENS


def resolve_canonical(owner: str, repo: str, meta: dict, search, api) -> dict:
    """Given a repo, resolve it to its canonical upstream — covering BOTH a real git fork and a
    non-fork CONCEPTUAL port of an upstream that isn't (yet) catalogued (see the module
    docstring's "conceptual-port gap"). `meta` is the same raw GitHub repo API shape `api`
    itself returns (full_name, fork, stargazers_count, forks_count, source/parent).

    A real fork (`meta['fork']` True) resolves exactly as `resolve_source()` does — same walk,
    same `api` contract, `search` never consulted.

    A non-fork resolves to itself UNLESS its SIGNIFICANT core name-token(s) (`_core_tokens()`,
    GENERIC_NAME_TOKENS-stopped) are found, via the injected `search(name_token) -> [{full_name,
    stars, fork}, ...]` (`default_search` shells the real `gh search repositories`; tests inject
    a fake, zero network), on ANOTHER repo (not itself, not itself a fork) that shares an EXACT
    core token AND clears a deliberately strict bar: stars >= CONCEPTUAL_PORT_STAR_MULTIPLE times
    the candidate's own AND stars >= STAR_FLOOR. Ties/multiple qualifying matches: the
    highest-starred one wins. Nothing qualifying: the candidate stays canonical (resolves to
    itself) — conservative by design, so a genuine original (a RogueDuck: real firmware, few
    stars, nothing else sharing its tokens) is never swept away by a coincidental token overlap
    or a merely-bigger sibling."""
    fallback = f"{owner}/{repo}"
    if meta.get("fork"):
        return _resolve_fork(meta, fallback, api)

    candidate_tokens = _core_tokens(repo)
    if not candidate_tokens:
        return _stats(meta, fallback)

    candidate_stars = meta.get("stargazers_count") or 0
    query = " ".join(sorted(candidate_tokens))
    best = None
    for result in search(query) or []:
        full_name = result.get("full_name") or ""
        if not full_name or full_name.lower() == fallback.lower() or result.get("fork"):
            continue
        if not (candidate_tokens & _core_tokens(full_name.split("/")[-1])):
            continue
        stars = result.get("stars") or 0
        if stars < STAR_FLOOR or stars < candidate_stars * CONCEPTUAL_PORT_STAR_MULTIPLE:
            continue
        if best is None or stars > best["stars"]:
            best = {"full_name": full_name, "stars": stars, "forks": 0}
    return best or _stats(meta, fallback)
