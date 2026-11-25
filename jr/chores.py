"""EspAtlas Jr — chores: the routine work a person used to do on open PRs (SPEC-jr-self-heal.md §1d).

Owner, 2026-11-18: "make jr automatically do chores. site must be self sufficient." That night 8 of 31 open
PRs conflicted with main and every agent BLOCK waited for a person. The hourly tick calls `run` after its
own work. Deterministic: no model here; the fixing is the heal delegate's, on the PR's own branch.

- A code PR (same repository, not draft, based on main, not a Jr tick or demand branch: those have their own
  refresh and retry) that GitHub reports DIRTY → a `conflict:#n` incident.
- A PR labelled `needs-human` whose newest agent-review verdict for its CURRENT head is BLOCK → a
  `review-fix:#n` incident carrying the findings. A BLOCK for an older head is stale: the agent re-judges first.
- Every live chore incident whose condition cleared, or whose PR closed, is resolved; a PR the fix led to
  merge resets the ack brake (ci_watch.Store.pr_fix_progress).
- Once a UTC day from DIGEST_HOUR, one line to the owner (`daily`): the last 24 h of merges by Jr vs by a
  person, what still needs a human, and the run of consecutive self-sufficient days. That line is the audit
  after the fact, and the only place "self-sufficient" may be claimed.
Incidents are recorded always; they reach the delegate only through `ci_watch.py claim --pr-fix` and the
`pr_fix_dispatch` switch. Never raises: a failure is `{"status": "unavailable"}`.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import agent_review
import ci_watch
import publish

SKIP_PREFIXES = ("jr/tick-", "jr/research-")   # review_refresh and the demand retry own those
CONTENT_PREFIXES = SKIP_PREFIXES                 # Jr's catalog PRs: a red check on one is healed on MAIN
HUMAN_LABEL = "needs-human"
DIGEST_HOUR = 12
PR_FIELDS = ("number,headRefName,headRefOid,mergeStateStatus,isDraft,labels,baseRefName,isCrossRepository,updatedAt,"
             "createdAt,statusCheckRollup")


# GitHub computes mergeability lazily: the first listing after main moves answers UNKNOWN for most PRs
# (2026-11-19, measured: 17 of 25 UNKNOWN, 12 s later 6 CONFLICTING). A listing with UNKNOWN in it is read again.
SLEEP = time.sleep
SETTLE_WAIT, SETTLE_TRIES = 10, 3
REQUIRED_LABELS = {"agent-pass": "0E8A16", "needs-human": "B60205", "review-fallback": "FBCA04", "jr-heal": "D93F0B"}


def list_settled(fetch, unknown, tries: int = SETTLE_TRIES, wait: int = SETTLE_WAIT):
    """`fetch()` -> a PR list or None; read again (after `wait` s) while `unknown(pr)` holds for any PR, at most
    `tries` listings in all. The last listing is returned as it is: a PR still unknown is simply not judged."""
    prs = fetch()
    for _ in range(max(tries, 1) - 1):
        if prs is None or not any(unknown(p) for p in prs):
            break
        SLEEP(wait)
        again = fetch()
        if again is None:
            break
        prs = again
    return prs


def ensure_labels(gh, store: ci_watch.Store, now: str) -> list[str]:
    """Once a UTC day: create every label the machine needs that the repository lacks (2026-11-19: four were
    missing and every `gh pr edit --add-label` would have raised). Best-effort; returns the names created."""
    day = now[:10]
    data = store._load()
    if data.get("labels_day") == day:
        return []
    have = ci_watch._json(gh, "label", "list", "--limit", "200", "--json", "name")
    if have is None:
        return []
    names = {str(l.get("name")) for l in have if isinstance(l, dict)}
    created = []
    for name, color in REQUIRED_LABELS.items():
        if name not in names and getattr(gh("label", "create", name, "--color", color), "returncode", 1) == 0:
            created.append(name)
    data = store._load()
    data["labels_day"] = day
    store._save(data)
    return created


def _labels(pr: dict) -> set:
    return {(l.get("name") if isinstance(l, dict) else l) for l in (pr.get("labels") or [])}


def _eligible(pr: dict) -> bool:
    return (not pr.get("isDraft") and not pr.get("isCrossRepository") and pr.get("baseRefName") == "main"
            and bool(pr.get("headRefOid")) and not str(pr.get("headRefName") or "").startswith(SKIP_PREFIXES))


def _red_required(pr: dict, required: list) -> list[tuple[str, str, str]]:
    """(check, run id, job id) of every REQUIRED check that FAILED at the PR's head. Cancelled/timed-out
    runs and non-required checks (sources-live, a cited site blinking) are never a chore."""
    out = []
    for c in pr.get("statusCheckRollup") or []:
        if c.get("name") in required and str(c.get("conclusion") or "").upper() == ci_watch.FAILURE:
            m = ci_watch._RUN_JOB.search(str(c.get("detailsUrl") or ""))
            if m:
                out.append((c["name"], m.group(1), m.group(2)))
    return out


def _main_green(gh, slug: str, check: str) -> bool:
    """main's newest run of `check` completed successfully. Unreadable or absent → False."""
    data = ci_watch._json(gh, "api", f"repos/{slug}/commits/main/check-runs?check_name={check}&per_page=20")
    runs = [r for r in (data or {}).get("check_runs") or [] if r.get("name") == check] if isinstance(data, dict) else []
    if not runs:
        return False
    newest = max(runs, key=lambda r: str(r.get("started_at") or ""))
    return newest.get("status") == "completed" and newest.get("conclusion") == "success"


