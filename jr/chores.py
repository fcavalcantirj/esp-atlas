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
HUMAN_LABEL = "needs-human"
DIGEST_HOUR = 12
PR_FIELDS = "number,headRefName,headRefOid,mergeStateStatus,isDraft,labels,baseRefName,isCrossRepository,updatedAt,createdAt"


def _labels(pr: dict) -> set:
    return {(l.get("name") if isinstance(l, dict) else l) for l in (pr.get("labels") or [])}


def _eligible(pr: dict) -> bool:
    return (not pr.get("isDraft") and not pr.get("isCrossRepository") and pr.get("baseRefName") == "main"
            and bool(pr.get("headRefOid")) and not str(pr.get("headRefName") or "").startswith(SKIP_PREFIXES))


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
        if dry_run:
            return {"status": "ok", "would": [f"record {v.check}" for v in wanted], "digest": None}
        recorded = []
        for v in wanted:
            rec = store.record(v, now)
            if rec:
                recorded.append(rec["id"])
        progress = store.pr_fix_progress({p["number"]: p.get("headRefOid") for p in prs},
                                         {v.check for v in wanted}, _closed(gh, store, {p["number"] for p in prs}), now)
        return {"status": "ok", "recorded": recorded, "resolved": progress["resolved"], "pushed": progress["pushed"],
                "stalled": progress["stalled"], "nudges": store.nudges(), "digest": daily(gh, store, prs, now)}
    except Exception as e:      # noqa: BLE001 — the tick must keep running whatever happens here
        return {"status": "unavailable", "why": f"{type(e).__name__}: {e}"[:300]}
