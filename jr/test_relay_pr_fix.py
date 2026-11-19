"""The relay check in PR-fix mode (SPEC-jr-self-heal.md §1d): a delegate that fixed a PR in place pushes to
the PR's own branch, so the check judges only the delegate's commits on top of the PR head — a merge of
main counts only its conflict resolution (`git show --remerge-diff`), never the lines main brings — and
the push must be a fast-forward of that head. Throwaway git repos."""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

import ci_watch as cw

ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}


def git(repo, *a, check=True):
    return subprocess.run(["git", *a], cwd=repo, env=ENV, capture_output=True, text=True, check=check).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """main moved 400 lines in big.txt; the PR changed f.txt's line 2, main changed it too: a conflict."""
    r = tmp_path / "r"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "f.txt").write_text("a\nb\nc\n")
    (r / "big.txt").write_text("".join(f"{i}\n" for i in range(50)))
    git(r, "add", "."), git(r, "commit", "-qm", "base")
    git(r, "checkout", "-qb", "pr")
    (r / "f.txt").write_text("a\nPR\nc\n")
    git(r, "commit", "-qam", "pr")
    git(r, "checkout", "-q", "main")
    (r / "f.txt").write_text("a\nMAIN\nc\n")
    (r / "big.txt").write_text("".join(f"{i}\n" for i in range(450)))
    git(r, "commit", "-qam", "main")
    git(r, "checkout", "-q", "pr")
    return r


def _resolve(r, text="a\nRESOLVED\nc\n"):
    git(r, "merge", "-q", "main", check=False)
    (r / "f.txt").write_text(text)
    git(r, "add", "f.txt", "big.txt"), git(r, "commit", "-qm", "merge main")
    return git(r, "rev-parse", "HEAD")


def test_a_merge_counts_only_its_conflict_resolution(repo):
    head = git(repo, "rev-parse", "HEAD")
    tip = _resolve(repo)
    assert cw.relay_problems(repo, head, tip, pr_fix=True, main_ref="main") == []
    assert any("more than" in p for p in cw.relay_problems(repo, head, tip))     # the heal-mode rule would refuse


def test_a_push_that_is_not_a_fast_forward_of_the_pr_head_is_refused(repo):
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-q", "main")
    other = git(repo, "rev-parse", "HEAD")
    assert any("fast-forward" in p for p in cw.relay_problems(repo, head, other, pr_fix=True, main_ref="main"))


def test_own_commits_on_top_keep_every_heal_rule(repo):
    head = git(repo, "rev-parse", "HEAD")
    _resolve(repo)
    (repo / "data").mkdir()
    (repo / "data" / "x.md").write_text("x\n")
    git(repo, "add", "data/x.md"), git(repo, "commit", "-qm", "data")
    tip = git(repo, "rev-parse", "HEAD")
    assert any("touches data/" in p for p in cw.relay_problems(repo, head, tip, pr_fix=True, main_ref="main"))


def test_a_resolution_that_is_large_is_still_counted(repo):
    head = git(repo, "rev-parse", "HEAD")
    tip = _resolve(repo, "a\n" + "".join(f"r{i}\n" for i in range(400)) + "c\n")
    assert any("more than" in p for p in cw.relay_problems(repo, head, tip, pr_fix=True, main_ref="main"))


def test_the_cli_takes_pr_fix(repo):
    head = git(repo, "rev-parse", "HEAD")
    tip = _resolve(repo)
    assert cw.main(["relay-check", "--repo", str(repo), "--base", head, "--head", tip, "--pr-fix", "--main", "main"]) == 0


# --- review BLOCK of #1857 (2026-11-19): a merge whose second parent is NOT main hid a data edit and a test
#     deletion from --remerge-diff (clean merge → empty remerge-diff) ---------------------------------------

def test_a_merge_of_a_side_branch_cannot_smuggle_changes(repo):
    head = git(repo, "rev-parse", "HEAD")
    git(repo, "checkout", "-qb", "side")
    (repo / "data").mkdir()
    (repo / "data" / "b.json").write_text("{}\n")
    git(repo, "add", "data/b.json"), git(repo, "commit", "-qm", "side")
    git(repo, "checkout", "-q", "pr")
    git(repo, "merge", "-q", "--no-ff", "side", "-m", "merge side")
    tip = git(repo, "rev-parse", "HEAD")
    problems = cw.relay_problems(repo, head, tip, pr_fix=True, main_ref="main")
    assert any("not on main" in p for p in problems), problems


def test_an_octopus_merge_is_refused(repo):
    head = git(repo, "rev-parse", "HEAD")
    for b in ("o1", "o2"):
        git(repo, "checkout", "-qb", b, head)
        (repo / f"{b}.txt").write_text(b)
        git(repo, "add", f"{b}.txt"), git(repo, "commit", "-qm", b)
    git(repo, "checkout", "-q", "pr")
    git(repo, "merge", "-q", "--no-ff", "o1", "o2", "-m", "octopus")
    tip = git(repo, "rev-parse", "HEAD")
    assert any("octopus" in p for p in cw.relay_problems(repo, head, tip, pr_fix=True, main_ref="main"))


def test_a_merge_of_main_still_passes_with_the_main_check(repo):
    head = git(repo, "rev-parse", "HEAD")
    tip = _resolve(repo)
    assert cw.relay_problems(repo, head, tip, pr_fix=True, main_ref="main") == []
