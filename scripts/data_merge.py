#!/usr/bin/env python3
"""The one serialized merger of Jr's data PRs (scripts/data_merge.py; Jr redesign plan, step 6).

Jr's tick publishes build-target facts in PRs labelled `jr-data`; a failing fact is hidden through PRs labelled
`jr-quarantine`. This coordinator is the ONLY thing that merges them, and it is LEVEL-TRIGGERED: every run reads
the open PRs and main as they are now and decides each PR afresh, so a run that GitHub replaced or cancelled
loses nothing. It runs in the `jr-data-merge` workflow (one concurrency group) from main's own code.

For each open PR, decide() answers one of:
  merge          eligible, both switches on, every required check green at the head, the head contains main's
                 tip, the diff inside its scope, the bookkeeping only adds or updates entries, within the limits;
                 the merge is `gh pr merge --merge --match-head-commit <head>`;
  update-branch  the head is behind main (strict up-to-date: checks must run on a head that contains main);
  wait           a required check is still running;
  close-timeout  open more than STALE_HOURS and not mergeable: closed with the `jr-timeout` label and a
                 marker comment, which jr/pending_prs.py treats as a re-queue, not a 30-day veto;
  skip           with the reason (not eligible, a switch off, a failed or missing check, out of scope, ...).

Scope of a `jr-data` PR: added build-target recipes, added firmware records with their signals, and the
enumerated bookkeeping files; never a modified or deleted record. A BACKFILL PR (`jr/tick-*-bf`, root-cause plan,
2026-11-26) has its own switch (`backfill_automerge`) and scope: modified board.md files only, every one of which
this run re-derives itself through scripts/check_claims.check_board_backfill from main's code (zero re-derived
fields is never a merge), counted in FIELDS per PR and per UTC day. Scope of a `jr-quarantine` PR: only
data/quarantine.json, never subject to the fact limits. `--dry-run` (the default) only prints.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import demand_canary  # noqa: E402

FLAG, VARIABLE = "build_target_automerge", "JR_TICK_AUTOMERGE"
JR_LOGIN = "espatlas-jr"
DATA_LABEL, QUARANTINE_LABEL, TIMEOUT_LABEL = "jr-data", "jr-quarantine", "jr-timeout"
TIMEOUT_MARKER = "<!-- jr-data-merge timeout -->"
REQUIRED_CHECKS = ("schema", "tests", "jr-tests", "quotes", "claims")
MAX_FACTS_PER_PR, MAX_FACTS_PER_DAY = 10, 30
BF_FLAG = "backfill_automerge"
MAX_FIELDS_PER_PR, MAX_FIELDS_PER_DAY = 12, 40
_BOARD = re.compile(r"^data/boards/[^/]+/[^/]+/board\.md$")
STALE_HOURS = 6
_RECIPE = re.compile(r"^data/recipes/([^/]+)/recipe\.md$")
_FIRMWARE = re.compile(r"^data/firmware/([^/]+)/firmware\.md$")
_SIGNALS = re.compile(r"^data/firmware/([^/]+)/signals\.json$")
_TELEMETRY_DAY = re.compile(r"^docs/telemetry/data-\d{4}-\d{2}-\d{2}\.md$")
BOOKKEEPING = {"jr/proposed_ledger.json": ("by_id", "by_repo"), "jr/board_cooldown.json": ("by_board",)}
APPEND_ONLY = ("docs/telemetry/yield.jsonl", "docs/telemetry/data-trend.jsonl")


def keys_kept(base: dict, head: dict, groups: tuple) -> bool:
    """Every entry under `groups` in main's file is still in the PR's (entries may be added or updated, never
    removed): the ledger's statuses and the cooldown's expiries change legitimately."""
    return all(set((base or {}).get(g) or {}) <= set((head or {}).get(g) or {}) for g in groups)


def lines_appended(base: str, head: str) -> bool:
    return head.startswith(base)


def _hours(since: str, now: str) -> float:
    a = datetime.fromisoformat(since.replace("Z", "+00:00"))
    b = datetime.fromisoformat(now.replace("Z", "+00:00"))
    return (b - a).total_seconds() / 3600


def _scope(kind: str, files: list[dict]) -> tuple[list[str], int]:
    """(problems, number of facts added) for the PR's full file list."""
    problems, facts = [], 0
    if kind == QUARANTINE_LABEL:
        for f in files:
            if f["path"] != "data/quarantine.json" or f["status"] != "modified":
                problems.append(f"scope: {f['status']} {f['path']} in a quarantine PR")
        return problems, 0
    new_firmware = {m.group(1) for f in files if f["status"] == "added" and (m := _FIRMWARE.match(f["path"]))}
    for f in files:
        p, st = f["path"], f["status"]
        if _RECIPE.match(p) or _FIRMWARE.match(p):
            if st != "added":
                problems.append(f"existing record {st}: {p}")
            elif _RECIPE.match(p):
                facts += 1
        elif (m := _SIGNALS.match(p)):
            if st != "added" or m.group(1) not in new_firmware:
                problems.append(f"signals for a firmware this PR does not add: {st} {p}")
        elif p in BOOKKEEPING or p in APPEND_ONLY:
            if st != "modified":
                problems.append(f"scope: bookkeeping {st}: {p}")
        elif _TELEMETRY_DAY.match(p):
            if st != "added":
                problems.append(f"scope: {st} {p}")
        else:
            problems.append(f"scope: {st} {p}")
    return problems, facts


