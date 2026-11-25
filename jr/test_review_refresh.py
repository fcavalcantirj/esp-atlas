"""Jr keeps its own review PRs mergeable (SPEC-jr-review-routing.md §8): a jr-review tick PR that conflicts
with main only in bookkeeping is refreshed by a merge commit on top of its head — the ledger rebuilt as
main + the PR's carried decisions + its own proposals, every other bookkeeping file from main — pushed
fast-forward, and only when the ledger guard is green and the PR's catalog files are byte-identical."""
from __future__ import annotations

import copy
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import memory

NOW = datetime(2026, 11, 15, 10, 0, tzinfo=timezone.utc)
_spec = importlib.util.spec_from_file_location("ledger_guard", Path(__file__).resolve().parent.parent / "scripts" / "ledger_guard.py")
ledger_guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ledger_guard)


def iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def rec(fid, status="rejected", hours_ago=1, ttl=30, **kw):
    r = {"id": fid, "repo": f"o/{fid}", "status": status, "timestamp": iso(NOW - timedelta(hours=hours_ago)), "pr_ref": None}
    if status in ("rejected", "seen") and ttl:
        r["expires"] = iso(NOW - timedelta(hours=hours_ago) + timedelta(days=ttl))
    r.update(kw)
    return r


def doc(*records):
    return {"by_id": {r["id"]: r for r in records}, "by_repo": {r["repo"]: r["id"] for r in records}}


def test_the_merged_ledger_keeps_main_and_carries_the_prs_decisions_and_proposals():
    base = doc(rec("old", hours_ago=900, ttl=60))
    main = doc(rec("old", hours_ago=900, ttl=60), rec("main-only", hours_ago=2), rec("fw-merged", status="merged", hours_ago=3))
    pr = doc(rec("old", hours_ago=900, ttl=60), rec("pr-decision", hours_ago=1), rec("orcdial", status="proposed", hours_ago=1, pr_ref="#1730"))
    merged = memory.merge_pr_ledger(main, base, pr, now=NOW)
    assert merged["by_id"]["main-only"] == main["by_id"]["main-only"]
    assert merged["by_id"]["fw-merged"]["status"] == "merged"
    assert merged["by_id"]["pr-decision"] == pr["by_id"]["pr-decision"]
    assert merged["by_id"]["orcdial"] == pr["by_id"]["orcdial"]
    assert ledger_guard.check(main, merged) == []


def test_a_newer_main_decision_wins_and_a_protected_one_is_never_replaced():
    base = doc()
    main = doc(rec("a", hours_ago=1, reason="main"), rec("v", ttl=None, hours_ago=50), rec("m", status="merged", hours_ago=50))
    pr = doc(rec("a", hours_ago=5, reason="pr"), rec("v", hours_ago=1), rec("m", status="proposed", hours_ago=1, pr_ref="#9"))
    merged = memory.merge_pr_ledger(main, base, pr, now=NOW)
    assert merged["by_id"]["a"]["reason"] == "main"
    assert merged["by_id"]["v"] == main["by_id"]["v"] and merged["by_id"]["m"] == main["by_id"]["m"]
    assert ledger_guard.check(main, merged) == []


def test_a_proposal_main_already_holds_is_left_as_main_has_it():
    base = doc()
    main = doc(rec("glide", status="proposed", hours_ago=2, pr_ref="#1717"))
    pr = doc(rec("glide", status="proposed", hours_ago=1, pr_ref="#1730"))      # a hydration copy of another PR's proposal
    merged = memory.merge_pr_ledger(main, base, pr, now=NOW)
    assert merged["by_id"]["glide"] == main["by_id"]["glide"]


def test_the_merge_does_not_mutate_its_inputs_and_is_idempotent():
    base, main, pr = doc(), doc(rec("x", hours_ago=3)), doc(rec("y", hours_ago=1), rec("z", status="proposed"))
    snap = copy.deepcopy((base, main, pr))
    once = memory.merge_pr_ledger(main, base, pr, now=NOW)
    assert (base, main, pr) == snap
    assert memory.merge_pr_ledger(once, base, pr, now=NOW) == once


# --- the refresh itself, on REAL git (a throwaway bare origin + clone); only gh is faked ---------------

import json  # noqa: E402
import subprocess  # noqa: E402
from types import SimpleNamespace  # noqa: E402

import publish  # noqa: E402
import review_refresh  # noqa: E402

LEDGER = "jr/proposed_ledger.json"


def _sh(cwd, *args):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def _write(root, rel, text):
    f = root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(text)


def _ledger_text(d):
    return json.dumps(d, indent=2, sort_keys=True) + "\n"


