"""EspAtlas Jr — the agent review runner (jr/agent_review.py): subscription lane first, API lane as fallback.

The independent exact-head review of a code PR (docs/REVIEW-CONTRACT.md) is run by an agent. Owner,
2026-11-18: "subscription and api as fallback". So:

- **Primary lane** = the runner's coding delegate on the Claude subscription (the same binary and token the
  demand executor and the CI heal use). An hourly job on the runner calls `python3 jr/agent_review.py once
  --delegate <path> --checkout <dir> ...`: it lists the open code PRs that have no verdict for their current
  head, checks out the next one's head (see `candidates`) in a throwaway worktree, runs the delegate with
  `docs/ops/REVIEW-PROMPT.md` as the task (read-only: --no-ship --no-merge), reads the structured verdict the
  agent wrote to VERDICT_FILE, and posts it as ONE PR comment that starts with MARKER. The code canary
  (scripts/code_canary.py) reads that comment.
- **Fallback lane** = GitHub Actions running `claude -p` with the API key (never `anthropics/claude-code-action`:
  it is billed as Claude Code, which the plan's API credit does not cover) — used ONLY when the
  primary lane says it is DOWN (no subscription token, usage limit, auth failure): the runner then labels the
  PR `review-fallback`, which triggers the Actions review for that PR alone, at most FALLBACK_PER_DAY a UTC day.
  BUSY (another delegate run holds the lock) is not down: the PR simply waits for the next hour.

Every decision is a pure function over the data the fakes can hand it; the gh/git/delegate effects are
injected. The verdict comment is the one source of truth for both lanes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MARKER = "<!-- agent-review verdict -->"
FALLBACK_LABEL = "review-fallback"
FALLBACK_PER_DAY = 3
# a heal PR is code: the agent reviews it too (§1d, 2026-11-18). A demand snapshot is bookkeeping whose owner is the
# publisher's auto-merge: reviewing it handed it to the code canary's sweep, which disarmed it hourly (#2057,
# 2026-11-26), so it is skipped like a tick PR
SKIP_PREFIXES = ("jr/tick-", "jr/research-", "jr/demand-")
# Only the reviewers' own accounts carry a verdict: the Jr bot (subscription lane, the runner's GH_TOKEN) and
# GitHub Actions (API lane, the workflow token). The repo is public: a marker comment from anyone else — a
# PR's author included — is ignored, never a PASS (review BLOCK of #1809, 2026-11-19). A fork's workflow
# token is read-only and cannot comment.
TRUSTED_AUTHORS = ("espatlas-jr", "github-actions[bot]")
LANES = ("subscription", "api")
DOWN_PATTERNS = re.compile(r"CLAUDE_CODE_OAUTH_TOKEN|setup-token|usage limit|rate.?limit|too many requests|"
                           r"\b(401|403|429)\b|unauthori[sz]ed|authentication|credit balance|billing", re.I)
PROMPT_PATH = REPO / "docs" / "ops" / "REVIEW-PROMPT.md"
CONTRACT_PATH = REPO / "docs" / "REVIEW-CONTRACT.md"     # this script runs from a checkout of main: main's contract
DEFAULT_STATE = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "espatlas-jr" / "agent-review.json"


# --- the verdict comment (both lanes write it, the canary reads it) ---------------------------------------

def read_verdict(doc) -> dict | None:
    """The reviewer's structured verdict, or None when it is not one: {verdict PASS|BLOCK, head, findings, checked}."""
    if isinstance(doc, str):
        try:
            doc = json.loads(doc)
        except json.JSONDecodeError:
            return None
    if not isinstance(doc, dict) or doc.get("verdict") not in ("PASS", "BLOCK"):
        return None
    if not isinstance(doc.get("head"), str) or not re.fullmatch(r"[0-9a-f]{7,40}", doc["head"]):
        return None
    findings = doc.get("findings") if isinstance(doc.get("findings"), list) else []
    checked = doc.get("checked") if isinstance(doc.get("checked"), list) else []
    return {"verdict": doc["verdict"], "head": doc["head"].lower(), "findings": findings, "checked": checked}


