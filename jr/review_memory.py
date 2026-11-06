"""EspAtlas Jr — durable owner-review decisions (jr/review_memory.py, SPEC-jr-review-routing.md §5).

ONE question: has the owner already been asked about this target, on this evidence? A needs_review
target routes its tick PR to `jr-review`, and a review PR is not merged on its own — so a decision
recorded only in that PR's ledger never reached main, and every hourly tick asked again
(#1478 … #1490, gdantas04/cardputer-system-monitor). Two halves close it:

- `reconcile` reads GitHub's jr-review PRs (open AND closed, one counted `gh pr list`) and writes
  each target they raised into the tick's worktree ledger as a live decision
  (memory.record_review_decision). The tick runs it before the stages.
- The admit gate (jr/stage_admit.py) holds a target whose live decision has the same evidence
  revision (`holds`): no review item, so the tick PR routes on its files alone — bookkeeping goes
  AUTO and carries the decision onto main. Main's ledger then holds it across ticks and restarts.

The PR body is the hand-off: render_marker() puts the targets in a hidden comment; parse_targets()
reads it back, and reads PRs that predate the marker from their rendered "Needs owner review" lines.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone

import device_evidence
import memory
from esp_atlas_core.floor import DOWNLOAD_FLOOR, FORK_FLOOR, STAR_FLOOR, is_editorial_home
from review_routing import REVIEW_LABEL

MARKER = "jr-review-targets"
_MARKER_RE = re.compile(r"<!--\s*" + MARKER + r":\s*(.*?)\s*-->", re.S)
_LEGACY_HEADER = "### Needs owner review"
_LEGACY_LINE_RE = re.compile(r"^- `([^`/\s]+/[^`\s]+)` \(`([^`\s]+)`\)")
REVIEW_PR_LIMIT = 200
OUTCOMES = {"OPEN": "open", "CLOSED": "closed"}     # MERGED: its ledger already landed on main
TARGET_KEYS = ("id", "repo", "repo_id", "evidence_rev", "reason")


# --- evidence revision -------------------------------------------------------------------------

def evidence(meta: dict, downloads: int | None = None) -> dict:
    """The raw facts a review decision was taken on, kept for a human: stars, forks, the launcher's
    downloads, an independent editorial home, and the source revision (GitHub `pushed_at`)."""
    homepage = meta.get("homepage")
    return {"stars": meta.get("stars"), "forks": meta.get("forks"), "downloads": downloads,
            "editorial_home": homepage if is_editorial_home(homepage) else None,
            "source": meta.get("pushed_at")}


def _clears(value, floor: int) -> bool | None:
    return None if not isinstance(value, int) else value >= floor


def evidence_rev(ev: dict) -> str:
    """A short hash of only what is MEANINGFUL: whether stars / forks / downloads clear their
    floor, the editorial home, the source revision. A star more or less is not new evidence."""
    meaningful = {"stars": _clears(ev.get("stars"), STAR_FLOOR), "forks": _clears(ev.get("forks"), FORK_FLOOR),
                  "downloads": _clears(ev.get("downloads"), DOWNLOAD_FLOOR),
                  "editorial_home": ev.get("editorial_home"), "source": ev.get("source")}
    return hashlib.sha256(json.dumps(meaningful, sort_keys=True).encode()).hexdigest()[:12]


def holds(decision: dict, rev: str | None) -> bool:
    """True unless both revisions are known and differ: an unknown one (a PR that predates the
    marker, a stage that has no metadata) reads as unchanged until the decision expires."""
    known = (decision.get("review") or {}).get("evidence_rev")
    return known is None or rev is None or known == rev


def live_decision(led: dict, now: datetime, firmware_id: str | None = None, repo: str | None = None,
                  repo_id: int | None = None) -> dict | None:
    """The unexpired owner-review decision for this target, or None (a plain rejection is not one)."""
    rec = memory.lookup(led, firmware_id=firmware_id, repo=repo, repo_id=repo_id)
    if rec is None or rec.get("status") != "rejected" or not rec.get("review"):
        return None
    return None if memory.is_expired(rec, now) else rec


# --- the PR-body hand-off ----------------------------------------------------------------------

def _target(item: dict) -> dict:
    out = {k: item.get(k) for k in TARGET_KEYS}
    if item.get("evidence") is not None:
        out["evidence"] = item["evidence"]
    return out


def render_marker(items: list[dict]) -> str:
    """The hidden comment a review PR body carries: one target per review item."""
    payload = json.dumps([_target(it) for it in items], sort_keys=True).replace("-->", "--\\u003e")
    return f"<!-- {MARKER}: {payload} -->"           # a "-->" in a reason must not end the comment early


def parse_targets(body: str | None) -> list[dict]:
    """The targets a review PR raised: its marker, else (a PR older than the marker) the rendered
    `` - `owner/repo` (`id`) `` lines of its "Needs owner review" section. [] when neither."""
    m = _MARKER_RE.search(body or "")
    if m:
        try:
            items = json.loads(m.group(1))
        except json.JSONDecodeError:
            return []
        return [_target(it) for it in items if isinstance(it, dict) and (it.get("id") or it.get("repo"))] \
            if isinstance(items, list) else []
    out, section = [], False
    for line in (body or "").splitlines():
        if line.startswith("### "):
            section = line.startswith(_LEGACY_HEADER)
            continue
        hit = _LEGACY_LINE_RE.match(line) if section else None
        if hit:
            out.append({"id": hit.group(2), "repo": hit.group(1).lower(), "repo_id": None,
                        "evidence_rev": None, "reason": None})
    return out


# --- reconcile: GitHub's jr-review PRs -> the worktree ledger ------------------------------------

def list_review_prs(gh) -> list[dict] | None:
    """Every jr-review PR, open or not (one counted call), or None when unreadable."""
    p = gh("pr", "list", "--state", "all", "--label", REVIEW_LABEL, "--limit", str(REVIEW_PR_LIMIT),
           "--json", "number,state,body,createdAt,mergedAt")
    if getattr(p, "returncode", 1) != 0:
        return None
    try:
        prs = json.loads(getattr(p, "stdout", "") or "[]")
    except json.JSONDecodeError:
        return None
    return [pr for pr in prs if isinstance(pr, dict)] if isinstance(prs, list) else None


def _when(ts) -> datetime | None:
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def latest_raises(prs: list[dict]) -> dict:
    """{identity: (target, pr, created)} — the MOST RECENT PR that raised each target. Identity is
    GitHub's numeric repo_id, stable across renames; the name only when a raise carries none."""
    out: dict = {}
    for pr in prs:
        created = _when(pr.get("createdAt"))
        if created is None:
            continue
        for t in parse_targets(pr.get("body")):
            key = _identity(t)
            if key and (key not in out or created > out[key][2]):
                out[key] = (t, pr, created)
    return out


