"""Runtime popularity collector: GitHub stars/forks as popularity.json on its own git branch.

Lane A, source-only. Reads the approved catalog (data/firmware/*/firmware.md) at one pinned
main revision, fetches counts with the shared GraphQL helpers (jr/popularity_graphql.py),
validates every record, and publishes ONE file, popularity.json (schema v1), to the branch
`runtime-popularity` with a parent-SHA compare-and-swap built from git plumbing. It never
writes main or the catalog, never touches PRs, never calls an LLM and keeps no database.

Identity is pinned: a repository whose GitHub id differs from the previous snapshot's, from a
quarantine carried over from an earlier run, or from the catalog's own github_repo_id is
quarantined and excluded until the pinned id returns. Quarantines and GitHub's rate-limit
cooldown persist as a JSON trailer on the branch commit (never as a second file); a run inside
the cooldown neither queries GitHub nor publishes. Counts may fall or be zero; there is
no admission floor. A source that fails or is rate-limited keeps its last-good record, with its
original github_as_of. A rival publish between observing the branch and pushing loses the race:
nothing is published and the exit code says so.

Usage: python jr/runtime_popularity.py [--dry-run --out PATH] [--repo PATH] [--remote origin]
Exit codes: 0 published / dry run written / cooling down, 1 unexpected error, 2 refused, 3 lost race.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml

import backfill_popularity
import popularity_graphql as gql
import stage_popularity_refresh as legacy
from budget import Budget

SCHEMA_VERSION = 1
BRANCH = "runtime-popularity"
FILENAME = "popularity.json"
DEFAULT_TIMEOUT_SECONDS = 180
DEFAULT_MAX_CALLS = 30
GIT_TIMEOUT_SECONDS = 60
PUBLISH_RESERVE_SECONDS = 10  # never start a push the time bound would cut off
COMMIT_IDENTITY = ("espatlas-jr", "hello@esp-atlas.com")
PROTECTED_BRANCHES = {"main", "master"}
# Collector state that must outlive one run (identity quarantines, GitHub's cooldown) rides as a
# JSON trailer on the branch commit's message: the published tree stays popularity.json alone.
STATE_TRAILER = "Runtime-Popularity-State: "
DEFAULT_LOCK = Path(tempfile.gettempdir()) / "jr-runtime-popularity.lock"
DEFAULT_DRY_RUN_OUT = Path(tempfile.gettempdir()) / "runtime-popularity.json"
REPO_ROOT = Path(__file__).resolve().parents[1]

TOP_KEYS = {"schema_version", "version", "catalog_revision", "published_at", "records"}
RECORD_KEYS = {"repository_url", "github_repo_id", "stars", "forks", "github_as_of"}
MAX_SAFE_INT = 2**53 - 1
CLOCK_SKEW = timedelta(minutes=5)
_FIRMWARE_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_FIRMWARE_PATH = re.compile(r"data/firmware/([^/]+)/firmware\.md")
_UTC_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|\+00:00)")
_REPO_URL = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?")


class Refused(RuntimeError):
    """Fail closed: nothing is published (bad input, unreadable remote, invalid snapshot, lock)."""


class LostRace(RuntimeError):
    """The branch moved after it was observed; the compare-and-swap refused the push."""


# --- schema v1 -----------------------------------------------------------------------------------

def canonical_repository(url) -> str | None:
    """'https://github.com/owner/repo' (lower-case, no .git) or None; the reader's canonical form."""
    match = _REPO_URL.fullmatch(url) if isinstance(url, str) else None
    if not match:
        return None
    owner, repo = match.group(1), match.group(2).removesuffix(".git")
    if owner in {".", ".."} or repo in {"", ".", ".."}:
        return None
    return f"https://github.com/{owner}/{repo}".lower()