def _defang(text: str) -> str:
    """No code fence can open inside the human part of a verdict comment."""
    return str(text).replace("```", "ʼʼʼ")


def render_comment(verdict: dict, lane: str) -> str:
    """ONE comment per verdict: the marker, a human line, the findings, and the JSON the canary parses."""
    v = read_verdict(verdict)
    if v is None or lane not in LANES:
        raise ValueError("not a verdict, or unknown lane")
    lines = [MARKER, f"**Agent review** ({lane} lane): **{v['verdict']}** at head `{v['head']}`."]
    if v["verdict"] == "BLOCK":
        lines.append("")
        for f in v["findings"]:
            if isinstance(f, dict):
                where = f"{f.get('file', '?')}" + (f":{f['line']}" if isinstance(f.get("line"), int) else "")
                lines.append(_defang(f"- `{where}` — {f.get('summary', '')}. Failure: {f.get('failure', '')}"))
        if not v["findings"]:
            lines.append("- (no finding listed: the reviewer could not complete the review; see `checked`)")
    if v["checked"]:
        lines += ["", "Checked: " + _defang(", ".join(str(c) for c in v["checked"])[:600])]
    # backticks escaped as \u0060 (valid JSON): no text inside the verdict can close or open a fence
    lines += ["", "```json", json.dumps({**v, "lane": lane}, sort_keys=True).replace("`", "\\u0060"), "```"]
    return "\n".join(lines)


def parse_comment(body: str) -> dict | None:
    """The verdict a MARKER comment carries (with its `lane`), or None for any other comment."""
    if not isinstance(body, str) or not body.lstrip().startswith(MARKER):
        return None
    # the LAST block is the verdict: findings rendered above it may quote anything (review BLOCK of #1809)
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", body, re.S)
    if not blocks:
        return None
    try:
        doc = json.loads(blocks[-1])
    except json.JSONDecodeError:
        return None
    v = read_verdict(doc)
    if v is None:
        return None
    v["lane"] = doc.get("lane") if doc.get("lane") in LANES else None
    return v


def _author(comment: dict) -> str:
    who = (comment or {}).get("user") or (comment or {}).get("author") or {}
    return str(who.get("login") or "") if isinstance(who, dict) else ""


def verdict_for_head(comments: list[dict], head: str) -> dict | None:
    """The newest verdict comment naming `head` written by a TRUSTED_AUTHORS account, or None."""
    found = None
    for c in comments:
        if _author(c) not in TRUSTED_AUTHORS:
            continue
        v = parse_comment((c or {}).get("body", ""))
        if v and v["head"] == head.lower():
            found = v
    return found


# --- what to review next --------------------------------------------------------------------------------

def candidates(prs: list[dict], comments_by_pr: dict) -> list[dict]:
    """Open, non-draft code PRs (not Jr's tick/research/heal branches) with no verdict for their current
    head and no fallback review pending. A PR that already has a trusted verdict for an EARLIER head comes
    first (its head moved: a fix is waiting to be judged, and it is the PR closest to merging), then the
    rest; inside each group, oldest update first."""
    out = []
    for pr in prs:
        branch = str(pr.get("headRefName") or "")
        # a fork's PR never reaches the runner: its own tests would run there with the bot's credentials
        # (review BLOCK of #1809, 2026-11-19); a human reviews forks
        if pr.get("isDraft") or pr.get("isCrossRepository") or branch.startswith(SKIP_PREFIXES) or not pr.get("headRefOid"):
            continue
        labels = {(l.get("name") if isinstance(l, dict) else l) for l in (pr.get("labels") or [])}
        if FALLBACK_LABEL in labels:
            continue                        # the API lane owns it until its verdict comment lands
        if verdict_for_head(comments_by_pr.get(pr["number"], []), pr["headRefOid"]):
            continue
        out.append(pr)
    def never_reviewed(p) -> bool:
        return not any(_author(c) in TRUSTED_AUTHORS and parse_comment((c or {}).get("body", ""))
                       for c in comments_by_pr.get(p["number"], []))
    out.sort(key=lambda p: (never_reviewed(p), str(p.get("updatedAt") or ""), p["number"]))
    return out