def red_prs(gh, slug: str, prs: list, store: ci_watch.Store, dry_run: bool, now: str | None = None) -> dict:
    """A red required check on any open PR (2026-11-19: tick PR #1828 sat red; ci_watch only declares a tick
    break when the two NEWEST tick PRs fail alike). In order, once per PR and FAILURE (never per head: main
    moves hourly, so per-head memory looped rerun → update → rerun with no incident, review BLOCK of #1857):
    (1) rerun the failed jobs (a flake clears itself); (2) still red and behind main → merge main into it (the
    fix may be on main already: a heal PR, any PR); (3) still red → a Jr content PR is one `pr-red:` heal incident on main per failing
    test (the delegate fixes main's code or test, never the data; the PRs are evidence), a code PR is a
    `ci-fix:#n`, fixed in place. Returns {"reruns", "verdicts", "fingerprints", "update_branch"}."""
    out = {"reruns": [], "verdicts": [], "fingerprints": set(), "update_branch": []}
    candidates = [p for p in prs if not p.get("isDraft") and not p.get("isCrossRepository")
                  and p.get("baseRefName") == "main" and p.get("headRefOid")]
    if not any(p.get("statusCheckRollup") for p in candidates):
        return out
    required = ci_watch.required_checks(gh, slug) or []
    data = store._load() if not dry_run else {}
    seen = data.get("reruns") or {}
    updated = data.get("updated_branch") or {}
    # a PR whose fix the delegate is working on is never moved under it (its push must fast-forward)
    in_flight = {((r["context"].get("evidence") or {}).get("pr")) for r in (data.get("incidents") or {}).values()
                 if ci_watch.is_pr_fix(r) and r["state"] in ("dispatched", "pushed")}
    # a pr-red heal that MERGED earns the red PRs one more merge of main (its fix is on main now)
    healed = {r["fingerprint"] for r in (data.get("incidents") or {}).values()
              if str(r["context"].get("check") or "").startswith(ci_watch.PR_RED_CHECK) and r.get("merged")}
    groups: dict = {}
    for p in candidates:
        n, head, branch = p["number"], p["headRefOid"], p["headRefName"]
        for check, run_id, job_id in _red_required(p, required)[:1]:
            parsed = ci_watch.parse_job_log(ci_watch._job_log(gh, slug, job_id))
            content = branch.startswith(CONTENT_PREFIXES)
            fp = (ci_watch.fingerprint(check, parsed) or ci_watch.hashlib.sha256(f"pr-red\n{check}".encode()).hexdigest())
            if content:
                out["fingerprints"].add(fp)          # still a live break until the PR is green
            # the memory key is the failing NODE, not the fingerprint: an assertion line can carry a tmp path or a
            # uuid that changes every run, and a key that never matches loops forever (2nd review of #1857)
            key = f"{n}:{check}:{parsed.failed or parsed.error or '?'}"
            if key not in seen:
                out["reruns"].append((n, run_id))
                seen[key] = run_id
                continue
            ukey = key if key not in updated or fp not in healed else f"{key}:after-heal"
            if ukey not in updated and n not in in_flight and _behind_main(gh, slug, head):
                out["update_branch"].append((n, head))
                updated[ukey] = head
                continue
            # a fix that reached main through ANY PR (2026-11-25: #2084 fixed #2053's red test, no Jr heal merged,
            # #2053 stayed red and its incident was abandoned): once per PR, failure and UTC day, merge main in
            # again when main's same check is green there. Daily, so main moving hourly never loops it.
            gkey = f"{key}:main-green:{ci_watch._utc_day(now)}" if now else None
            if (gkey and gkey not in updated and n not in in_flight and _behind_main(gh, slug, head)
                    and _main_green(gh, slug, check)):
                out["update_branch"].append((n, head))
                updated[gkey] = head
                continue
            if content:
                g = groups.setdefault(fp, {"check": check, "parsed": parsed, "prs": []})
                g["prs"].append(n)
            elif _eligible(p):
                out["verdicts"].append(ci_watch.pr_fix_verdict("ci-fix", n, branch, head, {
                    "check": check, "failed": parsed.failed, "assertion": parsed.assertion,
                    "log_excerpt": (parsed.excerpt or "")[-4000:]}))
    for fp, g in groups.items():
        parsed = g["parsed"]
        out["verdicts"].append(ci_watch.Verdict(
            kind="incident", source="pr", check=f"{ci_watch.PR_RED_CHECK}#{g['prs'][0]}:{g['check']}", fingerprint=fp,
            failed=parsed.failed, assertion=parsed.assertion, error=parsed.error, log_excerpt=(parsed.excerpt or "")[-4000:],
            kind_detail="pr-red", evidence={"prs": sorted(g["prs"]), "check": g["check"]}))
    if not dry_run:
        data = store._load()
        data["reruns"] = dict(list(seen.items())[-300:])
        data["updated_branch"] = dict(list(updated.items())[-300:])
        store._save(data)
    return out