def decide(pr: dict, st: dict, *, switches: dict, now: str) -> dict:
    """`pr`: one `gh pr list` entry. `st`: {"checks": {name: pass|pending|fail}, "behind_by": int, "files":
    [{path, status}], "bookkeeping_ok": bool, "facts_today": int}. `switches`: {"autonomy": {...}, "env": {...}}."""
    n, head = pr.get("number"), pr.get("headRefOid")
    out = lambda action, why="": {"pr": n, "head": head, "action": action, "why": why}  # noqa: E731
    labels = {l.get("name") for l in pr.get("labels") or []}
    kind = DATA_LABEL if DATA_LABEL in labels else QUARANTINE_LABEL if QUARANTINE_LABEL in labels else None
    branch = str(pr.get("headRefName") or "")
    if kind is None:
        return out("skip", "no jr-data / jr-quarantine label")
    if (pr.get("author") or {}).get("login") != JR_LOGIN:
        return out("skip", f"author is not {JR_LOGIN}")
    if pr.get("isCrossRepository"):
        return out("skip", "a fork's PR is never merged")
    if pr.get("baseRefName") != "main":
        return out("skip", "base is not main")
    if not branch.startswith("jr/tick-" if kind == DATA_LABEL else "jr/quarantine-"):
        return out("skip", f"branch {branch} does not match the {kind} label")
    backfill = kind == DATA_LABEL and branch.endswith("-bf")
    flag = BF_FLAG if backfill else FLAG
    if not (switches.get("autonomy") or {}).get(flag):
        return out("skip", f"switch off: jr/autonomy.json {flag} is not true")
    if str((switches.get("env") or {}).get(VARIABLE, "")).strip() == "0":
        return out("skip", f"switch off: {VARIABLE}=0")
    checks = st.get("checks") or {}
    stale = _hours(pr.get("createdAt") or now, now) > STALE_HOURS
    failed = [c for c in REQUIRED_CHECKS if checks.get(c) not in ("pass", "pending")]
    if failed:
        if stale:
            return out("close-timeout", f"open over {STALE_HOURS} h with {', '.join(failed)} not passing")
        return out("skip", f"required check not passing: {', '.join(failed)}")
    if any(checks.get(c) == "pending" for c in REQUIRED_CHECKS):
        return out("wait", "required checks still running")
    if st.get("behind_by", 0) > 0:
        return out("update-branch", f"head is {st['behind_by']} commit(s) behind main")
    if backfill:
        files = st.get("files") or []
        bad = [f"{f['status']} {f['path']}" for f in files if not (_BOARD.match(f["path"]) and f["status"] == "modified")]
        if bad or not files:
            return out("skip", f"scope: a backfill PR changes only existing board.md files ({', '.join(bad)[:200]})")
        bf = st.get("backfill") or {}
        if not bf.get("boards") or not bf.get("fields"):
            return out("skip", "nothing re-derived: zero backfilled fields is never a merge")
        if bf.get("pass") != bf.get("boards") or bf.get("boards") != len(files):
            return out("skip", "re-derivation did not pass every board: " + "; ".join(bf.get("problems") or [])[:240])
        if bf["fields"] > MAX_FIELDS_PER_PR:
            return out("skip", f"{bf['fields']} fields, more than {MAX_FIELDS_PER_PR} per PR")
        if st.get("fields_today", 0) + bf["fields"] > MAX_FIELDS_PER_DAY:
            return out("skip", f"would pass {MAX_FIELDS_PER_DAY} fields per day")
        return out("merge")
    problems, facts = _scope(kind, st.get("files") or [])
    if problems:
        return out("skip", "; ".join(problems)[:300])
    if kind == DATA_LABEL:
        if not st.get("bookkeeping_ok", False):
            return out("skip", "bookkeeping removes entries or rewrites appended lines")
        if facts > MAX_FACTS_PER_PR:
            return out("skip", f"{facts} facts, more than {MAX_FACTS_PER_PR} per PR")
        if st.get("facts_today", 0) + facts > MAX_FACTS_PER_DAY:
            return out("skip", f"would pass {MAX_FACTS_PER_DAY} facts per day")
    return out("merge")