# --- the subscription lane's answer ----------------------------------------------------------------------

def lane_state(delegate_verdict) -> str:
    """ok | busy | down | failed from the delegate's own DelegateVerdict line (not the review verdict)."""
    if not isinstance(delegate_verdict, dict):
        return "failed"
    kind = str(delegate_verdict.get("verdict") or "")
    reason = str(delegate_verdict.get("reason") or "")
    if kind == "BUSY":
        return "busy"
    if kind in ("FAIL", "REFUSED", "ERROR", "DEFER", "REFUSED_FOREGROUND") and DOWN_PATTERNS.search(reason):
        return "down"
    if kind in ("PASS", "LAUNCHED", "OK", "DONE"):
        return "ok"
    return "failed"


# --- the fallback budget (runner-local state) -------------------------------------------------------------

def fallbacks_today(state: dict, day: str) -> int:
    return int((state.get("fallback") or {}).get(day) or 0)


def note_fallback(state: dict, day: str, pr: int, head: str = "") -> dict:
    fb = state.setdefault("fallback", {})
    fb[day] = int(fb.get(day) or 0) + 1
    state["fallback_prs"] = (state.get("fallback_prs") or [])[-200:] + [{"day": day, "pr": pr, "head": head}]
    return state


def asked_backup(state: dict, pr: int, head: str) -> bool:
    """The backup reviewer was already asked about this PR at this exact head."""
    return any(f.get("pr") == pr and f.get("head") == head for f in state.get("fallback_prs") or [])


def note_empty(state: dict, day: str, pr: int) -> dict:
    """A PR the backup reviewer was asked about is a candidate again with no verdict: the backup produced
    nothing (2026-11-19: "Credit balance is too low", four times, and nobody was told)."""
    prev = state.get("fallback_empty") or {}
    prs = sorted(set((prev.get("prs") if prev.get("day") == day else []) or []) | {pr})
    state["fallback_empty"] = {"day": day, "prs": prs}
    return state


WORKFLOW_REL = ".github/workflows/agent-review.yml"


def snapshot_is_stale(gh, slug: str, number: int) -> bool | None:
    """True when the PR's merge snapshot carries another review workflow than main does. A pull_request event
    (the fallback label) runs the workflow FROM that snapshot, and GitHub rebuilds snapshots hours late
    (2026-11-19: #1876's was six hours old, so its fallback review ran without a fix merged a minute before
    and posted "BLOCK: the reviewer could not read the diff"). None when either blob cannot be read."""
    try:
        merge = json.loads(gh("api", f"repos/{slug}/pulls/{number}") or "{}").get("merge_commit_sha")
        if not merge:
            return None
        blobs = [json.loads(gh("api", f"repos/{slug}/contents/{WORKFLOW_REL}?ref={ref}") or "{}").get("sha")
                 for ref in (merge, "main")]
        return None if not all(blobs) else blobs[0] != blobs[1]
    except Exception:  # noqa: BLE001 — unreadable: the caller labels as before
        return None


# --- one pass -------------------------------------------------------------------------------------------