# --- canary retry ---------------------------------------------------------------------------------------
# A canary (scripts/demand_canary.py, scripts/tick_canary.py) runs only on a pull-request event. A Jr content
# PR it did not merge (capped today, a quoted page that did not answer, a guard fixed on main since) was never
# looked at again: these chores skip such branches and the tick refreshes only its own CONFLICTING tick PRs
# (2026-11-19: demand PR #1846, judged once on Nov 18). Each gets one more look per UTC day.
RETRY_LANES = {"jr/research-": ("demand_automerge", "demand-canary"), "jr/tick-": ("tick_automerge", "tick-canary")}
RETRY_PER_TICK = 2


def _ok(p) -> bool:
    return getattr(p, "returncode", 1) == 0


def canary_retry(gh, slug: str, prs: list, store: ci_watch.Store, now: str, dry_run: bool,
                 autonomy_path: Path = ci_watch.AUTONOMY_PATH) -> dict:
    """One more canary decision for an open Jr content PR, at most once per PR per UTC day and RETRY_PER_TICK
    per tick, oldest first; only for a lane whose switch in jr/autonomy.json is true. A demand PR behind main
    is merged with main (a new event: main's current guards and canary judge it); otherwise the failed jobs of
    its last run are rerun (the canary behind them follows), or the canary job alone. A tick PR is only ever
    rerun: jr/review_refresh.py owns its merges with main. Left alone: needs-human, a red REQUIRED check on a
    PR that is not a draft (red_prs' business; it never looks at drafts), checks still running, no run at all, a
    fork, another base, an AUTO-route tick PR, a PR whose fix the delegate is working on. The day's memory is
    written BEFORE each call (the tick's GitHub budget can end the run between two calls; review BLOCK of #1874),
    so a retry that was sent, refused or cut short is never sent twice in a day.
    Returns {"update_branch": [(n, head)], "rerun": [(n, run id)], "failed": [n]}."""
    out = {"update_branch": [], "rerun": [], "failed": []}
    try:
        flags = json.loads(Path(autonomy_path).read_text())
    except (OSError, ValueError):
        return out
    lanes = {prefix: job for prefix, (flag, job) in RETRY_LANES.items() if isinstance(flags, dict) and flags.get(flag) is True}
    data = store._load()
    seen, day = dict(data.get("canary_retry") or {}), ci_watch._utc_day(now)
    in_flight = {((r["context"].get("evidence") or {}).get("pr")) for r in (data.get("incidents") or {}).values()
                 if ci_watch.is_pr_fix(r) and r["state"] in ("dispatched", "pushed")}
    required = None
    for p in sorted(prs, key=lambda p: int(p.get("number") or 0)):
        if len(out["update_branch"]) + len(out["rerun"]) + len(out["failed"]) >= RETRY_PER_TICK:
            break
        n, head, branch = p.get("number"), p.get("headRefOid"), str(p.get("headRefName") or "")
        prefix = next((x for x in lanes if branch.startswith(x)), None)
        rollup = [c for c in p.get("statusCheckRollup") or [] if c.get("name")]          # check runs, not statuses
        if (prefix is None or not head or p.get("isCrossRepository") or p.get("baseRefName") != "main"
                or HUMAN_LABEL in _labels(p) or n in in_flight or seen.get(str(n)) == day or not rollup
                or any(str(c.get("status") or "COMPLETED").upper() != "COMPLETED" for c in rollup)):
            continue
        if prefix == "jr/tick-" and (p.get("isDraft") or "jr-review" not in _labels(p)):
            continue
        if required is None:
            required = ci_watch.required_checks(gh, slug) or []
        if _red_required(p, required) and not p.get("isDraft"):
            continue
        # the run that holds this lane's canary: a failure in another workflow's run (the agent review, a
        # deploy preview) is not what stands between the PR and its canary
        runs = {id(c): ci_watch._RUN_JOB.search(str(c.get("detailsUrl") or "")) for c in rollup}
        canary = next((runs[id(c)] for c in rollup if c.get("name") == lanes[prefix] and runs[id(c)]), None)
        if canary is None:
            continue
        canary_skipped = any(c.get("name") == lanes[prefix] and str(c.get("conclusion") or "").upper() == "SKIPPED"
                             for c in rollup)
        failed = [c for c in rollup if str(c.get("conclusion") or "").upper() == ci_watch.FAILURE
                  and runs[id(c)] and runs[id(c)].group(1) == canary.group(1)]
        if prefix == "jr/research-" and _behind_main(gh, slug, head):
            kind, call = "update_branch", ("api", "-X", "PUT", f"repos/{slug}/pulls/{n}/update-branch", "-f", f"expected_head_sha={head}")
        elif failed and canary_skipped:
            # a job the canary needs failed, so the canary never ran: rerunning the failed jobs runs it too.
            # When the canary DID run, a failure beside it (sources-live, a cited site blinking) is not in its
            # way, and `--failed` would rerun that job every day and never the canary (2nd review of #1874).
            kind, call = "rerun", ("run", "rerun", canary.group(1), "--failed")
        else:
            kind, call = "rerun", ("api", "-X", "POST", f"repos/{slug}/actions/jobs/{canary.group(2)}/rerun")
        if not dry_run:
            data = store._load()                       # fresh each time: the other chores write this store too
            # only today's entries are kept: the store is saved with sorted keys, so trimming by position
            # dropped the LOWEST PR number, and a stuck old PR was retried every tick (2nd review of #1874)
            today = {k: v for k, v in (data.get("canary_retry") or {}).items() if v == day}
            data["canary_retry"] = {**today, str(n): day}
            store._save(data)
        if dry_run or _ok(gh(*call)):
            out[kind].append((n, head) if kind == "update_branch" else (n, canary.group(1)))
        else:
            out["failed"].append(n)
    return out