# --- live state (the workflow) -----------------------------------------------------------------------------

def _gh_json(gh, *args):
    return json.loads(gh(*args) or "null")


def gather(gh, slug: str, pr: dict, repo: Path = REPO) -> dict:
    n, head = pr["number"], pr["headRefOid"]
    checks = {c.get("name"): c.get("bucket") for c in _gh_json(gh, "pr", "checks", str(n), "--repo", slug, "--json", "name,bucket") or []}
    cmp = _gh_json(gh, "api", f"repos/{slug}/compare/main...{head}") or {}
    files = [{"path": f.get("filename"), "status": f.get("status")} for f in cmp.get("files") or []]

    def show(ref, path):
        p = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=repo, capture_output=True, text=True)
        return p.stdout if p.returncode == 0 else None

    ok = True
    subprocess.run(["git", "fetch", "-q", "origin", f"+{head}:refs/remotes/pr/{n}"], cwd=repo, capture_output=True)
    for path, groups in BOOKKEEPING.items():
        if any(f["path"] == path for f in files):
            b, h = show("origin/main", path), show(f"pr/{n}", path)
            ok = ok and b is not None and h is not None and keys_kept(json.loads(b), json.loads(h), groups)
    for path in APPEND_ONLY:
        if any(f["path"] == path for f in files):
            b, h = show("origin/main", path), show(f"pr/{n}", path)
            ok = ok and b is not None and h is not None and lines_appended(b, h)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    added = subprocess.run(["git", "log", "--since", f"{today}T00:00:00Z", "--diff-filter=A", "--name-only", "--format=",
                            "origin/main", "--", "data/recipes"], cwd=repo, capture_output=True, text=True).stdout
    facts_today = sum(1 for line in added.split() if _RECIPE.match(line) and "status: build-target" in (show("origin/main", line) or ""))
    out = {"checks": checks, "behind_by": int(cmp.get("behind_by") or 0), "files": files,
           "bookkeeping_ok": ok, "facts_today": facts_today}
    if str(pr.get("headRefName") or "").endswith("-bf"):
        out["backfill"] = _rederive(files, show, n, today)
        out["fields_today"] = _fields_today(repo, today)
    return out