def run_once(*, gh, git, delegate, slug: str, now: datetime, state: dict, dry_run: bool = False,
             fallback_per_day: int = FALLBACK_PER_DAY, prompt: str | None = None, out=None,
             review_python: str | None = None, contract: str | None = None) -> dict:
    """One hourly pass: review the next unreviewed code PR (`candidates` order) on the subscription lane; on a DOWN lane,
    hand that PR to the API lane (label) within the daily budget. Returns a small report dict.
    `gh(*args) -> str`, `git(*args) -> str`, `delegate(task, repo_path, env) -> (returncode, delegate_verdict_dict,
    review_verdict_text_or_None)`."""
    out = out or sys.stdout
    say = lambda s: print(s, file=out)  # noqa: E731
    day = now.astimezone(timezone.utc).date().isoformat()
    prs = json.loads(gh("pr", "list", "--repo", slug, "--state", "open", "--limit", "100",
                        "--json", "number,headRefOid,headRefName,isDraft,labels,updatedAt,isCrossRepository") or "[]")
    comments = {}
    for pr in prs:
        if not pr.get("isDraft") and not str(pr.get("headRefName") or "").startswith(SKIP_PREFIXES):
            comments[pr["number"]] = json.loads(gh("api", f"repos/{slug}/issues/{pr['number']}/comments",
                                                   "--paginate") or "[]")
    todo = candidates(prs, comments)
    if not todo:
        say("agent-review: nothing to review (every open code PR has a verdict for its head)")
        return {"outcome": "noop", "state": state}
    pr = todo[0]
    number, head = pr["number"], pr["headRefOid"].lower()
    say(f"agent-review: #{number} at {head[:8]} ({len(todo)} waiting)")
    if dry_run:
        return {"outcome": "dry_run", "pr": number, "head": head, "state": state}
    task = (prompt if prompt is not None else PROMPT_PATH.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="agent-review-") as tmp:
        # always a throwaway directory: nothing here ever deletes a configurable path (three reviews of #1866
        # found three ways a fixed, self-cleaned path could delete or stall; the feature was dropped)
        wt = Path(tmp) / "pr"
        verdict_file = Path(tmp) / "verdict.json"
        contract_file = Path(tmp) / "REVIEW-CONTRACT.md"
        contract_file.write_text(contract if contract is not None else CONTRACT_PATH.read_text(encoding="utf-8"),
                                 encoding="utf-8")
        git("fetch", "origin", f"pull/{number}/head")
        git("worktree", "add", "--detach", str(wt), "FETCH_HEAD")
        try:
            env = {"REPO_SLUG": slug, "PR_NUMBER": str(number), "HEAD": head, "VERDICT_FILE": str(verdict_file)}
            rc, dv, review_text = delegate(task + run_block(verdict_file, contract_file, review_python), str(wt), env)
        finally:
            git("worktree", "remove", "--force", str(wt))
    # the review the agent WROTE is the deliverable: a verdict for this exact head is posted whatever the
    # delegate's own code guard said about the read-only tree (2026-11-19, first real run: the guard went RED
    # because the PR's tests could not import the core package in the delegate's venv, and the review was lost)
    written = read_verdict(review_text)
    lane = "ok" if written is not None else lane_state(dv)
    if lane == "ok":
        v = written
        if v is None:
            say(f"agent-review: #{number}: the delegate finished but wrote no readable verdict; nothing posted")
            return {"outcome": "no_verdict", "pr": number, "head": head, "state": state}
        if v["head"] != head:
            say(f"agent-review: #{number}: verdict names {v['head'][:8]}, not {head[:8]}; nothing posted")
            return {"outcome": "stale_verdict", "pr": number, "head": head, "state": state}
        gh("pr", "comment", str(number), "--repo", slug, "--body", render_comment(v, "subscription"))
        say(f"agent-review: #{number} {v['verdict']} at {head[:8]} posted (subscription lane)")
        return {"outcome": "reviewed", "pr": number, "head": head, "verdict": v["verdict"], "state": state}
    if lane == "busy":
        say("agent-review: the delegate is busy (another run holds the lock); next hour")
        return {"outcome": "busy", "pr": number, "head": head, "state": state}
    if lane == "down":
        # A candidate we already sent to the backup at this head came back with no verdict (its label is gone,
        # or it would not be a candidate): say so, remember it for the tick's warning, and never ask the backup
        # twice for the same head. The next candidate not yet asked gets the label instead.
        if asked_backup(state, number, head):
            state = note_empty(state, day, number)
            fresh = next((p for p in todo if not asked_backup(state, p["number"], p["headRefOid"])), None)
            say(f"agent-review: subscription lane DOWN and the backup reviewer returned NO verdict for #{number} "
                f"at {head[:8]}; it is not asked again for this head")
            if fresh is None:
                return {"outcome": "fallback_empty", "pr": number, "head": head, "state": state}
            number, head = fresh["number"], fresh["headRefOid"]
        used = fallbacks_today(state, day)
        if used >= fallback_per_day:
            say(f"agent-review: subscription lane DOWN ({(dv or {}).get('reason', '')[:120]}); fallback budget "
                f"{used}/{fallback_per_day} spent today; #{number} waits")
            return {"outcome": "fallback_capped", "pr": number, "head": head, "state": state}
        # the label runs the workflow from the PR's merge snapshot: bring a stale one up to main first (a new
        # head, labelled on a later pass), at most once per PR per day; a refusal or an unreadable snapshot
        # is labelled as before
        refreshed = state.setdefault("fallback_refreshed", {})
        if refreshed.get(str(number)) != day and snapshot_is_stale(gh, slug, number):
            try:
                gh("api", "-X", "PUT", f"repos/{slug}/pulls/{number}/update-branch", "-f", f"expected_head_sha={head}")
            except Exception as e:  # noqa: BLE001 — a conflict, a moved head: label what is there
                say(f"agent-review: #{number}: stale snapshot, refresh refused ({str(e)[:100]}); labelling anyway")
            else:
                state["fallback_refreshed"] = {**{k: v for k, v in refreshed.items() if v == day}, str(number): day}
                say(f"agent-review: subscription lane DOWN; #{number}'s merge snapshot carries an older review "
                    f"workflow: merged main into it; it gets {FALLBACK_LABEL} on a later pass")
                return {"outcome": "fallback_refresh", "pr": number, "head": head, "state": state}
        gh("pr", "edit", str(number), "--repo", slug, "--add-label", FALLBACK_LABEL)
        state = note_fallback(state, day, number, head)
        say(f"agent-review: subscription lane DOWN ({(dv or {}).get('reason', '')[:120]}); #{number} labelled "
            f"{FALLBACK_LABEL} (API lane, {used + 1}/{fallback_per_day} today)")
        return {"outcome": "fallback_requested", "pr": number, "head": head, "state": state}
    say(f"agent-review: delegate failed for #{number}: {(dv or {}).get('verdict')} {(dv or {}).get('reason', '')[:160]}; next hour")
    return {"outcome": "failed", "pr": number, "head": head, "state": state}