GAVE_UP = ("Jr's fix agent has tried this PR {n} times and it is still not mergeable ({kind}). Jr stops here and "
           "does not try again for {days} days. Nobody is waited on: the author decides what happens next.")


def _give_up_on_pr(gh, rec: dict) -> None:
    """The third time the same PR needs the same kind of fix, Jr says so on the PR once and moves on. A PR Jr
    opened itself (a heal) is closed with that comment; a person's PR stays open for its author."""
    ev = rec["context"].get("evidence") or {}
    n, branch = ev.get("pr"), str(ev.get("pr_branch") or "")
    if not n:
        return
    text = GAVE_UP.format(n=ci_watch.MAX_PER_FINGERPRINT, kind=rec["context"].get("kind_detail") or "fix",
                          days=ci_watch.ABANDON_DAYS)
    if branch.startswith(ci_watch.HEAL_BRANCH):
        gh("pr", "close", str(n), "--comment", text)
    else:
        gh("pr", "comment", str(n), "--body", text)


# --- Jr's own tick PRs never wait for a person ----------------------------------------------------------------
# A review-routed tick PR merges by itself when scripts/receipt_guard.py can vouch for every recipe it adds
# (the tick canary, one a day). One the guard cannot vouch for used to sit open until a person read it
# (2026-11-19: four of them, 25 to 38 hours old). After EXPIRE_HOURS Jr asks the same guard once more and, when
# it still says no, closes the PR with the reasons. A tick PR closed unmerged is the existing 30-day veto of what
# it proposed (jr/pending_prs.py), so Jr does not propose the same unverifiable thing every hour. An eligible
# PR is never closed here: it only waits for the canary's daily slot. An unreadable upstream closes nothing.
REPO = Path(__file__).resolve().parent.parent
EXPIRE_HOURS, EXPIRE_PER_TICK = 72, 2
EXPIRED = ("Jr closes this tick PR after {hours} h: the evidence check cannot vouch for everything it adds, so "
           "nothing here may merge without a person, and Jr does not wait for one.\n\n{why}\n\n"
           "Nothing is lost for good: a tick PR closed unmerged is not proposed again for 30 days, and it comes "
           "back by itself when the upstream's evidence changes. A person who has verified it can reopen and merge it.")


