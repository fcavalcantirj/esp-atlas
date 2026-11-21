"""scripts/demand_guard.py — a demand PR changes exactly what its work item says. Throwaway git repos:
a base commit with the queue, the receipts and a seed board, then the PR's commits on a
jr/research-<KEY> branch, written the way jr/work_record.py writes them. No network."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import demand_guard as dg

KEY = "pam-aa11bb22cc33dd44ee55ff66"
BRANCH = f"jr/research-{KEY}"
PR = "https://github.com/o/r/pull/7"
BOARD = """---
id: {bid}
type: board
brand: freenove
name: {name}
soc: esp32
sources:
- field: '*'
  url: https://github.com/Freenove/{bid}
  verified: '2026-11-17'
---

Body.
"""


def _git(repo: Path, *args: str) -> str:
    p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, (args, p.stderr)
    return p.stdout


def _commit(repo: Path, subject: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", subject)


def _validation(expected=("freenove-esp32-wrover",), forbidden=("freenove-esp32-wroom",)):
    return {"verified_on": "2026-11-17", "forbidden_ids": list(forbidden), "verification_kind": "catalog_part",
            "validated_by": "jr-demand-executor run 1", "primary_sources": ["https://docs.freenove.com/x"],
            "expected_ids": list(expected), "identity_verified": True, "term_key": "freenove esp32 wrover starter kit"}


def _queue(status="validated", links=(), other_status="new"):
    return {"version": 1, "max_new_per_day": 1, "reopen_after_days": 14, "candidates": {
        KEY: {"term": "Freenove ESP32-WROVER Starter Kit", "source": "pam_feed", "status": status,
              "first_seen": "2026-11-17", "history": [], "linked_work": list(links), "validation": _validation()},
        "pam-other": {"term": "Other Kit", "source": "pam_feed", "status": other_status, "first_seen": "2026-11-16",
                      "history": [], "linked_work": []}}}


def _receipts(phase="research", pr_url=None, links=(), other_state="delivered"):
    r = {"key": KEY, "branch": BRANCH, "term": "Freenove ESP32-WROVER Starter Kit", "phase": phase, "state": "reserved",
         "started_on": "2026-11-17", "source": "pam_feed", "linked_work": list(links)}
    if pr_url:
        r["pr_url"] = pr_url
    return {"version": 1, "receipts": [r, {"key": "pam-other", "branch": "jr/research-pam-other", "term": "Other Kit",
                                           "phase": "author", "state": other_state, "started_on": "2026-11-16",
                                           "source": "pam_feed", "linked_work": []}]}


def _write(repo: Path, rel: str, text: str) -> None:
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def repo(tmp_path):
    """main at the base commit; the PR branch checked out, with the link commit and the record commit."""
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _write(r, dg.QUEUE, json.dumps(_queue(), indent=1))
    _write(r, dg.RECEIPTS, json.dumps(_receipts(), indent=1))
    _write(r, "docs/demand/pam-leads.json", "{}")
    _write(r, "data/boards/freenove/freenove-fnk0104a/board.md", BOARD.format(bid="freenove-fnk0104a", name="FNK0104A"))
    _commit(r, "base")
    _git(r, "checkout", "-q", "-b", BRANCH)
    _write(r, "data/boards/freenove/freenove-esp32-wrover/board.md", BOARD.format(bid="freenove-esp32-wrover", name="ESP32-WROVER"))
    _commit(r, f"feat(catalog): Freenove ESP32-WROVER board (demand work {KEY})")
    _write(r, dg.QUEUE, json.dumps(_queue(status="linked", links=[PR]), indent=1))
    _write(r, dg.RECEIPTS, json.dumps(_receipts(phase="author", pr_url=PR, links=[PR]), indent=1))
    _commit(r, f"chore(demand): link work {KEY} to draft PR #7")
    return r


def run(repo, **kw):
    args = dict(base="main", head="HEAD", branch=BRANCH, pr_url=PR)
    args.update(kw)
    return dg.check(repo, **args)


def test_the_real_shape_of_a_demand_pr_passes_every_rule(repo):
    problems, lines = run(repo)
    assert problems == [], problems
    assert any("R5 records added: ['freenove-esp32-wrover']" in ln for ln in lines)
    assert any("R6 demand commits: 1, all chore(demand):" in ln for ln in lines)


def test_main_exit_codes_follow_the_verdict(repo, capsys):
    assert dg.main(["--repo", str(repo), "--base", "main", "--branch", BRANCH, "--pr-url", PR]) == 0
    assert "✓ demand guard" in capsys.readouterr().out
    assert dg.main(["--repo", str(repo), "--base", "main", "--branch", "feat/not-demand"]) == 2


def test_r1_another_demand_file_changed(repo):
    _write(repo, "docs/demand/pam-leads.json", '{"leads": []}')
    _commit(repo, "chore(demand): refresh leads")
    problems, _ = run(repo)
    assert any(p.startswith("R1") and "pam-leads.json" in p for p in problems)


def test_r2_the_candidate_must_link_exactly_this_pr(repo):
    assert any(p.startswith("R2") for p in run(repo, pr_url="https://github.com/o/r/pull/8")[0])
    q = _queue(status="linked", links=[PR, "https://github.com/o/r/pull/9"])
    _write(repo, dg.QUEUE, json.dumps(q, indent=1))
    _commit(repo, "chore(demand): second link")
    assert any(p.startswith("R2") and "not exactly this PR" in p for p in run(repo)[0])


def test_r2_an_unreadable_validation_fails(repo):
    q = _queue(status="linked", links=[PR])
    q["candidates"][KEY]["validation"]["expected_ids"] = []
    _write(repo, dg.QUEUE, json.dumps(q, indent=1))
    _commit(repo, "chore(demand): broken validation")
    assert any(p.startswith("R2") and "readable validation" in p for p in run(repo)[0])


def test_r3_the_receipt_must_name_the_same_pr_in_the_author_phase(repo):
    _write(repo, dg.RECEIPTS, json.dumps(_receipts(phase="research", pr_url="https://github.com/o/r/pull/8", links=[PR]), indent=1))
    _commit(repo, "chore(demand): odd receipt")
    problems = run(repo)[0]
    assert any("R3" in p and "pr_url" in p for p in problems) and any("R3" in p and "phase" in p for p in problems)


def test_r4_touching_another_candidate_or_receipt_fails(repo):
    _write(repo, dg.QUEUE, json.dumps(_queue(status="linked", links=[PR], other_status="closed"), indent=1))
    _commit(repo, "chore(demand): sneaky close of another candidate")
    assert any(p.startswith("R4") and "candidate other than" in p for p in run(repo)[0])
    _write(repo, dg.QUEUE, json.dumps(_queue(status="linked", links=[PR]), indent=1))
    _write(repo, dg.RECEIPTS, json.dumps(_receipts(phase="author", pr_url=PR, links=[PR], other_state="abandoned"), indent=1))
    _commit(repo, "chore(demand): sneaky settle of another receipt")
    assert any(p.startswith("R4") and "receipt other than" in p for p in run(repo)[0])


def test_r5_the_records_added_must_be_exactly_the_expected_ids(repo):
    _write(repo, "data/boards/freenove/freenove-extra/board.md", BOARD.format(bid="freenove-extra", name="Extra"))
    _commit(repo, "feat(catalog): one more board")
    assert any(p.startswith("R5") and "!= expected_ids" in p for p in run(repo)[0])


def test_r5_a_forbidden_sibling_anywhere_in_the_change_fails(repo):
    _write(repo, "data/boards/freenove/freenove-esp32-wroom/board.md", BOARD.format(bid="freenove-esp32-wroom", name="WROOM"))
    _commit(repo, "feat(catalog): the sibling too")
    problems = run(repo)[0]
    assert any(p.startswith("R5") and "forbidden" in p and "freenove-esp32-wroom" in p for p in problems)


def test_r5_editing_an_existing_record_is_out_of_scope(repo):
    _write(repo, "data/boards/freenove/freenove-fnk0104a/board.md", BOARD.format(bid="freenove-fnk0104a", name="FNK0104A v2"))
    _commit(repo, "fix(catalog): touch the seed")
    assert any(p.startswith("R5") and "beyond the expected records" in p for p in run(repo)[0])


def test_r6_a_demand_file_changed_outside_a_chore_demand_commit_fails(repo):
    _write(repo, dg.RECEIPTS, json.dumps(_receipts(phase="author", pr_url=PR, links=[PR]), indent=1) + "\n")
    _commit(repo, "feat(catalog): also tweak the receipts by hand")
    assert any(p.startswith("R6") and "feat(catalog): also tweak" in p for p in run(repo)[0])


def test_key_of_reads_the_branch_name_only():
    assert dg.key_of(BRANCH) == KEY and dg.key_of(f"refs/heads/{BRANCH}") == KEY
    assert dg.key_of("jr/research-") is None and dg.key_of("main") is None and dg.key_of(None) is None


# --- R6 and merges of main (2026-11-19) -----------------------------------------------------------------
# #1846 was refreshed with main ("Merge branch 'main' into jr/research-…") and demand-guard went red on that
# commit's subject: main had changed docs/demand since the branch was cut, so the merge touches it. Every
# refresh (a person's Update branch, Jr's chores, a conflict fix) and GitHub's own test merge hit the same wall.

def _merge(repo: Path, what: str, subject: str, *extra: str) -> None:
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", *extra, "-m", subject, what)


def _main_moves(repo: Path) -> None:
    _git(repo, "checkout", "-q", "main")
    _write(repo, "docs/demand/pam-leads.json", '{"refreshed": true}')
    _commit(repo, "chore(demand): daily leads refresh")
    _git(repo, "checkout", "-q", BRANCH)


def test_r6_a_merge_of_main_that_carries_mains_demand_changes_is_not_a_hand_edit(repo):
    _main_moves(repo)
    _merge(repo, "main", f"Merge branch 'main' into {BRANCH}")
    problems, lines = run(repo)
    assert problems == []
    assert any("R6 demand commits: 1, all chore(demand):" in ln and "1 clean merge of main not counted" in ln for ln in lines)


def test_r6_githubs_own_test_merge_of_the_pr_into_a_moved_main_passes(repo):
    _main_moves(repo)
    head = _git(repo, "rev-parse", "HEAD").strip()
    _git(repo, "checkout", "-q", "--detach", "main")
    _merge(repo, head, f"Merge {head} into {_git(repo, 'rev-parse', 'main').strip()}")     # refs/pull/N/merge
    assert run(repo)[0] == []


def test_r6_a_hand_edit_hidden_in_a_merge_of_main_is_still_caught_by_the_content_rules(repo):
    _main_moves(repo)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "--no-commit", "main")
    _write(repo, dg.QUEUE, json.dumps(_queue(status="linked", links=[PR], other_status="closed"), indent=1))
    _commit(repo, f"Merge branch 'main' into {BRANCH}")
    assert any(p.startswith("R4") for p in run(repo)[0])


def _merge_main_with_an_edit(repo: Path, receipts=None, queue=None, subject=None) -> None:
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-ff", "--no-commit", "main")
    if receipts is not None:
        _write(repo, dg.RECEIPTS, json.dumps(receipts, indent=1))
    if queue is not None:
        _write(repo, dg.QUEUE, json.dumps(queue, indent=1))
    _commit(repo, subject or f"Merge branch 'main' into {BRANCH}")


def test_r6_an_edit_of_this_items_own_receipt_typed_into_a_merge_of_main_is_a_hand_edit(repo):
    # review BLOCK of #1872: R1-R5 accept any readable receipt in the author phase, so nothing else stops this
    _main_moves(repo)
    broken = _receipts(phase="author", pr_url=PR, links=[PR])
    broken["receipts"][0]["started_on"] = "yesterday"
    _merge_main_with_an_edit(repo, receipts=broken)
    assert any(p.startswith("R6") and "Merge branch 'main'" in p for p in run(repo)[0])


def test_r6_a_promise_rewritten_inside_a_merge_of_main_is_a_hand_edit(repo):
    _main_moves(repo)
    q = _queue(status="linked", links=[PR])
    text = json.dumps(q).replace("freenove-esp32-wroom", "freenove-esp32-nothing")       # the forbidden sibling
    assert text != json.dumps(q)
    _merge_main_with_an_edit(repo, queue=json.loads(text))
    assert any(p.startswith("R6") for p in run(repo)[0])


def test_r6_a_conflict_in_the_demand_files_resolved_by_hand_is_a_hand_edit(repo):
    _git(repo, "checkout", "-q", "main")
    _write(repo, dg.RECEIPTS, json.dumps(_receipts(phase="research", other_state="abandoned"), indent=1))
    _write(repo, dg.QUEUE, json.dumps(_queue(status="linked", links=["https://example.org/other"]), indent=1))
    _commit(repo, "chore(demand): main rewrites the same lines")
    _git(repo, "checkout", "-q", BRANCH)
    p = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "merge", "--no-ff", "main"], cwd=repo,
                       capture_output=True, text=True)
    assert p.returncode != 0                                              # a real conflict
    _write(repo, dg.QUEUE, json.dumps(_queue(status="linked", links=[PR]), indent=1))
    _write(repo, dg.RECEIPTS, json.dumps(_receipts(phase="author", pr_url=PR, links=[PR], other_state="abandoned"), indent=1))
    _commit(repo, f"Merge branch 'main' into {BRANCH}")
    assert any(p.startswith("R6") and "Merge branch 'main'" in p for p in run(repo)[0])


def test_r6_an_octopus_or_a_merge_onto_an_old_main_commit_with_an_edit_gets_no_exemption(repo):
    old_main = _git(repo, "rev-parse", "main").strip()
    _main_moves(repo)
    _git(repo, "checkout", "-q", "-b", "other", old_main)
    _write(repo, "unrelated.txt", "x")
    _commit(repo, "chore: unrelated")
    _git(repo, "checkout", "-q", BRANCH)
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "merge", "-q", "--no-commit", "main", "other")
    _write(repo, dg.RECEIPTS, json.dumps(_receipts(phase="author", pr_url=PR, links=[PR]), indent=1) + "\n")
    _commit(repo, "Merge branches 'main' and 'other'")
    assert any(p.startswith("R6") and "Merge branches" in p for p in run(repo)[0])


def test_r6_a_merge_of_anything_but_main_gets_no_exemption(repo):
    _git(repo, "checkout", "-q", "-b", "side")
    _write(repo, dg.RECEIPTS, json.dumps(_receipts(phase="author", pr_url=PR, links=[PR]), indent=1) + "\n")
    _commit(repo, "feat(catalog): hand tweak on a side branch")
    _git(repo, "checkout", "-q", BRANCH)
    _write(repo, "docs/demand/note.txt", "x")
    _commit(repo, "chore(demand): unrelated")
    _merge(repo, "side", "Merge branch 'side'")
    bad = next(p for p in run(repo)[0] if p.startswith("R6"))
    assert "hand tweak on a side branch" in bad and "Merge branch 'side'" in bad


def test_r6_an_ordinary_commit_sitting_directly_on_main_gets_no_exemption(repo):
    # its only parent IS main's history; one parent is never a merge
    _git(repo, "checkout", "-q", "-b", "fresh", "main")
    _write(repo, dg.RECEIPTS, json.dumps(_receipts(phase="author", pr_url=PR, links=[PR]), indent=1))
    _commit(repo, "feat(catalog): receipts edited by hand as the first commit")
    assert any(p.startswith("R6") and "edited by hand as the first commit" in p for p in run(repo, branch=BRANCH)[0])


# --- a settle-only PR (2026-11-21) --------------------------------------------------------------------------
# #1968 settled the 'esp32 tenstar' work item as abandoned (a store brand, no one board): the receipt went
# reserved -> abandoned with its reason, the queue candidate with that term went closed with the same outcome,
# and nothing under data/ changed. The guard judged it as a delivery (R2 'queue has no candidate <KEY>') and
# failed it, so an abandoned item could never close by machine.

TERM = "Freenove ESP32-WROVER Starter Kit"
REASON = "Not catalog content: a store brand that resells many boards"


def _settle_repo(tmp_path, *, state="abandoned", queue_status="closed", other_change=False, data_change=False,
                 subject="chore(demand): settle {key} abandoned", reason=REASON, outcome_status=None):
    r = tmp_path / "settle"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    q = {"version": 1, "candidates": {"freenove esp32 wrover starter kit": {"term": TERM, "status": "new", "history": [], "linked_work": []},
                                     "other kit": {"term": "Other Kit", "status": "new", "history": [], "linked_work": []}}}
    rc = _receipts()
    _write(r, dg.QUEUE, json.dumps(q, indent=1))
    _write(r, dg.RECEIPTS, json.dumps(rc, indent=1))
    _commit(r, "base")
    _git(r, "checkout", "-q", "-b", BRANCH)
    cand = q["candidates"]["freenove esp32 wrover starter kit"]
    cand.update(status=queue_status, closed_on="2026-11-21", outcome={"status": outcome_status or state, "reason": reason})
    if other_change:      # closed exactly like a settle, so only the term rule can tell it is the wrong item
        q["candidates"]["other kit"].update(status="closed", closed_on="2026-11-21", outcome={"status": state, "reason": reason})
    rc["receipts"][0].update(state=state, resolution={"status": state, "reason": reason}, last_attempt_on="2026-11-21")
    _write(r, dg.QUEUE, json.dumps(q, indent=1))
    _write(r, dg.RECEIPTS, json.dumps(rc, indent=1))
    if data_change:
        _write(r, "data/boards/freenove/freenove-esp32-wrover/board.md", BOARD.format(bid="freenove-esp32-wrover", name="X"))
    _commit(r, subject.format(key=KEY))
    return r


def _settle_check(r):
    return dg.check(r, base="main", head="HEAD", branch=BRANCH, pr_url=PR)


@pytest.mark.parametrize("state", ["abandoned", "rejected"])
def test_a_pr_that_only_settles_its_own_item_passes(tmp_path, state):
    problems, lines = _settle_check(_settle_repo(tmp_path, state=state))
    assert problems == [], problems
    assert any(ln.startswith(f"S1 settle {KEY}: reserved -> {state}") for ln in lines)


@pytest.mark.parametrize("kw, rule", [
    (dict(data_change=True), "S1"),                       # a settle never adds or edits catalog data
    (dict(other_change=True), "S3"),                      # another candidate changed
    (dict(queue_status="linked"), "S3"),                  # the candidate is not closed
    (dict(outcome_status="rejected"), "S3"),              # the candidate's outcome disagrees with the receipt
    (dict(reason=""), "S2"),                              # no reason recorded
    (dict(subject="settle it by hand"), "R6"),            # not written by work_record (subject)
])
def test_anything_beyond_a_clean_settle_fails(tmp_path, kw, rule):
    problems, _ = _settle_check(_settle_repo(tmp_path, **kw))
    assert any(p.startswith(rule) for p in problems), (kw, problems)


def test_a_delivery_pr_is_judged_exactly_as_before(repo):
    problems, lines = dg.check(repo, base="main", head="HEAD", branch=BRANCH, pr_url=PR)
    assert not any(ln.startswith("S1") for ln in lines)