def _rederive(files: list, show, n: int, today: str) -> dict:
    """Re-derive every board the backfill PR changes, from main's code (this checkout) on the live pages."""
    import check_claims
    import board_backfill
    res = {"boards": 0, "pass": 0, "fields": 0, "problems": []}
    for f in files:
        if not _BOARD.match(f["path"]):
            continue
        res["boards"] += 1
        base, head = show("origin/main", f["path"]), show(f"pr/{n}", f["path"])
        r = check_claims.check_board_backfill(base or "", head or "", REPO / "data", board_backfill.default_fetch, today) \
            if base and head else {"verdict": "INCONCLUSIVE", "id": f["path"], "reasons": ["unreadable at a ref"]}
        if r is None:
            res["problems"].append(f"{f['path']}: no backfilled field")
            continue
        if r["verdict"] == check_claims.PASS:
            res["pass"] += 1
            from esp_atlas_core.frontmatter import parse_frontmatter_text
            fb, _ = parse_frontmatter_text(base)
            fh, _ = parse_frontmatter_text(head)
            res["fields"] += sum(1 for k in fh if k not in fb and k in check_claims.BACKFILL_FIELDS)
        else:
            res["problems"].append(f"{r['id']}: {r['verdict']} {'; '.join(r['reasons'][:2])}"[:200])
    return res


_FIELD_LINE = re.compile(r"^\+(" + "|".join(("usb_serial", "download_mode", "getting_started")) + r"):", re.M)


def _fields_today(repo: Path, today: str) -> int:
    """Gated fields added to board.md files on main since 00:00 UTC (its own history, one count per added line)."""
    diff = subprocess.run(["git", "log", "--since", f"{today}T00:00:00Z", "-p", "--format=", "origin/main", "--",
                           "data/boards"], cwd=repo, capture_output=True, text=True).stdout
    return len(_FIELD_LINE.findall(diff))


def act(gh, slug: str, d: dict) -> str:
    n = str(d["pr"])
    if d["action"] == "merge":
        return gh("pr", "merge", n, "--repo", slug, "--merge", "--match-head-commit", d["head"])
    if d["action"] == "update-branch":
        return gh("pr", "update-branch", n, "--repo", slug)
    if d["action"] == "close-timeout":
        gh("pr", "edit", n, "--repo", slug, "--add-label", TIMEOUT_LABEL)
        gh("pr", "comment", n, "--repo", slug, "--body", f"{TIMEOUT_MARKER}\nClosed by jr-data-merge: {d['why']}. "
                                                         "A timeout, not a rejection: its facts are re-queued.")
        return gh("pr", "close", n, "--repo", slug)
    return ""


def main(argv=None) -> int:
    import os
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="act; without it, only print the decisions")
    ap.add_argument("--repo-slug", default=os.environ.get("GITHUB_REPOSITORY", "fcavalcantirj/esp-atlas"))
    args = ap.parse_args(argv)
    gh = demand_canary.default_gh
    autonomy = json.loads((REPO / "jr" / "autonomy.json").read_text(encoding="utf-8"))
    switches = {"autonomy": autonomy, "env": {VARIABLE: os.environ.get(VARIABLE, "")}}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prs = _gh_json(gh, "pr", "list", "--repo", args.repo_slug, "--state", "open", "--limit", "100", "--json",
                   "number,headRefName,headRefOid,baseRefName,author,isCrossRepository,labels,createdAt") or []
    mine = [p for p in prs if {l.get("name") for l in p.get("labels") or []} & {DATA_LABEL, QUARANTINE_LABEL}]
    print(f"jr-data-merge {'APPLY' if args.apply else 'dry run'} at {now}: {len(mine)} labelled PR(s)")
    for p in sorted(mine, key=lambda x: x["number"]):
        d = decide(p, gather(gh, args.repo_slug, p), switches=switches, now=now)
        print(f"  #{d['pr']} {d['action']}{': ' + d['why'] if d['why'] else ''}")
        if args.apply and d["action"] in ("merge", "update-branch", "close-timeout"):
            act(gh, args.repo_slug, d)
            if d["action"] == "merge":
                break                                         # one merge per run: main moved, the rest re-check
    return 0


if __name__ == "__main__":
    sys.exit(main())