# --- defaults for the runner -----------------------------------------------------------------------------

def default_gh(*args: str) -> str:
    p = subprocess.run(["gh", *args], capture_output=True, text=True, timeout=120)
    if p.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args[:3])}: {p.stderr.strip()[:200]}")
    return p.stdout


def make_git(checkout: Path):
    def git(*args: str) -> str:
        p = subprocess.run(["git", "-C", str(checkout), *args], capture_output=True, text=True, timeout=300)
        if p.returncode != 0:
            raise RuntimeError(f"git {' '.join(args[:3])}: {p.stderr.strip()[:200]}")
        return p.stdout
    return git


def last_json_object(text: str) -> dict | None:
    """The last complete JSON object in `text`, single-line or pretty-printed over many lines (the delegate
    prints its final DelegateVerdict with indent=2)."""
    dec, found, i = json.JSONDecoder(), None, 0
    while True:
        i = text.find("{", i)
        if i < 0:
            return found
        try:
            obj, end = dec.raw_decode(text, i)
        except json.JSONDecodeError:
            i += 1
            continue
        if isinstance(obj, dict):
            found = obj
        i = end


def run_block(verdict_file: Path, contract_file: Path, review_python: str | None) -> str:
    """What this run hands the reviewer, as text: the verdict path is NOT in the process environment, so the
    PR's own code (the tests the reviewer runs) cannot read it there."""
    return ("\n\n## This run (runner-supplied)\n\n"
            f"VERDICT_FILE={verdict_file}\n"
            f"CONTRACT_FILE={contract_file} (main's copy of docs/REVIEW-CONTRACT.md: read THIS one, not the checkout's)\n"
            f"REVIEW_PYTHON={review_python or 'python3'} (the interpreter that has pytest and the repo's dependencies)\n")


