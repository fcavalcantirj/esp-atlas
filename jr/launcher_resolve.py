"""EspAtlas Jr — the deterministic repo resolver for launcher entries with no repo (jr/launcher_resolve.py).

G1b (2026-11-03 jr-fixes): of the LauncherHub catalog's 2,897 entries, 1,229 carry `github: None`
and ~20 an owner-only url (`https://github.com/geo-tp` on "IButton M5Stick C Plus2"). Every tick
jr/stage_admit.py rejected them as `repo_unresolved: unparseable repo` without a single call.

This module resolves such an entry with ONE `gh api search/repositories` call: q = the entry's
significant name tokens plus `user:<owner>` (the owner-only url's owner, else the entry `author`
normalized to a GitHub login). The search is only accepted when EXACTLY ONE hit's repo name
shares a significant token with the entry name, on a complete result page — anything else is
"no source repo" and the caller decides it once with a TTL. No fuzzy scoring, no LLM: the same
entry and the same search answer always resolve the same way. The accepted repo is only a
candidate; the scorer and the popularity floor still decide it.

`gh` is injected (the tick's counted ctx.gh); nothing here touches the network on its own.
"""
from __future__ import annotations

import json
import re
import urllib.parse

import tools
from budget import BudgetExceeded

# Searches per tick, inside the tick's call budget AND admit's call share (stage_admit checks
# both). ~1,250 entries need resolving and an inconclusive one is re-searched after the 7-day
# unresolved TTL: 10/hour = 1,680/week, so the whole backlog cycles within one TTL.
RESOLVER_CALLS_PER_TICK = 10
SEARCH_PER_PAGE = 30
MAX_QUERY_TOKENS = 4
NO_SOURCE_REPO = "no_source_repo"
LEDGER_ID_PREFIX = "launcher-"
LEDGER_REPO_PREFIX = "launcher:"   # ':' never appears in a GitHub owner, so no real repo collides

# Device-family and filler words a launcher name carries that say nothing about WHICH repo it is
# ("IButton M5Stick C Plus2" is the iButton repo; "M5Stick", "Plus2" fit half of geo-tp's repos).
_RESOLVER_STOPWORDS = tools.NAME_TOKEN_DEDUP_STOPWORDS | {
    "m5stick", "m5stickc", "m5stickcplus", "m5stickcplus2", "stick", "sticks3", "cplus", "cplus2",
    "plus", "plus2", "m5cardputer", "cardputer", "paper", "papers3", "m5paper", "m5stack",
    "for", "by", "and", "the", "with", "version", "beta", "alpha", "edition", "fork", "port",
}
_VERSION_TOKEN = re.compile(r"^v\d+$")
_OWNER_ONLY = re.compile(r"^https?://(?:www\.)?github\.com/([A-Za-z0-9-]+)/?$", re.I)


def needs_resolution(entry: dict) -> bool:
    """True when the entry's `github` is None/blank or an owner-only github.com url — the two
    shapes this resolver handles. Junk text and non-GitHub homepages stay on the existing path."""
    github = (entry.get("github") or "").strip()
    return not github or bool(_OWNER_ONLY.match(github))


def normalize_login(raw: str | None) -> str | None:
    """A launcher `author` in GitHub-login form: runs of `_`, whitespace and `.` become one hyphen,
    anything else outside [a-z0-9-] is dropped, no leading/trailing hyphen, at most 39 chars.
    None when nothing is left."""
    s = re.sub(r"[_\s.]+", "-", (raw or "").strip().lower())
    s = re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9-]", "", s)).strip("-")[:39].rstrip("-")
    return s or None


def owner_hint(entry: dict) -> str | None:
    """The owner the search is scoped to: the owner-only url's owner, else the author."""
    m = _OWNER_ONLY.match((entry.get("github") or "").strip())
    if m:
        return m.group(1).lower()
    return normalize_login(entry.get("author"))


def significant_tokens(name: str | None) -> list[str]:
    """The entry name's identifying tokens, in name order, deduped: lowercase alphanumeric runs of
    3+ chars that are not device-family/filler words or version tags."""
    out = []
    for t in re.split(r"[^a-z0-9]+", (name or "").lower()):
        if len(t) >= 3 and t not in _RESOLVER_STOPWORDS and not _VERSION_TOKEN.match(t) and t not in out:
            out.append(t)
    return out


def build_query(entry: dict) -> str | None:
    """The search q: up to MAX_QUERY_TOKENS significant name tokens plus `user:<owner>`. None
    when the name has no significant token or no owner is known: an unscoped search over all of
    GitHub would accept a stranger's repo on a lone shared token, so that entry is inconclusive."""
    tokens = significant_tokens(entry.get("name"))[:MAX_QUERY_TOKENS]
    owner = owner_hint(entry)
    if not tokens or not owner:
        return None
    return " ".join(tokens + [f"user:{owner}"])


def ledger_key(entry: dict) -> tuple[str, str] | None:
    """(id, repo) the entry's own decision is recorded under: the launcher fid, never empty.
    None when the entry has no fid — it cannot be keyed, so it must never reach the ledger."""
    fid = str(entry.get("fid") or "").strip()
    if not fid:
        return None
    return f"{LEDGER_ID_PREFIX}{fid}", f"{LEDGER_REPO_PREFIX}{fid}"


def _name_matches(tokens: list[str], repo_name: str) -> bool:
    """A repo name shares a significant token: as a whole name token, or (4+ chars) inside the
    compacted name (`M5IButton` carries `ibutton`)."""
    low = repo_name.lower()
    words = set(re.split(r"[^a-z0-9]+", low))
    compact = re.sub(r"[^a-z0-9]", "", low)
    return any(t in words or (len(t) >= 4 and t in compact) for t in tokens)


def match_hits(entry: dict, items: list) -> list[str]:
    """full_names of the search hits whose repo name shares a significant token with the entry."""
    tokens = significant_tokens(entry.get("name"))
    out = []
    for it in items if isinstance(items, list) else []:
        full = (it or {}).get("full_name") if isinstance(it, dict) else None
        if full and "/" in full and _name_matches(tokens, full.split("/", 1)[1]):
            out.append(full)
    return out


def resolve(entry: dict, gh) -> dict:
    """{repo, query, matches, error}: `repo` is the one accepted owner/repo, else None. One `gh`
    call at most (none when there is nothing to search for). BudgetExceeded propagates; any other
    failure resolves to nothing with the error, never raises."""
    q = build_query(entry)
    out = {"repo": None, "query": q, "matches": [], "error": None}
    if q is None:
        out["error"] = "no searchable name tokens or owner"
        return out
    try:
        p = gh("api", f"search/repositories?q={urllib.parse.quote(q, safe=':')}&per_page={SEARCH_PER_PAGE}")
    except BudgetExceeded:
        raise
    except Exception as e:  # noqa: BLE001 — a failed search is an inconclusive one, retried after the TTL
        out["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        return out
    if getattr(p, "returncode", 1) != 0:
        out["error"] = (getattr(p, "stderr", "") or "search failed").strip()[:120]
        return out
    try:
        doc = json.loads(getattr(p, "stdout", "") or "{}")
    except json.JSONDecodeError as e:
        out["error"] = f"unparseable search response: {e}"
        return out
    items = doc.get("items") if isinstance(doc, dict) else None
    items = items if isinstance(items, list) else []
    out["matches"] = match_hits(entry, items)
    complete = not doc.get("incomplete_results") and (doc.get("total_count") or 0) <= len(items)
    if len(out["matches"]) == 1 and complete:
        out["repo"] = out["matches"][0]
    return out
