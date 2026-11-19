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

from datetime import datetime, timedelta

import agent_review
import ci_watch
import publish

SKIP_PREFIXES = ("jr/tick-", "jr/research-")   # review_refresh and the demand retry own those
CONTENT_PREFIXES = SKIP_PREFIXES                 # Jr's catalog PRs: a red check on one is healed on MAIN
HUMAN_LABEL = "needs-human"
DIGEST_HOUR = 12
PR_FIELDS = ("number,headRefName,headRefOid,mergeStateStatus,isDraft,labels,baseRefName,isCrossRepository,updatedAt,"
             "createdAt,statusCheckRollup")


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


def red_prs(gh, slug: str, prs: list, store: ci_watch.Store, dry_run: bool) -> dict:
    """A red required check on any open PR (2026-11-19: tick PR #1828 sat red; ci_watch only declares a tick
    break when the two NEWEST tick PRs fail alike). In order, once per head: (1) rerun the failed jobs (a flake
    clears itself); (2) still red and behind main → merge main into it (the fix may be on main already: a heal
    PR, any PR); (3) still red, up to date → a Jr content PR is one `pr-red:` heal incident on main per failing
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
    groups: dict = {}
    for p in candidates:
        n, head, branch = p["number"], p["headRefOid"], p["headRefName"]
        for check, run_id, job_id in _red_required(p, required)[:1]:
            key = f"{n}@{head}"
            if key not in seen:
                out["reruns"].append((n, run_id))
                seen[key] = run_id
                continue
            parsed = ci_watch.parse_job_log(ci_watch._job_log(gh, slug, job_id))
            content = branch.startswith(CONTENT_PREFIXES)
            fp = (ci_watch.fingerprint(check, parsed) or ci_watch.hashlib.sha256(f"pr-red\n{check}".encode()).hexdigest())
            if content:
                out["fingerprints"].add(fp)          # still a live break until the PR is green
            if updated.get(str(n)) != head and _behind_main(gh, slug, head):
                out["update_branch"].append((n, head))
                updated[str(n)] = head
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
        data["updated_branch"] = updated
        store._save(data)
    return out


def _behind_main(gh, slug: str, head: str) -> bool:
    """main has commits the PR head lacks (compare head...main: ahead_by > 0). Unreadable → False: never
    merge into a PR on a guess."""
    cmp = ci_watch._json(gh, "api", f"repos/{slug}/compare/{head}...main")
    return isinstance(cmp, dict) and int(cmp.get("ahead_by") or 0) > 0


def _comments(gh, slug: str, number: int) -> list:
    return ci_watch._json(gh, "api", f"repos/{slug}/issues/{number}/comments") or []


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
SCOREBOARD_KEEP = 60


def _machine(login: str | None) -> bool:
    """A merge Jr or a workflow made (a canary's `gh pr merge --auto` shows its token's account)."""
    login = str(login or "")
    return login == publish.JR_LOGIN or login.endswith("[bot]") or login.startswith("app/")


def daily(gh, store: ci_watch.Store, prs: list, now: str) -> str | None:
    """Once a UTC day from DIGEST_HOUR: the owner's audit and the self-sufficiency scoreboard in one line.
    A day is self-sufficient when nothing merged in the last 24 h was merged by a person, no PR waits on
    `needs-human`, and no heal incident is stuck (needs_human, stalled, halted). Merges unreadable → not
    proven → not self-sufficient. The consecutive count is kept in the store; SELF_SUFFICIENT_DAYS in a
    row is the claim (SPEC-jr-self-heal.md §1d) and nothing less is."""
    when = datetime.fromisoformat(now)
    data = store._load()
    day = when.strftime("%Y-%m-%d")
    if when.hour < DIGEST_HOUR or data.get("digest_day") == day:
        return None
    since = (when - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    merged = ci_watch._json(gh, "pr", "list", "--state", "merged", "--limit", "200", "--search", f"merged:>={since}",
                            "--json", "number,headRefName,mergedBy")
    waiting = [f"#{p['number']} needs-human {_hours_since(p.get('updatedAt'), now):.0f} h" for p in prs
               if HUMAN_LABEL in _labels(p)]
    # an open, non-draft PR still open a day after it was opened is waiting on someone too, label or not
    # (Nov 18: 25 code PRs waited on one reviewer with no label at all). createdAt, not updatedAt: CI runs and
    # label changes touch updatedAt without anyone deciding anything.
    idle = sorted((p for p in prs if not p.get("isDraft") and HUMAN_LABEL not in _labels(p)
                   and _hours_since(p.get("createdAt"), now) >= 24),
                  key=lambda p: str(p.get("createdAt") or ""))
    if idle:
        waiting.append(f"{len(idle)} PR(s) open ≥ 24 h (oldest #{idle[0]['number']}, "
                       f"{_hours_since(idle[0].get('createdAt'), now):.0f} h)")
    stuck = [f"{r['id']} {r['state']}" for r in data["incidents"].values() if r["state"] in ("needs_human", "stalled")]
    if data.get("halted"):
        stuck.append("self-heal halted (run `ci_watch.py ack`)")
    if merged is None:
        by_jr = by_person = None
        ok = False
    else:
        by_jr = sum(1 for m in merged if _machine((m.get("mergedBy") or {}).get("login")))
        by_person = len(merged) - by_jr
        ok = by_person == 0 and not waiting and not stuck
    rows = [r for r in (data.get("scoreboard") or []) if r.get("day") != day]
    rows.append({"day": day, "by_jr": by_jr, "by_person": by_person, "waiting": len(waiting), "stuck": len(stuck), "ok": ok})
    rows = rows[-SCOREBOARD_KEEP:]
    streak = 0
    for r in reversed(rows):
        if not r.get("ok"):
            break
        streak += 1
    data.update(digest_day=day, scoreboard=rows)
    store._save(data)
    merges = "merges unreadable" if merged is None else f"merged by Jr {by_jr} · by a person {by_person}"
    held = ("needs a human: " + ", ".join(waiting + stuck)) if (waiting or stuck) else "nothing waits on a human"
    verdict = (f"self-sufficient {min(streak, SELF_SUFFICIENT_DAYS)}/{SELF_SUFFICIENT_DAYS} days"
               + (" — SELF-SUFFICIENT" if streak >= SELF_SUFFICIENT_DAYS else ""))
    return f"🧹 Jr daily {day} (last 24 h): {merges} · {held} · {verdict}"


def run(gh, store: ci_watch.Store, now: str, *, slug: str, dry_run: bool = False) -> dict:
    try:
        prs = ci_watch._json(gh, "pr", "list", "--state", "open", "--limit", "200", "--json", PR_FIELDS)
        if prs is None:
            return {"status": "unavailable", "why": "gh pr list failed"}
        wanted = plan(gh, slug, prs)
        reds = red_prs(gh, slug, prs, store, dry_run)
        wanted += reds["verdicts"]
        if dry_run:
            return {"status": "ok", "would": [f"record {v.check}" for v in wanted]
                    + [f"rerun #{n} run {r}" for n, r in reds["reruns"]]
                    + [f"merge main into #{n}" for n, _ in reds["update_branch"]], "digest": None}
        for _, run_id in reds["reruns"]:
            gh("run", "rerun", str(run_id), "--failed")
        for n, head in reds["update_branch"]:
            # REST, not `gh pr update-branch` (the runner's gh 2.46 has no such subcommand); expected_head_sha
            # makes GitHub refuse if the PR moved since we looked
            gh("api", "-X", "PUT", f"repos/{slug}/pulls/{n}/update-branch", "-f", f"expected_head_sha={head}")
        recorded = []
        for v in wanted:
            rec = store.record(v, now)
            if rec:
                recorded.append(rec["id"])
        progress = store.pr_fix_progress({p["number"]: p.get("headRefOid") for p in prs},
                                         {v.check for v in wanted if ci_watch.is_pr_fix(v.check)},
                                         _closed(gh, store, {p["number"] for p in prs}), now)
        progress["resolved"] += store.resolve_pr_red(reds["fingerprints"], now)
        return {"status": "ok", "recorded": recorded, "reruns": [n for n, _ in reds["reruns"]],
                "updated": [n for n, _ in reds["update_branch"]], "resolved": progress["resolved"], "pushed": progress["pushed"],
                "stalled": progress["stalled"], "nudges": store.nudges(), "digest": daily(gh, store, prs, now)}
    except Exception as e:      # noqa: BLE001 — the tick must keep running whatever happens here
        return {"status": "unavailable", "why": f"{type(e).__name__}: {e}"[:300]}
