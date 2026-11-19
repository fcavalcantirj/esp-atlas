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