def _identity(target: dict):
    rid = target.get("repo_id")
    if rid is not None:
        try:
            return ("repo_id", int(rid))
        except (TypeError, ValueError):
            pass
    return (target.get("repo") or target.get("id") or "").lower()


def _newer_decision(rec: dict | None, pr_ref: str, created: datetime) -> bool:
    """True when the ledger already holds a decision taken AFTER this raise (another PR's)."""
    if not rec or (rec.get("review") or {}).get("pr_ref") == pr_ref:
        return False
    ts = _when(rec.get("timestamp"))
    return ts is not None and ts > created


def reconcile(gh, ledger_path, now: datetime) -> list[str] | None:
    """Write the decision of every target an OPEN or CLOSED-unmerged jr-review PR raised into the
    ledger at `ledger_path`. Skipped: a MERGED raise (main has it), an expired one (reconsidered),
    one a newer decision supersedes. Returns the ids written, or None when GitHub is unreadable."""
    prs = list_review_prs(gh)
    if prs is None:
        return None
    ttl = timedelta(days=memory.NO_BUILD_SIGNAL_DAYS)
    written = []
    for target, pr, created in latest_raises(prs).values():
        outcome = None if pr.get("mergedAt") else OUTCOMES.get(str(pr.get("state", "")).upper())
        if outcome is None or created + ttl <= now:
            continue
        led = memory.load(ledger_path)
        repo, rid = target.get("repo") or target.get("id"), target.get("repo_id")
        rec = memory.lookup(led, firmware_id=target.get("id"), repo=repo, repo_id=rid)
        fid = memory.canonical_id(led, target.get("id") or (rec or {}).get("id"), rid)
        rec = led["by_id"].get(fid)                      # the repo_id's record, never a shadow of it
        pr_ref = f"#{pr.get('number')}"
        if not fid or _newer_decision(rec, pr_ref, created):
            continue
        before = json.dumps((rec or {}), sort_keys=True)
        reason = target.get("reason") or f"{device_evidence.NEEDS_REVIEW_TARGET}: owner review raised in {pr_ref}"
        prior = (rec or {}).get("review") or {}
        rev = target.get("evidence_rev") or (prior.get("evidence_rev") if prior.get("pr_ref") == pr_ref else None)
        ev = target.get("evidence") or (prior.get("evidence") if prior.get("pr_ref") == pr_ref else None)
        memory.record_review_decision(target.get("id") or fid, repo, reason, repo_id=rid, evidence=ev,
                                      evidence_rev=rev, pr_ref=pr_ref, outcome=outcome, raised_at=created,
                                      path=ledger_path, now=now)
        after = memory.lookup(memory.load(ledger_path), firmware_id=fid, repo=repo, repo_id=rid)
        if json.dumps(after or {}, sort_keys=True) != before:
            written.append(fid)
    return written