def _fetch_branch(branch: str) -> None:
    import subprocess
    for ref in ("main", branch):
        p = subprocess.run(["git", "-C", str(REPO), "fetch", "-q", "origin", f"+refs/heads/{ref}:refs/remotes/origin/{ref}"],
                           capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            raise RuntimeError(f"git fetch {ref}: {p.stderr.strip()[:200]}")


def _guard(repo, *, base, head, branch):
    import sys
    sys.path.insert(0, str(REPO / "scripts"))
    import receipt_guard
    return receipt_guard.check(repo, base=base, head=head, branch=branch)


def expire_tick_prs(gh, prs: list, now: str, dry_run: bool, guard=None, fetch=None) -> dict:
    """Close the review-routed tick PRs older than EXPIRE_HOURS that the receipt guard still cannot vouch for:
    at most EXPIRE_PER_TICK a tick, oldest first. {"closed", "kept" (eligible), "unreadable"}."""
    guard, fetch = guard or _guard, fetch or _fetch_branch
    out = {"closed": [], "kept": [], "unreadable": []}
    old = sorted((p for p in prs if str(p.get("headRefName") or "").startswith(ci_watch.TICK_BRANCH)
                  and "jr-review" in _labels(p) and not p.get("isDraft") and not p.get("isCrossRepository")
                  and p.get("baseRefName") == "main" and _hours_since(p.get("createdAt"), now) >= EXPIRE_HOURS),
                 key=lambda p: (str(p.get("createdAt") or ""), p["number"]))
    for p in old[:EXPIRE_PER_TICK]:
        n, branch = p["number"], p["headRefName"]
        try:
            fetch(branch)
            problems, _ = guard(REPO, base="origin/main", head=f"origin/{branch}", branch=branch)
        except Exception:  # noqa: BLE001 — git or an upstream unreadable: never close on a guess
            out["unreadable"].append(n)
            continue
        if not problems:
            out["kept"].append(n)
            continue
        if not dry_run:
            why = "\n".join(f"- {x}" for x in problems[:8])
            gh("pr", "close", str(n), "--comment", EXPIRED.format(hours=EXPIRE_HOURS, why=why))
        out["closed"].append(n)
    return out


def review_lane_warning(now: str, state_path: Path | None = None) -> str | None:
    """One line for the tick when the backup reviewer was asked today and answered nothing (the runner's
    reviewer keeps that in its own state file on the same machine). Silence used to be the only sign."""
    try:
        state = agent_review.load_state(state_path or agent_review.DEFAULT_STATE)
    except Exception:  # noqa: BLE001
        return None
    empty = state.get("fallback_empty") or {}
    if empty.get("day") != ci_watch._utc_day(now) or not empty.get("prs"):
        return None
    prs = ", ".join(f"#{n}" for n in empty["prs"][:5])
    return (f"the backup reviewer was asked and gave NO verdict today ({prs}): the subscription lane is down "
            "and the API lane is not answering (check the API account's credit and the agent-review runs)")


def _behind_main(gh, slug: str, head: str) -> bool:
    """main has commits the PR head lacks (compare head...main: ahead_by > 0). Unreadable → False: never
    merge into a PR on a guess."""
    cmp = ci_watch._json(gh, "api", f"repos/{slug}/compare/{head}...main")
    return isinstance(cmp, dict) and int(cmp.get("ahead_by") or 0) > 0


def _comments(gh, slug: str, number: int) -> list:
    return ci_watch._json(gh, "api", f"repos/{slug}/issues/{number}/comments", "--paginate") or []


def plan(gh, slug: str, prs: list) -> list[ci_watch.Verdict]:
    """The chore incidents the open PRs call for now."""
    out = []
    for pr in prs:
        if not _eligible(pr):
            continue
        n, branch, head = pr["number"], pr["headRefName"], pr["headRefOid"]
        if pr.get("mergeStateStatus") == "DIRTY":
            out.append(ci_watch.pr_fix_verdict("conflict", n, branch, head))
        if HUMAN_LABEL in _labels(pr):
            v = agent_review.verdict_for_head(_comments(gh, slug, n), head)
            if v and v["verdict"] == "BLOCK":
                out.append(ci_watch.pr_fix_verdict("review-fix", n, branch, head,
                                                   {"findings": list(v.get("findings") or [])}))
    return out


def _closed(gh, store: ci_watch.Store, open_numbers: set) -> dict:
    """{number: MERGED|CLOSED} for the PRs behind live chore incidents that are no longer open."""
    out = {}
    for rec in store._load()["incidents"].values():
        n = ((rec["context"].get("evidence") or {}).get("pr"))
        if not ci_watch.is_pr_fix(rec) or rec["state"] not in ci_watch.LIVE or n in open_numbers or n in out:
            continue
        st = (ci_watch._json(gh, "pr", "view", str(n), "--json", "state") or {}).get("state")
        if st in ("MERGED", "CLOSED"):
            out[n] = st
    return out


def _hours_since(stamp: str | None, now: str) -> float:
    return ci_watch._hours(str(stamp or "").replace("Z", "+00:00") or None, now)


SELF_SUFFICIENT_DAYS = 7
# The catalog's daily size, one row a day from the tick (jr/data_snapshot.py, SPEC-data-trend.md).
TREND = REPO / "docs" / "telemetry" / "data-trend.jsonl"
GROWTH_COUNTS = ("firmware_count", "recipe_count", "boards_with_firmware", "boards_zero_firmware")
SCOREBOARD_KEEP = 60


JR_BRANCHES = (ci_watch.TICK_BRANCH, "jr/research-", ci_watch.HEAL_BRANCH)


def _jr_authored(branch) -> bool:
    """A PR Jr itself opened: a tick, a demand work item, a heal. Everything else is a person's."""
    return str(branch or "").startswith(JR_BRANCHES)


def _machine(login: str | None) -> bool:
    """A merge Jr or a workflow made (a canary's `gh pr merge --auto` shows its token's account)."""
    login = str(login or "")
    return login == publish.JR_LOGIN or login.endswith("[bot]") or login.startswith("app/")


def catalog_growth(day: str, path: Path | None = None) -> tuple[int | None, str]:
    """(growth, span) of the catalog between the trend row of `day` and the newest row before it: firmware,
    recipes, boards (with and without firmware) and filled board fields (`board_fields[*].count`), so a new
    record, a new recipe or a backfilled field all count. (None, why) when the file cannot be read, has no row
    for `day`, or has nothing before it. The newest row per date wins (a re-run appends)."""
    try:
        lines = (path or TREND).read_text(encoding="utf-8").splitlines()
        rows = {}
        for line in lines:
            if line.strip():
                row = json.loads(line)
                if isinstance(row, dict) and row.get("date"):
                    rows[str(row["date"])] = row
    except (OSError, ValueError) as e:
        return None, f"catalog growth unreadable ({e.__class__.__name__})"
    if day not in rows:
        return None, f"catalog growth unknown: no trend row for {day}"
    before = sorted(d for d in rows if d < day)
    if not before:
        return None, "catalog growth unknown: fewer than two trend rows"

    def size(row: dict) -> int:
        fields = row.get("board_fields") or {}
        return (sum(int(row.get(k) or 0) for k in GROWTH_COUNTS)
                + sum(int((v or {}).get("count") or 0) for v in fields.values() if isinstance(v, dict)))
    return size(rows[day]) - size(rows[before[-1]]), f"{before[-1]}→{day}"


def daily(gh, store: ci_watch.Store, prs: list, now: str) -> str | None:
    """Once a UTC day from DIGEST_HOUR: the owner's audit and the self-sufficiency scoreboard in one line.
    The scoreboard measures JR, not people: a day is self-sufficient when no person had to merge one of Jr's
    own PRs (`jr/tick-*`, `jr/research-*`, `jr/heal-*`) in the last 24 h, none of Jr's own PRs carries
    `needs-human`, no heal incident is stuck (needs_human, stalled, halted), AND the catalog grew since the day
    before (`catalog_growth`: 2026-11-21, a day of 36 bookkeeping merges and nothing added is not Jr doing its
    job; unreadable growth proves nothing, so it is not self-sufficient either). People
    merging and holding their OWN PRs is ordinary work: counted and shown, never a broken day (2026-11-19:
    the first line read 0/7 for a person's 18 infrastructure merges and 6 PRs blocked by review; under that
    rule the count could never reach 7 while anybody worked here). Merges unreadable → not proven → not
    self-sufficient. The consecutive count is kept in the store; SELF_SUFFICIENT_DAYS in a row is the claim
    (SPEC-jr-self-heal.md §1d) and nothing less is."""
    when = datetime.fromisoformat(now)
    data = store._load()
    day = when.strftime("%Y-%m-%d")
    if when.hour < DIGEST_HOUR or data.get("digest_day") == day:
        return None
    since = (when - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    merged = ci_watch._json(gh, "pr", "list", "--state", "merged", "--limit", "200", "--search", f"merged:>={since}",
                            "--json", "number,headRefName,mergedBy")
    mine = [p for p in prs if _jr_authored(p.get("headRefName"))]
    theirs = [p for p in prs if not _jr_authored(p.get("headRefName")) and not p.get("isDraft")]
    waiting = [f"#{p['number']} needs-human {_hours_since(p.get('updatedAt'), now):.0f} h" for p in mine
               if HUMAN_LABEL in _labels(p)]
    # Jr's own open PRs without that label are Jr's QUEUE, not a wait on a person: an eligible tick PR waits for
    # the canary's daily slot, one the guard cannot vouch for is closed by expire_tick_prs after EXPIRE_HOURS, a
    # heal PR waits for the agent review. Shown, never counted.
    queue = sorted((p for p in mine if not p.get("isDraft") and HUMAN_LABEL not in _labels(p)),
                   key=lambda p: str(p.get("createdAt") or ""))
    stuck = [f"{r['id']} {r['state']}" for r in data["incidents"].values() if r["state"] in ("needs_human", "stalled")]
    if data.get("halted"):
        stuck.append("self-heal paused until 00:00 UTC")
    if merged is None:
        by_jr = by_person = own = None
        ok = False
    else:
        by_jr = sum(1 for m in merged if _machine((m.get("mergedBy") or {}).get("login")))
        by_hand = [m for m in merged if not _machine((m.get("mergedBy") or {}).get("login"))]
        by_person = sum(1 for m in by_hand if _jr_authored(m.get("headRefName")))    # a person did Jr's job
        own = len(by_hand) - by_person                                               # people's own work
        ok = by_person == 0 and not waiting and not stuck
    grew, span = catalog_growth(day)
    ok = bool(ok) and grew is not None and grew > 0
    rows = [r for r in (data.get("scoreboard") or []) if r.get("day") != day]
    blocked = sum(1 for p in theirs if HUMAN_LABEL in _labels(p))
    rows.append({"day": day, "by_jr": by_jr, "by_person": by_person, "waiting": len(waiting), "stuck": len(stuck),
                 "ok": ok, "own_merged": own, "own_open": len(theirs), "grew": grew})
    rows = rows[-SCOREBOARD_KEEP:]
    streak = 0
    for r in reversed(rows):
        if not r.get("ok"):
            break
        streak += 1
    data.update(digest_day=day, scoreboard=rows)
    store._save(data)
    merges = ("merges unreadable" if merged is None
              else f"merged by Jr {by_jr} · Jr's PRs merged by a person {by_person}")
    held = (("Jr needs a person: " + ", ".join(waiting + stuck)) if (waiting or stuck)
            else "nothing of Jr's waits on a person")
    people = f"people's own: {own if own is not None else '?'} merged, {len(theirs)} open ({blocked} blocked by review)"
    jrq = ("Jr's own queue: empty" if not queue else
           f"Jr's own queue: {len(queue)} open (oldest #{queue[0]['number']}, "
           f"{_hours_since(queue[0].get('createdAt'), now):.0f} h)")
    verdict = (f"self-sufficient {min(streak, SELF_SUFFICIENT_DAYS)}/{SELF_SUFFICIENT_DAYS} days"
               + (" — SELF-SUFFICIENT" if streak >= SELF_SUFFICIENT_DAYS else ""))
    growth = (span if grew is None else f"catalog {grew:+d} ({span})" if grew else f"catalog did not grow ({span})")
    return f"🧹 Jr daily {day} (last 24 h): {merges} · {growth} · {held} · {jrq} · {people} · {verdict}"


def run(gh, store: ci_watch.Store, now: str, *, slug: str, dry_run: bool = False,
        autonomy_path: Path = ci_watch.AUTONOMY_PATH) -> dict:
    try:
        prs = list_settled(lambda: ci_watch._json(gh, "pr", "list", "--state", "open", "--limit", "200", "--json", PR_FIELDS),
                           lambda p: p.get("mergeStateStatus") == "UNKNOWN")
        if prs is None:
            return {"status": "unavailable", "why": "gh pr list failed"}
        wanted = plan(gh, slug, prs)
        reds = red_prs(gh, slug, prs, store, dry_run, now)
        wanted += reds["verdicts"]
        touched = {n for n, _ in reds["reruns"]} | {n for n, _ in reds["update_branch"]}
        rest = [p for p in prs if p.get("number") not in touched]
        if dry_run:
            retries = canary_retry(gh, slug, rest, store, now, True, autonomy_path=autonomy_path)
            expired = expire_tick_prs(gh, rest, now, True)
            return {"status": "ok", "would": [f"record {v.check}" for v in wanted]
                    + [f"rerun #{n} run {r}" for n, r in reds["reruns"]]
                    + [f"merge main into #{n}" for n, _ in reds["update_branch"]]
                    + [f"canary retry #{n} (merge main)" for n, _ in retries["update_branch"]]
                    + [f"canary retry #{n} (rerun {r})" for n, r in retries["rerun"]]
                    + [f"close tick PR #{n} ({EXPIRE_HOURS} h, not eligible)" for n in expired["closed"]], "digest": None}
        for _, run_id in reds["reruns"]:
            gh("run", "rerun", str(run_id), "--failed")
        for n, head in reds["update_branch"]:
            # REST, not `gh pr update-branch` (the runner's gh 2.46 has no such subcommand); expected_head_sha
            # makes GitHub refuse if the PR moved since we looked
            gh("api", "-X", "PUT", f"repos/{slug}/pulls/{n}/update-branch", "-f", f"expected_head_sha={head}")
        # after the actions red_prs already remembered: a budget that ends here must never cost them
        retries = canary_retry(gh, slug, rest, store, now, False, autonomy_path=autonomy_path)
        acted = {n for n, _ in retries["update_branch"] + retries["rerun"]}
        expired = expire_tick_prs(gh, [p for p in rest if p.get("number") not in acted], now, False)
        recorded = []
        for v in wanted:
            rec = store.record(v, now)
            if rec:
                recorded.append(rec["id"])
                if rec["state"] == "abandoned" and ci_watch.is_pr_fix(rec):
                    _give_up_on_pr(gh, rec)
        progress = store.pr_fix_progress({p["number"]: p.get("headRefOid") for p in prs},
                                         {v.check for v in wanted if ci_watch.is_pr_fix(v.check)},
                                         _closed(gh, store, {p["number"] for p in prs}), now)
        progress["resolved"] += store.resolve_pr_red(reds["fingerprints"], now)
        lane = review_lane_warning(now)
        return {"status": "ok", "recorded": recorded, "labels_created": ensure_labels(gh, store, now),
                "warnings": [lane] if lane else [],
                "reruns": [n for n, _ in reds["reruns"]],
                "canary_retries": [n for n, _ in retries["update_branch"] + retries["rerun"]],
                "canary_retry_failed": retries["failed"],
                "expired": expired["closed"], "expire_unreadable": expired["unreadable"],
                "updated": [n for n, _ in reds["update_branch"]], "resolved": progress["resolved"], "pushed": progress["pushed"],
                "stalled": progress["stalled"], "nudges": store.nudges(), "digest": daily(gh, store, prs, now)}
    except Exception as e:      # noqa: BLE001 — the tick must keep running whatever happens here
        return {"status": "unavailable", "why": f"{type(e).__name__}: {e}"[:300]}
