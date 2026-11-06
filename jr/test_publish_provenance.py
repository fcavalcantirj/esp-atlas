"""The worktree's reported base revision is the tree this run actually mined (PR 1483, blocker A).

publish.add_worktree used to detach at `origin/main` and then read `origin/main` AGAIN for
`base_sha`: a concurrent fetch moving origin/main between the two left the worktree at A while the
run reported B, and the demand closure asked git whether a merge is an ancestor of B — a revision
this run never mined. These tests race a REAL git repository in tmp_path (no network, no host
state): a hook moves origin/main to B right after the first command that names it.

Run: cd jr && python3 -m pytest test_publish_provenance.py -v
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

import demand_run
import publish
from test_demand_broker import SLUG, snapshot_miner
from test_demand_closure import MERGE_SHA, NEXT_NOW, PAM_RAW, QUEUE_RAW, RECEIPTS_RAW, SNAP
from test_demand_run import git_ok, norm_calls, recorder
from test_demand_run_closure import gh_all


def _git_in(cwd):
    def git(*args):
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return git


@pytest.fixture
def racing_clone(tmp_path, monkeypatch):
    """(clone, A, B): origin/main is A; B is a later commit a concurrent fetch can land."""
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    for var in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(var, "jr-test")
    for var in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(var, "jr-test@example.invalid")
    origin = tmp_path / "origin"
    demand = origin / "docs" / "demand"
    demand.mkdir(parents=True)
    (demand / "research-queue.json").write_bytes(QUEUE_RAW)
    (demand / "work-receipts.json").write_bytes(RECEIPTS_RAW)
    (demand / "pam-leads.json").write_bytes(PAM_RAW)
    git = _git_in(origin)
    git("init", "-q", "-b", "main")
    git("add", "-A")
    git("commit", "-q", "-m", "A: the mined tree")
    git("checkout", "-q", "-b", "next")
    git("commit", "-q", "--allow-empty", "-m", "B: lands after the resolve")
    git("checkout", "-q", "main")
    subprocess.run(["git", "clone", "-q", str(origin), str(tmp_path / "clone")], check=True,
                   capture_output=True)
    clone = _git_in(tmp_path / "clone")
    a = clone("rev-parse", "origin/main").stdout.strip()
    b = clone("rev-parse", "origin/next").stdout.strip()
    assert a and b and a != b
    return tmp_path / "clone", a, b


def racing(real, b):
    """`real` git, but a concurrent fetch moves origin/main to `b` right after the first command
    (other than the fetch itself) that names origin/main."""
    moved = []

    def git(*args):
        p = real(*args)
        if not moved and args[:1] != ("fetch",) and any("origin/main" in str(a) for a in args):
            real("update-ref", "refs/remotes/origin/main", b)
            moved.append(args)
        return p

    git.moved = moved
    return git


def test_a_fetch_racing_the_worktree_add_never_reports_an_unmined_base(racing_clone, tmp_path):
    clone, a, b = racing_clone
    real = _git_in(clone)
    git = racing(real, b)
    wt = publish.add_worktree(git=git, root=tmp_path / "wt")
    try:
        head = real("-C", str(wt.path), "rev-parse", "HEAD").stdout.strip()
        assert git.moved and real("rev-parse", "origin/main").stdout.strip() == b   # the race happened
        assert head == a and wt.base_sha == head
        assert wt.base_sha != b
    finally:
        publish.remove_worktree(wt, git=real)


def test_a_worktree_whose_head_is_not_the_resolved_base_fails_closed(tmp_path):
    d = tmp_path / "wt"
    d.mkdir()
    git = recorder({("rev-parse", "--verify", "origin/main^{commit}"): (0, "a" * 40 + "\n"),
                    ("rev-parse", "--verify", "HEAD^{commit}"): (0, "b" * 40 + "\n")})
    with pytest.raises(RuntimeError, match="HEAD"):
        publish.add_worktree(git=git, root=d)
    assert not d.exists()                                           # never leak the temp dir
    assert ("worktree", "remove", "--force", str(d)) in norm_calls(git)


def test_an_unresolvable_origin_main_adds_no_worktree(tmp_path):
    git = recorder({("rev-parse",): (128, "")})
    with pytest.raises(RuntimeError, match="origin/main"):
        publish.add_worktree(git=git, root=tmp_path / "wt")
    assert all(c[:2] != ("worktree", "add") for c in norm_calls(git))


def test_the_closure_asks_ancestry_only_of_the_mined_revision(racing_clone, tmp_path):
    """The whole daily run over a racing clone: the worktree, its base and its status are real git;
    the ancestry question, staging and the push go to a recorder. Every ancestry question names A,
    the tree this run mined — never B."""
    clone, a, b = racing_clone
    real, rec = _git_in(clone), git_ok()
    raced = racing(real, b)

    def git(*args):
        norm = args[2:] if args[:1] == ("-C",) else args
        if norm[:1] in {("fetch",), ("worktree",), ("rev-parse",), ("status",), ("update-ref",)}:
            return raced(*args)
        return rec(*args)

    res = demand_run.run(git=git, gh=gh_all(), miner=snapshot_miner(SNAP, queue=json.loads(QUEUE_RAW)),
                         now=NEXT_NOW, root=tmp_path / "wt", repo_slug=SLUG, python="/venv/bin/python")
    assert raced.moved and res.aborted == ""
    asked = [c for c in norm_calls(rec) if c[:2] == ("merge-base", "--is-ancestor")]
    assert asked and all(c == ("merge-base", "--is-ancestor", MERGE_SHA, a) for c in asked)
    assert not any(b in str(arg) for c in norm_calls(rec) for arg in c)