def _repo(tmp_path, *, pr_extra=None, main_extra=None, seed_extra=None):
    """origin with main + a tick branch that changed the ledger and added a firmware; main then moved
    (a new ledger record) so the branch conflicts on the ledger only."""
    origin, clone = tmp_path / "origin.git", tmp_path / "clone"
    _sh(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _sh(tmp_path, "clone", str(origin), str(clone))
    for k, v in (("user.email", "jr@example.com"), ("user.name", "Jr")):
        _sh(clone, "config", k, v)
    _write(clone, LEDGER, _ledger_text(doc(rec("seed", hours_ago=500, ttl=60))))
    _write(clone, "data/firmware/seed/firmware.md", "seed\n")
    for rel, text in (seed_extra or {}).items():
        _write(clone, rel, text)
    _sh(clone, "add", "-A"); _sh(clone, "commit", "-qm", "seed"); _sh(clone, "push", "-q", "origin", "main")
    _sh(clone, "checkout", "-qb", "jr/tick-x")
    _write(clone, LEDGER, _ledger_text(doc(rec("seed", hours_ago=500, ttl=60), rec("pr-dec", hours_ago=1),
                                           rec("newfw", status="proposed", hours_ago=1, pr_ref="#7"))))
    _write(clone, "data/firmware/newfw/firmware.md", "new firmware\n")
    for rel, text in (pr_extra or {}).items():
        _write(clone, rel, text)
    _sh(clone, "add", "-A"); _sh(clone, "commit", "-qm", "tick"); _sh(clone, "push", "-q", "origin", "jr/tick-x")
    head = _sh(clone, "rev-parse", "HEAD")
    _sh(clone, "checkout", "-q", "main")
    _write(clone, LEDGER, _ledger_text(doc(rec("seed", hours_ago=500, ttl=60), rec("main-dec", hours_ago=2))))
    for rel, text in (main_extra or {}).items():
        _write(clone, rel, text)
    _sh(clone, "add", "-A"); _sh(clone, "commit", "-qm", "main moved"); _sh(clone, "push", "-q", "origin", "main")
    return clone, head


def _git(clone):
    return lambda *a: subprocess.run(["git", *a], cwd=clone, capture_output=True, text=True)


def _gh(authors=(publish.JR_LOGIN,)):
    def gh(*a):
        if a[:2] == ("pr", "view") and "commits" in a:
            return SimpleNamespace(returncode=0, stdout=json.dumps({"commits": [{"authors": [{"login": x}]} for x in authors]}))
        return SimpleNamespace(returncode=1, stdout="", stderr="unexpected")
    return gh


def _pr(head, mergeable="CONFLICTING", labels=("jr-review",)):
    return {"number": 7, "headRefName": "jr/tick-x", "headRefOid": head, "mergeable": mergeable,
            "labels": [{"name": x} for x in labels], "author": {"login": publish.JR_LOGIN}, "isCrossRepository": False}


def test_a_conflicting_review_pr_is_refreshed_fast_forward_with_the_merged_ledger(tmp_path):
    clone, head = _repo(tmp_path)
    r = review_refresh.refresh(_pr(head), git=_git(clone), gh=_gh(), now=NOW)
    assert r["status"] == "refreshed", r
    new = _sh(clone, "rev-parse", "origin/jr/tick-x") if _sh(clone, "fetch", "-q", "origin") is not None else None
    assert _sh(clone, "merge-base", "--is-ancestor", head, new) == ""            # fast-forward: the old head is an ancestor
    merged = json.loads(_sh(clone, "show", f"{new}:{LEDGER}"))
    assert {"main-dec", "pr-dec", "newfw"} <= set(merged["by_id"])
    assert _sh(clone, "show", f"{new}:data/firmware/newfw/firmware.md") == "new firmware"
    assert _sh(clone, "merge-tree", "--write-tree", "origin/main", new)            # now merges clean with main


def test_a_human_commit_on_the_pr_is_never_refreshed(tmp_path):
    clone, head = _repo(tmp_path)
    r = review_refresh.refresh(_pr(head), git=_git(clone), gh=_gh((publish.JR_LOGIN, "fcavalcantirj")), now=NOW)
    assert r["status"] == "skipped" and "human" in r["why"]


def test_a_content_conflict_is_never_resolved(tmp_path):
    clone, head = _repo(tmp_path, pr_extra={"data/firmware/seed/firmware.md": "pr edit\n"},
                        main_extra={"data/firmware/seed/firmware.md": "main edit\n"})
    r = review_refresh.refresh(_pr(head), git=_git(clone), gh=_gh(), now=NOW)
    assert r["status"] == "skipped" and r["why"] == "content conflict: data/firmware/seed/firmware.md"
    _sh(clone, "fetch", "-q", "origin")
    assert _sh(clone, "rev-parse", "origin/jr/tick-x") == head                    # nothing pushed


def test_only_a_conflicting_jr_review_pr_qualifies(tmp_path):
    clone, head = _repo(tmp_path)
    assert review_refresh.refresh(_pr(head, mergeable="MERGEABLE"), git=_git(clone), gh=_gh(), now=NOW)["status"] == "skipped"
    assert review_refresh.refresh(_pr(head, labels=()), git=_git(clone), gh=_gh(), now=NOW)["status"] == "skipped"
    foreign = dict(_pr(head), author={"login": "someone"})
    assert review_refresh.refresh(foreign, git=_git(clone), gh=_gh(), now=NOW)["status"] == "skipped"


def test_a_head_that_moved_since_the_listing_is_not_touched(tmp_path):
    clone, head = _repo(tmp_path)
    r = review_refresh.refresh(_pr("0" * 40), git=_git(clone), gh=_gh(), now=NOW)
    assert r["status"] == "skipped" and "moved" in r["why"]


def test_a_dry_run_says_it_would_refresh_and_pushes_nothing(tmp_path):
    clone, head = _repo(tmp_path)
    r = review_refresh.refresh(_pr(head), git=_git(clone), gh=_gh(), now=NOW, dry_run=True)
    assert r["status"] == "would_refresh"
    _sh(clone, "fetch", "-q", "origin")
    assert _sh(clone, "rev-parse", "origin/jr/tick-x") == head


def test_an_auto_merged_change_to_the_prs_catalog_file_is_refused(tmp_path):
    """Main and the PR touch different lines of one catalog file: git merges it silently, but the reviewer
    approved the PR's bytes, so the refresh refuses instead of shipping a file nobody reviewed."""
    five = "line one\nline two\nline three\nline four\nline five\n"
    path = "data/firmware/shared/firmware.md"
    clone, head = _repo(tmp_path, seed_extra={path: five}, pr_extra={path: five.replace("line one", "PR one")},
                        main_extra={path: five.replace("line five", "main five")})
    r = review_refresh.refresh(_pr(head), git=_git(clone), gh=_gh(), now=NOW)
    assert r["status"] == "skipped" and r["why"] == f"catalog file changed by the merge: {path}"


def test_the_prs_own_topics_yield_row_survives_the_refresh(tmp_path):
    """2026-11-19 (stall:topics): the tick that produced appends its yield row in its own PR, so a jr-review
    PR conflicts on docs/telemetry/yield.jsonl; taking main's copy there dropped the only row saying the lane
    produced (#1828 lost 2026-11-18T07:00Z, #1875 lost 2026-11-19T07:00Z). The refresh keeps main's rows and
    adds the PR's rows main lacks."""
    path = "docs/telemetry/yield.jsonl"

    def row(tick, stage, produced=0):
        return json.dumps({"produced": produced, "stage": stage, "tick": tick, "units": 2}, sort_keys=True) + "\n"

    seed = row("2026-11-19T05:00Z", "admit_topics")
    clone, head = _repo(tmp_path, seed_extra={path: seed},
                        pr_extra={path: seed + row("2026-11-19T07:00Z", "admit_topics", produced=2)},
                        main_extra={path: seed + row("2026-11-19T08:00Z", "admit_topics")})
    r = review_refresh.refresh(_pr(head), git=_git(clone), gh=_gh(), now=NOW)
    assert r["status"] == "refreshed", r
    _sh(clone, "fetch", "-q", "origin")
    got = _sh(clone, "show", f"origin/jr/tick-x:{path}") + "\n"
    assert got == seed + row("2026-11-19T07:00Z", "admit_topics", produced=2) + row("2026-11-19T08:00Z", "admit_topics")


def _yield_row(tick, stage, produced=0):
    return json.dumps({"tick": tick, "stage": stage, "units": 2, "produced": produced}, sort_keys=True) + "\n"


def test_the_prs_own_yield_rows_survive_the_refresh(tmp_path):
    """2026-11-19 (stall:firmware, incident 0cf1acb95f79): a refresh took main's yield.jsonl, so the rows of
    the PR's own tick — the boardmap recipes it is the review PR for — never reached main, and the firmware
    lane read 0 produced over 24 ticks while it had produced 9 recipes in 7 of them."""
    seed = _yield_row("2026-11-18T05:00Z", "boardmap")
    pr_row = _yield_row("2026-11-18T06:00Z", "boardmap", produced=1)
    main_row = _yield_row("2026-11-18T08:00Z", "boardmap")
    clone, head = _repo(tmp_path, seed_extra={"docs/telemetry/yield.jsonl": seed},
                        pr_extra={"docs/telemetry/yield.jsonl": seed + pr_row},
                        main_extra={"docs/telemetry/yield.jsonl": seed + main_row})
    r = review_refresh.refresh(_pr(head), git=_git(clone), gh=_gh(), now=NOW)
    assert r["status"] == "refreshed", r
    _sh(clone, "fetch", "-q", "origin")
    assert _sh(clone, "show", "origin/jr/tick-x:docs/telemetry/yield.jsonl") + "\n" == seed + pr_row + main_row


def test_an_auto_route_tick_pr_is_refreshed_when_the_tick_asks_for_any_route(tmp_path):
    """2026-11-25, #2081: an auto-route (unlabelled) tick PR conflicted and halted every tick."""
    clone, head = _repo(tmp_path)
    assert review_refresh.refresh(_pr(head, labels=()), git=_git(clone), gh=_gh(), now=NOW)["status"] == "skipped"
    r = review_refresh.refresh(_pr(head, labels=()), git=_git(clone), gh=_gh(), now=NOW, any_route=True)
    assert r["status"] == "refreshed", r