def make_delegate(delegate_path: Path, python: str):
    """The runner's coding delegate, read-only review mode, synchronous. Its stdout's last DelegateVerdict
    line is the lane's answer; the review verdict is what the agent wrote to VERDICT_FILE."""
    def delegate(task: str, repo_path: str, env: dict):
        run_env = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_API_KEY", "PYTHONPATH")}
        run_env.update({k: v for k, v in env.items() if k != "VERDICT_FILE"})      # the path travels in the task text
        p = subprocess.run([python, str(delegate_path), "--repo", repo_path, "--task", task, "--no-ship", "--no-merge",
                            "--foreground", "--message", f"agent review #{env.get('PR_NUMBER')} at {env.get('HEAD', '')[:8]}"],
                           capture_output=True, text=True, env=run_env, timeout=3600)
        dv = last_json_object(p.stdout or "")
        vf = Path(env["VERDICT_FILE"])
        review = vf.read_text(encoding="utf-8") if vf.is_file() else None
        return p.returncode, dv, review
    return delegate


def load_state(path: Path) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(path: Path, state: dict) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(path).with_name(Path(path).name + ".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="agent_review", description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    once = sub.add_parser("once", help="one hourly pass on the runner (subscription lane, API fallback)")
    once.add_argument("--slug", default=os.environ.get("GITHUB_REPOSITORY", "fcavalcantirj/esp-atlas"))
    once.add_argument("--checkout", type=Path, required=True, help="a clone of the repository (origin = GitHub)")
    once.add_argument("--delegate", type=Path, required=True, help="the runner's delegate script")
    once.add_argument("--python", default=sys.executable, help="the delegate's interpreter")
    once.add_argument("--state", type=Path, default=DEFAULT_STATE)
    once.add_argument("--fallback-per-day", type=int, default=int(os.environ.get("JR_REVIEW_FALLBACK_PER_DAY", FALLBACK_PER_DAY)))
    once.add_argument("--dry-run", action="store_true")
    once.add_argument("--review-python", default=None, help="the interpreter the reviewer runs the PR's tests with")
    com = sub.add_parser("comment", help="post a verdict comment (the API lane's workflow step)")
    com.add_argument("--pr", type=int, required=True)
    com.add_argument("--slug", default=os.environ.get("GITHUB_REPOSITORY", "fcavalcantirj/esp-atlas"))
    com.add_argument("--lane", choices=LANES, required=True)
    com.add_argument("--verdict-json", default=os.environ.get("VERDICT_JSON"))
    args = ap.parse_args(argv)
    if args.cmd == "comment":
        v = read_verdict(args.verdict_json)
        if v is None:
            print("agent-review: VERDICT_JSON is not a verdict; nothing posted", file=sys.stderr)
            return 2
        default_gh("pr", "comment", str(args.pr), "--repo", args.slug, "--body", render_comment(v, args.lane))
        if args.lane == "api":
            default_gh("pr", "edit", str(args.pr), "--repo", args.slug, "--remove-label", FALLBACK_LABEL)
        print(f"agent-review: #{args.pr} {v['verdict']} at {v['head'][:8]} posted ({args.lane} lane)")
        return 0
    state = load_state(args.state)
    rep = run_once(gh=default_gh, git=make_git(args.checkout), delegate=make_delegate(args.delegate, args.python),
                   slug=args.slug, now=datetime.now(timezone.utc), state=state, dry_run=args.dry_run,
                   fallback_per_day=args.fallback_per_day, review_python=args.review_python)
    if not args.dry_run:
        save_state(args.state, rep["state"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
