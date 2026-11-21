#!/usr/bin/env python3
"""A demand PR changes exactly what its work item says, and nothing else (scripts/demand_guard.py).

The review of a `jr/research-<KEY>` PR (SPEC-demand-work-consumer.md, "Machine review of a demand PR")
used to include a human reading the diff of `docs/demand/research-queue.json` and `work-receipts.json`
to see that only the broker's own `work_record.py` commands touched them, and that the catalog ids the
PR adds are the ones the validation receipt promised. This script is that reading, as a CI job:

  R1  under docs/demand only research-queue.json and work-receipts.json changed;
  R2  the queue candidate KEY (from the branch name) is `linked` to this PR and nothing else, and its
      validation is readable (research_work.readable_validation: validated_by, verified_on, primary
      sources, expected_ids, forbidden_ids disjoint);
  R3  the receipt KEY carries the same pr_url, phase `author`, a live state;
  R4  every OTHER candidate, receipt and top-level field is byte-identical to the base;
  R5  the catalog records the PR adds under data/boards/<vendor>/<id>/board.md are exactly
      validation.expected_ids; no forbidden id appears in any changed path or added record id; no other
      data/** file changes;
  R6  every commit that touches docs/demand has a subject starting with `chore(demand):`. Not counted: a
      two-parent merge of the base's history whose docs/demand is exactly git's automatic merge of its
      parents (a refresh of the branch, GitHub's test merge). A hand-resolved or edited merge is counted.

A SETTLE PR (2026-11-21: #1968 closed 'esp32 tenstar' as abandoned, a store brand) delivers nothing: its
receipt KEY goes from a live state to `abandoned` or `rejected` (work_record.py settle). It is judged by
R1, S1-S3, R4 for the receipts and R6 instead of R2/R3/R5:
  S1  nothing under data/ changed;
  S2  the receipt's resolution names the same state and a reason;
  S3  in the queue only the candidates whose term is the receipt's term changed, each to `closed` with the
      same outcome; every other candidate and top-level field is unchanged.

Exit 0: every rule holds (the receipt lines say what was checked). Exit 1: a rule failed, named.
Exit 2: not a demand branch, or git/JSON could not be read.

    python3 scripts/demand_guard.py                      # branch, base and PR url from the Actions env
    python3 scripts/demand_guard.py --branch jr/research-KEY --base origin/main --pr-url https://github.com/o/r/pull/1
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "jr"))
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))

import research_queue as rq  # noqa: E402
import research_work as rw  # noqa: E402

BRANCH_PREFIX = "jr/research-"
QUEUE, RECEIPTS = "docs/demand/research-queue.json", "docs/demand/work-receipts.json"
ALLOWED_DEMAND = {QUEUE, RECEIPTS}
COMMIT_PREFIX = "chore(demand):"
_BOARD = re.compile(r"^data/boards/[^/]+/([^/]+)/board\.md$")


class Unreadable(Exception):
    pass


def _git(repo: Path, *args: str) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError) as e:
        raise Unreadable(f"git {' '.join(args)}: {e}") from e
    if p.returncode != 0:
        raise Unreadable(f"git {' '.join(args)}: {p.stderr.strip()[:200]}")
    return p.stdout


def _is_ancestor(repo: Path, commit: str, of: str) -> bool:
    """True when `commit` is in the history of `of`. Anything but a clean yes (an unknown sha, a git error) is no."""
    try:
        p = subprocess.run(["git", "merge-base", "--is-ancestor", commit, of], cwd=repo, capture_output=True,
                           text=True, timeout=120)
    except (subprocess.TimeoutExpired, OSError):
        return False
    return p.returncode == 0


def _clean_merge_of_base(repo: Path, sha: str, parents: list[str], base: str) -> bool:
    """True only for a two-parent merge with a parent in the base's history whose docs/demand tree is exactly
    what `git merge-tree` computes from the two parents without a conflict. Fail closed: an octopus, a
    conflict, a git too old for `merge-tree --write-tree`, any error -> False, and R6 judges the commit."""
    if len(parents) != 2 or not any(_is_ancestor(repo, par, base) for par in parents):
        return False
    try:
        p = subprocess.run(["git", "merge-tree", "--write-tree", parents[0], parents[1]], cwd=repo,
                           capture_output=True, text=True, timeout=120)
        if p.returncode != 0:
            return False
        auto = p.stdout.split("\n")[0].strip()
        return bool(auto) and (_git(repo, "rev-parse", f"{auto}:docs/demand").strip()
                               == _git(repo, "rev-parse", f"{sha}:docs/demand").strip())
    except (subprocess.TimeoutExpired, OSError, Unreadable):
        return False


def _json_at(repo: Path, ref: str, path: str) -> dict:
    try:
        return json.loads(_git(repo, "show", f"{ref}:{path}"))
    except json.JSONDecodeError as e:
        raise Unreadable(f"{ref}:{path}: {e}") from e


def key_of(branch: str | None) -> str | None:
    b = (branch or "").strip()
    if b.startswith("refs/heads/"):
        b = b[len("refs/heads/"):]
    return b[len(BRANCH_PREFIX):] if b.startswith(BRANCH_PREFIX) and len(b) > len(BRANCH_PREFIX) else None


def changed_paths(repo: Path, base: str, head: str) -> list[tuple[str, str]]:
    """[(status, path)] of base...head, status A/M/D/R…"""
    out = []
    for line in _git(repo, "diff", "--name-status", f"{base}...{head}").split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        out.append((parts[0][0], parts[-1]))
    return out


def check(repo: Path, *, base: str, head: str, branch: str, pr_url: str | None) -> tuple[list[str], list[str]]:
    """(problems, receipt lines). Raises Unreadable when the inputs cannot be read."""
    key = key_of(branch)
    if not key:
        raise Unreadable(f"{branch!r} is not a {BRANCH_PREFIX}<KEY> branch")
    problems, lines = [], [f"work {key}: branch {branch}"]
    changes = changed_paths(repo, base, head)
    paths = [p for _s, p in changes]

    demand = [p for p in paths if p.startswith("docs/demand/")]
    extra = sorted(set(demand) - ALLOWED_DEMAND)
    if extra:
        problems.append(f"R1 demand files other than the queue and receipts changed: {', '.join(extra)}")
    lines.append(f"R1 demand files changed: {', '.join(sorted(demand)) or 'none'}")

    q_base, q_head = _json_at(repo, base, QUEUE), _json_at(repo, head, QUEUE)
    r_base, r_head = _json_at(repo, base, RECEIPTS), _json_at(repo, head, RECEIPTS)
    rec_base = {r.get("key"): r for r in (r_base.get("receipts") or []) if isinstance(r, dict)}.get(key) or {}
    rec_head = {r.get("key"): r for r in (r_head.get("receipts") or []) if isinstance(r, dict)}.get(key) or {}
    if rec_head.get("state") in SETTLE_STATES and rec_base.get("state") not in SETTLE_STATES + ("delivered",):
        _check_settle(repo, key, base, head, changes, q_base, q_head, r_base, r_head, rec_base, rec_head, problems, lines)
        return problems, lines
    cands_head = q_head.get("candidates") or {}
    cand = cands_head.get(key)
    if not isinstance(cand, dict):
        problems.append(f"R2 queue has no candidate {key}")
        cand = {}
    links = [u for u in (cand.get("linked_work") or []) if isinstance(u, str)]
    if cand.get("status") != rw.STATUS_LINKED:
        problems.append(f"R2 candidate {key} is {cand.get('status')!r}, not {rw.STATUS_LINKED!r}")
    if pr_url and links != [pr_url]:
        problems.append(f"R2 candidate {key} links {links}, not exactly this PR {pr_url}")
    elif not pr_url and len(links) != 1:
        problems.append(f"R2 candidate {key} links {len(links)} PRs, not one")
    validation = rw.readable_validation(cand) if cand else None
    if validation is None:
        problems.append(f"R2 candidate {key} has no readable validation (validated_by, verified_on, primary_sources, expected_ids)")
        expected, forbidden = set(), set()
    else:
        expected, forbidden = set(validation.get("expected_ids") or []), set(validation.get("forbidden_ids") or [])
    lines.append(f"R2 candidate {key}: status {cand.get('status')!r}, linked_work {links}, expected_ids {sorted(expected)}, forbidden_ids {sorted(forbidden)}")

    receipts_head = {r.get("key"): r for r in (r_head.get("receipts") or []) if isinstance(r, dict)}
    rec = receipts_head.get(key)
    if not isinstance(rec, dict):
        problems.append(f"R3 receipts have no entry {key}")
        rec = {}
    if pr_url and rec.get("pr_url") != pr_url:
        problems.append(f"R3 receipt {key} pr_url is {rec.get('pr_url')!r}, not this PR")
    if rec.get("phase") != rw.PHASE_AUTHOR:
        problems.append(f"R3 receipt {key} phase is {rec.get('phase')!r}, not {rw.PHASE_AUTHOR!r}")
    if rec.get("state") in ("abandoned", "rejected", "delivered"):
        problems.append(f"R3 receipt {key} is already {rec.get('state')!r}")
    lines.append(f"R3 receipt {key}: phase {rec.get('phase')!r}, state {rec.get('state')!r}, pr_url {rec.get('pr_url')!r}")

    def _others_q(doc):
        d = {k: v for k, v in doc.items() if k != "candidates"}
        d["candidates"] = {k: v for k, v in (doc.get("candidates") or {}).items() if k != key}
        return json.dumps(d, sort_keys=True)

    def _others_r(doc):
        return _receipts_but(doc, key)

    if _others_q(q_base) != _others_q(q_head):
        problems.append(f"R4 a candidate other than {key}, or a queue top-level field, changed")
    if _others_r(r_base) != _others_r(r_head):
        problems.append(f"R4 a receipt other than {key}, or a receipts top-level field, changed")
    lines.append("R4 every other candidate and receipt unchanged" if not any(p.startswith("R4") for p in problems) else "R4 see above")

    added_ids = {m.group(1) for s, p in changes if s == "A" and (m := _BOARD.match(p))}
    other_data = sorted(p for s, p in changes if p.startswith("data/") and not (s == "A" and _BOARD.match(p)))
    if added_ids != expected:
        problems.append(f"R5 records added {sorted(added_ids)} != expected_ids {sorted(expected)}")
    hit = sorted(f for f in forbidden if f in added_ids or any(f"/{f}/" in p for p in paths))
    if hit:
        problems.append(f"R5 forbidden id(s) in the change: {', '.join(hit)}")
    if other_data:
        problems.append(f"R5 data/** changed beyond the expected records: {', '.join(other_data)}")
    lines.append(f"R5 records added: {sorted(added_ids)}")

    _check_commits(repo, base, head, problems, lines)
    return problems, lines


SETTLE_STATES = ("abandoned", "rejected")


def _receipts_but(doc: dict, key: str) -> str:
    d = {k: v for k, v in doc.items() if k != "receipts"}
    d["receipts"] = sorted((json.dumps(r, sort_keys=True) for r in (doc.get("receipts") or []) if (r or {}).get("key") != key))
    return json.dumps(d, sort_keys=True)


def _check_settle(repo, key, base, head, changes, q_base, q_head, r_base, r_head, rec_base, rec_head, problems, lines):
    """S1-S3, R4 for the receipts and R6 for a PR that settles its work item instead of delivering it."""
    state = rec_head.get("state")
    lines.append(f"S1 settle {key}: {rec_base.get('state')} -> {state}")
    data = sorted(p for _s, p in changes if p.startswith("data/"))
    if data:
        problems.append(f"S1 a settle changed catalog data: {', '.join(data[:5])}")
    res = rec_head.get("resolution") if isinstance(rec_head.get("resolution"), dict) else {}
    if res.get("status") != state or not str(res.get("reason") or "").strip():
        problems.append(f"S2 receipt {key} resolution {res!r} does not name {state!r} and a reason")
    term = rq.term_key(rec_head.get("term"))
    cb, ch = q_base.get("candidates") or {}, q_head.get("candidates") or {}
    for k in sorted(set(cb) | set(ch)):
        if cb.get(k) == ch.get(k):
            continue
        c = ch.get(k) if isinstance(ch.get(k), dict) else {}
        outcome = c.get("outcome") if isinstance(c.get("outcome"), dict) else {}
        if rq.term_key(c.get("term")) != term or not term:
            problems.append(f"S3 queue candidate {k!r} changed, but it is not the settled term {term!r}")
        elif c.get("status") != "closed" or outcome.get("status") != state:
            problems.append(f"S3 queue candidate {k!r} is {c.get('status')!r} with outcome {outcome.get('status')!r}, "
                            f"not closed as {state!r}")
    if {k: v for k, v in q_base.items() if k != "candidates"} != {k: v for k, v in q_head.items() if k != "candidates"}:
        problems.append("S3 a queue top-level field changed")
    if _receipts_but(r_base, key) != _receipts_but(r_head, key):
        problems.append(f"R4 a receipt other than {key}, or a receipts top-level field, changed")
    _check_commits(repo, base, head, problems, lines)


def _check_commits(repo, base, head, problems, lines):
    """R6, shared by deliveries and settles."""
    # A merge that brings main in and leaves docs/demand exactly as git's own automatic merge of its two
    # parents does is not a hand edit: it only carries what main changed there since the branch was cut (every
    # refresh of the branch, GitHub's test merge; 2026-11-19: #1846 went red on "Merge branch 'main'"). Anything
    # typed into such a merge, a hand-resolved conflict included, makes it differ and R6 judges its subject.
    subjects, merges_of_main = [], 0
    for row in _git(repo, "log", "--format=%H%x1f%P%x1f%s", f"{base}..{head}", "--", "docs/demand").split("\n"):
        if not row.strip():
            continue
        _sha, parents, subject = (row.split("\x1f") + ["", ""])[:3]
        if _clean_merge_of_base(repo, _sha, parents.split(), base):
            merges_of_main += 1
            continue
        subjects.append(subject)
    bad = [s for s in subjects if not s.startswith(COMMIT_PREFIX)]
    if bad:
        problems.append(f"R6 commit(s) touching docs/demand without the {COMMIT_PREFIX} subject: {bad[:3]}")
    merged = f" ({merges_of_main} clean merge of main not counted)" if merges_of_main else ""
    lines.append(f"R6 demand commits: {len(subjects)}, all {COMMIT_PREFIX}{merged}" if not bad else "R6 see above")


def default_base() -> str:
    ref = os.environ.get("GITHUB_BASE_REF")
    return f"origin/{ref}" if ref else "origin/main"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=str(REPO))
    ap.add_argument("--base", default=None)
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--branch", default=None, help="default: GITHUB_HEAD_REF, else the checked-out branch")
    ap.add_argument("--pr-url", default=os.environ.get("PR_URL") or None)
    a = ap.parse_args(argv)
    repo = Path(a.repo)
    try:
        branch = a.branch or os.environ.get("GITHUB_HEAD_REF") or _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
        problems, lines = check(repo, base=a.base or default_base(), head=a.head, branch=branch, pr_url=a.pr_url)
    except Unreadable as e:
        print(f"demand guard: cannot read: {e}", file=sys.stderr)
        return 2
    for ln in lines:
        print(f"  {ln}")
    if problems:
        print("\nDEMAND GUARD FAILED:")
        for p in problems:
            print(f"  ✗ {p}")
        return 1
    print("\n✓ demand guard: the PR changes exactly what its work item says")
    return 0


if __name__ == "__main__":
    sys.exit(main())