def _utc(value) -> datetime | None:
    if not isinstance(value, str) or not _UTC_STAMP.fullmatch(value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:  # matches the shape but names no real instant, e.g. month 13
        return None


def _stamp(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _record_errors(fid, row, published: datetime | None, now: datetime) -> list[str]:
    if not isinstance(fid, str) or not _FIRMWARE_ID.fullmatch(fid):
        return [f"invalid firmware id {fid!r}"]
    if not isinstance(row, dict) or set(row) != RECORD_KEYS:
        return [f"{fid}: record must have exactly {sorted(RECORD_KEYS)}"]
    errors = []
    url = row["repository_url"]
    if canonical_repository(url) != url:
        errors.append(f"{fid}: repository_url is not a canonical GitHub URL")
    for key, minimum in (("github_repo_id", 1), ("stars", 0), ("forks", 0)):
        if type(row[key]) is not int or not minimum <= row[key] <= MAX_SAFE_INT:
            errors.append(f"{fid}: {key} must be an integer >= {minimum}")
    observed = _utc(row["github_as_of"])
    if observed is None or (published and observed > published) or observed > now + CLOCK_SKEW:
        errors.append(f"{fid}: github_as_of must be a UTC timestamp no later than published_at")
    return errors


def validate_snapshot(doc, *, now: datetime) -> list[str]:
    """Every reason `doc` is not a valid popularity.json v1; [] when it is."""
    if not isinstance(doc, dict):
        return ["snapshot is not an object"]
    errors = [] if set(doc) == TOP_KEYS else [f"snapshot must have exactly {sorted(TOP_KEYS)}"]
    if type(doc.get("schema_version")) is not int or doc.get("schema_version") != SCHEMA_VERSION:
        errors.append("schema_version must be 1")
    if not isinstance(doc.get("version"), str) or not 1 <= len(doc["version"]) <= 200:
        errors.append("version must be a 1-200 character string")
    if not isinstance(doc.get("catalog_revision"), str) or not re.fullmatch(r"[0-9a-f]{40}", doc["catalog_revision"]):
        errors.append("catalog_revision must be a 40-character commit SHA")
    published = _utc(doc.get("published_at"))
    if published is None or published > now + CLOCK_SKEW:
        errors.append("published_at must be a UTC timestamp, not in the future")
    records = doc.get("records")
    if not isinstance(records, dict):
        return errors + ["records must be an object"]
    for fid, row in records.items():
        errors += _record_errors(fid, row, published, now)
    return errors


def build_snapshot(catalog_revision: str, records: dict, now: datetime) -> dict:
    body = json.dumps({"catalog_revision": catalog_revision, "records": records}, sort_keys=True)
    return {"schema_version": SCHEMA_VERSION,
            "version": "sha256:" + hashlib.sha256(body.encode()).hexdigest(),
            "catalog_revision": catalog_revision, "published_at": _stamp(now),
            "records": {fid: records[fid] for fid in sorted(records)}}


# --- git -----------------------------------------------------------------------------------------

def make_git(repo: Path, *, budget: Budget | None = None):
    """A `git -C repo` runner; each call is bounded by the run's remaining time when given one."""
    def git(*args: str, input: str | None = None) -> subprocess.CompletedProcess:
        remaining = budget.remaining_seconds() if budget else GIT_TIMEOUT_SECONDS
        if remaining <= 0:
            return subprocess.CompletedProcess(args, 124, "", "time budget exhausted")
        try:
            return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                                  input=input, timeout=min(remaining, GIT_TIMEOUT_SECONDS),
                                  env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, 124, "", "git timed out")
    return git


def _out(git, *args: str, input: str | None = None, what: str) -> str:
    p = git(*args, input=input)
    if p.returncode != 0:
        raise Refused(f"{what} failed: {(p.stderr or '').strip()[:200]}")
    return p.stdout.strip()


# --- catalog -------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Entry:
    firmware_id: str
    repo: str              # lower-case "owner/name", the GraphQL lookup key
    repository_url: str    # canonical_repository() form
    catalog_id: int | None  # popularity.github_repo_id recorded in the catalog, if any


def _entry(fid: str, text: str) -> Entry | str:
    """An Entry for one firmware.md, or the exclusion reason."""
    try:
        fm, _ = backfill_popularity._split(text)
    except (ValueError, yaml.YAMLError):
        return "excluded_invalid_record"
    if not isinstance(fm, dict) or not _FIRMWARE_ID.fullmatch(fid):
        return "excluded_invalid_record"
    pair = backfill_popularity.repo_owner_and_name(fm.get("url") if isinstance(fm.get("url"), str) else "")
    url = canonical_repository("https://github.com/" + "/".join(pair)) if pair else None
    if url is None:
        return "excluded_invalid_url"
    repo = url.removeprefix("https://github.com/")
    if (fid, repo) in legacy.QUARANTINED:
        return "excluded_wrong_source"
    pop = fm.get("popularity") if isinstance(fm.get("popularity"), dict) else {}
    catalog_id = pop.get("github_repo_id")
    if catalog_id is not None and (type(catalog_id) is not int or catalog_id <= 0):
        return "excluded_invalid_record"
    return Entry(fid, repo, url, catalog_id)


def read_catalog(git, ref: str) -> tuple[str, list[Entry], dict[str, str]]:
    """(pinned revision, entries, {firmware_id: exclusion reason}) read from git objects at `ref`."""
    revision = _out(git, "rev-parse", "--verify", "-q", f"{ref}^{{commit}}", what=f"resolving {ref}")
    listing = _out(git, "ls-tree", "-r", "--name-only", revision, "--", "data/firmware", what="listing catalog")
    entries, excluded = [], {}
    for path in sorted(listing.splitlines()):
        match = _FIRMWARE_PATH.fullmatch(path)
        if not match:
            continue
        found = _entry(match.group(1), _out(git, "show", f"{revision}:{path}", what=f"reading {path}"))
        if isinstance(found, Entry):
            entries.append(found)
        else:
            excluded[match.group(1)] = found
    return revision, entries, excluded


# --- previous snapshot ---------------------------------------------------------------------------

def observe_branch(git, remote: str, branch: str, *, now: datetime | None = None):
    """(parent SHA, previous snapshot) of the published branch, or (None, None) when absent.

    The parent is what the compare-and-swap will expect. An unreadable remote or an invalid
    previous snapshot is refused: last-good records and identity pins come from it."""
    ref = f"refs/heads/{branch}"
    p = git("ls-remote", "--exit-code", remote, ref)
    if p.returncode == 2:
        return None, None
    if p.returncode != 0 or not p.stdout.strip():
        raise Refused(f"cannot read {remote} {ref}: {(p.stderr or '').strip()[:200]}")
    parent = p.stdout.split()[0]
    _out(git, "fetch", "--no-tags", "--no-write-fetch-head", remote, ref, what=f"fetching {ref}")
    _out(git, "cat-file", "-e", f"{parent}^{{commit}}", what="locating observed parent")
    text = _out(git, "show", f"{parent}:{FILENAME}", what=f"reading previous {FILENAME}")
    try:
        previous = json.loads(text)
    except ValueError:
        raise Refused(f"previous {FILENAME} at {parent[:12]} is not JSON") from None
    errors = validate_snapshot(previous, now=now or datetime.now(timezone.utc))
    if errors:
        raise Refused(f"previous {FILENAME} at {parent[:12]} is invalid: {errors[0]}")
    return parent, previous


# --- collection ----------------------------------------------------------------------------------

@dataclass
class Collection:
    records: dict = field(default_factory=dict)
    fresh: list = field(default_factory=list)
    kept_last_good: list = field(default_factory=list)
    excluded: dict = field(default_factory=dict)
    quarantined: dict = field(default_factory=dict)
    cooldown_until: str | None = None


def _fetch(repos: list[str], *, gh, budget: Budget, now: datetime):
    """({repo: validated stats}, {repo: failure reason}, cooldown or None): popularity_full's
    bounded loop, including where it derives a cooldown from GitHub's rate-limit replies."""
    stats: dict[str, dict] = {}
    failed = {repo: "unattempted" for repo in repos}

    def mark(subset, reason):
        failed.update({repo: reason for repo in subset})

    if not repos:
        return stats, failed, None
    if budget.remaining_calls() < 1 or budget.remaining_seconds() < gql.MIN_REMAINING_SECONDS:
        mark(repos, "unattempted_budget")
        return stats, failed, None
    ctx = SimpleNamespace(gh=budget.wrap(gh, "graphql"))
    cost = SimpleNamespace(graphql_cost_spent=0, graphql_cost_unknown_requests=0)
    probe, headers, status = gql._call(ctx, "query { rateLimit { cost remaining resetAt } }")
    quota = gql._quota(probe, headers)
    gql._charge_cost(cost, quota)
    if gql._limited(probe, status):
        mark(repos, "unattempted_rate_limit")
        return stats, failed, gql._cooldown_until(now, headers, quota)
    if not isinstance(quota, dict) or type(quota.get("remaining")) is not int:
        mark(repos, "unattempted_quota_unknown")
        return stats, failed, None
    if quota["remaining"] - gql._next_batch_cost_bound(repos[:gql.BATCH_SIZE]) < gql.MIN_GRAPHQL_POINTS:
        mark(repos, "unattempted_rate_limit")
        return stats, failed, gql._cooldown_until(now, headers, quota)
    for start in range(0, len(repos), gql.BATCH_SIZE):
        batch = repos[start:start + gql.BATCH_SIZE]
        if budget.remaining_calls() < 1 or budget.remaining_seconds() < gql.MIN_REMAINING_SECONDS:
            mark(repos[start:], "unattempted_budget")
            break
        if quota["remaining"] - gql._next_batch_cost_bound(batch) < gql.MIN_GRAPHQL_POINTS:
            mark(repos[start:], "unattempted_rate_limit")
            return stats, failed, gql._cooldown_until(now, {}, quota)
        doc, headers, status = gql._call(ctx, gql._query(batch))
        next_quota = gql._quota(doc, headers)
        gql._charge_cost(cost, next_quota)
        limited = gql._limited(doc, status)
        if doc is None or not isinstance(doc.get("data"), dict):
            mark(batch, "attempted_rate_limited" if limited else "attempted_query_failure")
            mark(repos[start + len(batch):], "unattempted_rate_limit" if limited else "unattempted_query_failure")
            return stats, failed, gql._cooldown_until(now, headers, quota) if limited else None
        error_aliases = {path[0] for error in doc.get("errors") or [] if isinstance(error, dict)
                         for path in [error.get("path")] if isinstance(path, list) and path
                         and isinstance(path[0], str)}
        for index, repo in enumerate(batch):
            found = gql._stats(doc["data"].get(f"r{index}"), repo, None)
            if found is None:
                failed[repo] = ("attempted_graphql_error" if f"r{index}" in error_aliases
                                else "attempted_invalid_identity_or_counts")
            else:
                stats[repo] = found
                del failed[repo]
        quota = next_quota if isinstance(next_quota, dict) and type(next_quota.get("remaining")) is int else None
        if limited or quota is None:
            mark(repos[start + len(batch):], "unattempted_rate_limit" if limited else "unattempted_quota_unknown")
            return stats, failed, gql._cooldown_until(now, headers, quota) if limited else None
    return stats, failed, None


def _same_source(row: dict | None, entry: Entry) -> dict | None:
    """`row` when it describes this entry's repository; history of another source is no pin."""
    return row if row and row.get("repository_url") == entry.repository_url else None


def collect(entries: list[Entry], previous_records: dict, *, gh, budget: Budget, now: datetime,
            quarantine: dict | None = None) -> Collection:
    """Fresh validated records, last-good fallbacks, exclusions and identity quarantines.

    Pins: the previous snapshot's id, a quarantine carried from earlier runs, the catalog's id.
    A quarantine lasts until GitHub reports the pinned id again or the catalog moves the source."""
    stats, failed, cooldown = _fetch(sorted({entry.repo for entry in entries}), gh=gh, budget=budget, now=now)
    result = Collection(cooldown_until=_stamp(cooldown) if cooldown else None)
    for entry in sorted(entries, key=lambda e: e.firmware_id):
        fid = entry.firmware_id
        previous = _same_source(previous_records.get(fid), entry)
        held = _same_source((quarantine or {}).get(fid), entry)
        pins = ([previous["github_repo_id"]] if previous else []) + ([held["pinned_repo_id"]] if held else []) \
            + ([entry.catalog_id] if entry.catalog_id is not None else [])
        found = stats.get(entry.repo)
        if found is not None:
            mismatch = next((pin for pin in pins if pin != found["id"]), None)
            if mismatch is not None:
                result.quarantined[fid] = {"repository_url": entry.repository_url,
                                           "pinned_repo_id": mismatch, "observed_repo_id": found["id"]}
                continue
            result.records[fid] = {"repository_url": entry.repository_url, "github_repo_id": found["id"],
                                   "stars": found["stars"], "forks": found["forks"],
                                   "github_as_of": _stamp(now)}
            result.fresh.append(fid)
        elif held:
            result.quarantined[fid] = {"repository_url": entry.repository_url,
                                       "pinned_repo_id": held["pinned_repo_id"], "observed_repo_id": None}
        elif previous and entry.catalog_id in (None, previous["github_repo_id"]):
            result.records[fid] = dict(previous)
            result.kept_last_good.append(fid)
        elif previous:
            result.excluded[fid] = "excluded_identity_mismatch"  # last-good contradicts the catalog id
        else:
            result.excluded[fid] = failed[entry.repo]
    return result


# --- collector state (commit trailer) ------------------------------------------------------------

def _empty_state() -> dict:
    return {"quarantine": {}, "cooldown_until": None}


def _state_is_valid(state) -> bool:
    if not isinstance(state, dict) or set(state) != {"quarantine", "cooldown_until"}:
        return False
    if state["cooldown_until"] is not None and _utc(state["cooldown_until"]) is None:
        return False
    held = state["quarantine"]
    return isinstance(held, dict) and all(
        isinstance(fid, str) and _FIRMWARE_ID.fullmatch(fid) and isinstance(pin, dict)
        and set(pin) == {"repository_url", "pinned_repo_id"}
        and canonical_repository(pin["repository_url"]) == pin["repository_url"]
        and type(pin["pinned_repo_id"]) is int and 0 < pin["pinned_repo_id"] <= MAX_SAFE_INT
        for fid, pin in held.items())


def read_state(git, commit: str) -> dict:
    """The collector state carried on `commit`'s message; empty when it has none, Refused when
    it is malformed (the identity pins in it must never silently vanish)."""
    message = _out(git, "log", "-1", "--format=%B", commit, what="reading collector state")
    lines = [line for line in message.splitlines() if line.startswith(STATE_TRAILER)]
    if not lines:
        return _empty_state()
    try:
        state = json.loads(lines[-1][len(STATE_TRAILER):])
    except ValueError:
        state = None
    if not _state_is_valid(state):
        raise Refused(f"collector state on {commit[:12]} is malformed")
    return state


def _next_state(result: Collection) -> dict:
    return {"quarantine": {fid: {"repository_url": row["repository_url"], "pinned_repo_id": row["pinned_repo_id"]}
                           for fid, row in sorted(result.quarantined.items())},
            "cooldown_until": result.cooldown_until}


# --- publish -------------------------------------------------------------------------------------

def _remote_tip(git, remote: str, ref: str) -> str | None:
    p = git("ls-remote", "--exit-code", remote, ref)
    if p.returncode == 2:
        return None
    if p.returncode != 0:
        raise Refused(f"push did not confirm and {remote} {ref} cannot be re-read: outcome unknown")
    return p.stdout.split()[0]


def publish(git, *, remote: str, branch: str, parent: str | None, snapshot: dict, now: datetime,
            state: dict | None = None) -> str:
    """Commit ONLY popularity.json on top of `parent` (orphan when None) and push it with a lease
    that expects exactly `parent`. Returns the new commit; LostRace when the branch moved.

    An accepted push is the outcome, whatever a rival does afterwards. A push that reports failure
    is settled by re-reading the branch: our commit there means it landed, `parent` there means
    it was refused, anything else means a rival won."""
    if branch in PROTECTED_BRANCHES:
        raise Refused(f"refusing to publish to {branch}")
    errors = validate_snapshot(snapshot, now=now)
    if errors:
        raise Refused(f"snapshot invalid: {errors[0]}")
    text = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    blob = _out(git, "hash-object", "-w", "--stdin", input=text, what="hash-object")
    tree = _out(git, "mktree", input=f"100644 blob {blob}\t{FILENAME}\n", what="mktree")
    subject = f"popularity: runtime snapshot {snapshot['published_at']} (catalog {snapshot['catalog_revision'][:12]})"
    trailer = STATE_TRAILER + json.dumps(state or _empty_state(), sort_keys=True, separators=(",", ":"))
    name, email = COMMIT_IDENTITY
    commit = _out(git, "-c", f"user.name={name}", "-c", f"user.email={email}", "commit-tree", tree,
                  *(["-p", parent] if parent else []), "-m", subject, "-m", trailer, what="commit-tree")
    ref = f"refs/heads/{branch}"
    push = git("push", "--porcelain", "--no-verify", f"--force-with-lease={ref}:{parent or ''}",
               remote, f"{commit}:{ref}")
    if push.returncode == 0:
        return commit
    tip = _remote_tip(git, remote, ref)
    if tip == commit:
        return commit
    if tip == parent:
        raise Refused(f"push failed: {(push.stderr or '').strip()[:200]}")
    raise LostRace(f"{ref} moved from {parent or 'absent'} to {tip or 'absent'}")


# --- run -----------------------------------------------------------------------------------------

@contextmanager
def exclusive_lock(path: Path):
    """This collector's own non-blocking flock; a held lock is Refused, never waited on."""
    try:
        fh = open(path, "a+")
    except OSError as e:
        raise Refused(f"cannot open lock {path}: {e}") from None
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refused(f"another collector run holds {path}") from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    finally:
        fh.close()


@dataclass
class Receipt:
    status: str
    exit_code: int
    catalog_revision: str | None = None
    parent: str | None = None
    commit: str | None = None
    published: int = 0
    kept_last_good: int = 0
    excluded: int = 0
    quarantined: int = 0
    quarantined_ids: list = field(default_factory=list)
    excluded_ids: list = field(default_factory=list)
    cooldown_until: str | None = None
    reason: str | None = None

    def line(self) -> str:
        parts = [f"status={self.status}", f"published={self.published}",
                 f"kept_last_good={self.kept_last_good}", f"excluded={self.excluded}",
                 f"quarantined={self.quarantined}", f"commit={self.commit or '-'}",
                 f"parent={self.parent or '-'}", f"catalog={self.catalog_revision or '-'}"]
        if self.quarantined_ids:
            parts.append("quarantined_ids=" + ",".join(self.quarantined_ids))
        if self.excluded_ids:
            parts.append("excluded_ids=" + ",".join(self.excluded_ids))
        if self.cooldown_until:
            parts.append(f"cooldown_until={self.cooldown_until}")
        if self.reason:
            parts.append(f"reason={json.dumps(self.reason)}")
        return "runtime-popularity: " + " ".join(parts)


def _write_local(out: Path, snapshot: dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name + ".tmp")
    tmp.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(out)


def run(*, git, gh, remote: str, branch: str, catalog_ref: str, budget: Budget, now: datetime,
        lock_path: Path, dry_run: bool = False, out: Path | None = None) -> Receipt:
    receipt = Receipt(status="refused", exit_code=2)
    try:
        with exclusive_lock(lock_path):
            revision, entries, catalog_excluded = read_catalog(git, catalog_ref)
            receipt.catalog_revision = revision
            parent, previous = observe_branch(git, remote, branch, now=now)
            receipt.parent = parent
            state = read_state(git, parent) if parent else _empty_state()
            cooldown = _utc(state["cooldown_until"])
            if cooldown and now < cooldown:
                receipt.status, receipt.exit_code, receipt.cooldown_until = "cooldown", 0, state["cooldown_until"]
                return receipt
            result = collect(entries, (previous or {}).get("records", {}), gh=gh, budget=budget, now=now,
                             quarantine=state["quarantine"])
            receipt.cooldown_until = result.cooldown_until
            receipt.published, receipt.kept_last_good = len(result.fresh), len(result.kept_last_good)
            receipt.excluded_ids = sorted({**catalog_excluded, **result.excluded})
            receipt.excluded = len(receipt.excluded_ids)
            receipt.quarantined, receipt.quarantined_ids = len(result.quarantined), sorted(result.quarantined)
            snapshot = build_snapshot(revision, result.records, now)
            errors = validate_snapshot(snapshot, now=now)
            if errors:
                raise Refused(f"snapshot invalid: {errors[0]}")
            if dry_run:
                _write_local(out or DEFAULT_DRY_RUN_OUT, snapshot)
                receipt.status, receipt.exit_code = "dry_run", 0
                return receipt
            if budget.remaining_seconds() < PUBLISH_RESERVE_SECONDS:
                raise Refused("too little time left in the run's bound to push safely")
            receipt.commit = publish(git, remote=remote, branch=branch, parent=parent, snapshot=snapshot,
                                     now=now, state=_next_state(result))
            receipt.status, receipt.exit_code = "published", 0
    except Refused as e:
        receipt.status, receipt.exit_code, receipt.reason = "refused", 2, str(e)
    except LostRace as e:
        receipt.status, receipt.exit_code, receipt.reason = "lost_race", 3, str(e)
    return receipt


def default_gh(*args: str, timeout: float = GIT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess:
    """The real transport: `gh api graphql …` only; any other gh command is refused outright."""
    if args[:2] != ("api", "graphql"):
        raise ValueError(f"runtime popularity only calls gh api graphql, not {args[:2]}")
    try:
        return subprocess.run(["gh", *args], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(args, 124, "", "gh timed out")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Publish runtime GitHub popularity to its own branch")
    ap.add_argument("--repo", type=Path, default=REPO_ROOT, help="checkout holding the catalog")
    ap.add_argument("--remote", default="origin")
    ap.add_argument("--branch", default=BRANCH)
    ap.add_argument("--catalog-ref", default="main")
    ap.add_argument("--dry-run", action="store_true", help="write JSON locally; never push")
    ap.add_argument("--out", type=Path, default=DEFAULT_DRY_RUN_OUT)
    ap.add_argument("--lock-path", type=Path, default=DEFAULT_LOCK)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    args = ap.parse_args(argv)
    budget = Budget(max_calls=args.max_calls, max_seconds=args.timeout)
    transport = default_gh
    try:
        receipt = run(git=make_git(args.repo, budget=budget),
                      gh=lambda *a: transport(*a, timeout=max(1.0, budget.remaining_seconds())),
                      remote=args.remote, branch=args.branch, catalog_ref=args.catalog_ref,
                      budget=budget, now=datetime.now(timezone.utc), lock_path=args.lock_path,
                      dry_run=args.dry_run, out=args.out)
    except Exception as e:  # noqa: BLE001 — the receipt line is the contract, even on a crash
        receipt = Receipt(status="error", exit_code=1, reason=f"{type(e).__name__}: {e}")
    print(receipt.line())
    return receipt.exit_code


if __name__ == "__main__":
    sys.exit(main())
