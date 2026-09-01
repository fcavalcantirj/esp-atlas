"""Tests for jr/drain_pr.py — the PR-orchestrating cron entrypoint around drain.run_drain()
(JR.md Law 3: bot proposes, humans dispose — Jr writes PRs only, never `main`).

Covers: (a) a non-empty `authored` list creates a fresh jr-drain-<UTC timestamp> branch, stages
only the new data/firmware + data/recipes paths, commits with a Conventional Commit subject,
pushes, and opens a `gh pr create` whose body lists every authored id with its source URL and
states the guard is green; (b) an empty `authored` list touches git/gh not at all and just
prints a terse line; (c) no git call, ever, references `main` — the only "main" reference in the
whole flow is `gh pr create --base main`, which is not a git write. `git`, `gh`, and `run_drain`
are always injected fakes: no real subprocgit call, and no real network.

Run: cd jr && python3 -m pytest test_drain_pr.py -v
"""
from __future__ import annotations
import re
import shutil
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

import drain_pr
import tools

REPO = tools.REPO
FIXTURE_IDS = ["zzz-test-fixture-drain-pr-one", "zzz-test-fixture-drain-pr-two"]
FIXTURE_URLS = {
    "zzz-test-fixture-drain-pr-one": "https://github.com/octocat/fixture-one",
    "zzz-test-fixture-drain-pr-two": "https://github.com/octocat/fixture-two",
}


class FakeProc(SimpleNamespace):
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def _recorder(**extra_returns):
    calls = []

    def fn(*args):
        calls.append(args)
        return FakeProc(**extra_returns)

    fn.calls = calls
    return fn


@pytest.fixture
def fixture_firmware():
    """Write real (throwaway) firmware.md files under data/firmware/<id>/ so drain_pr's PR-body
    builder can read a real `url` field off disk, exactly like a real drain run would leave
    behind. Cleaned up after every test, pass or fail."""
    for fid in FIXTURE_IDS:
        d = tools.FIRMWARE_DIR / fid
        d.mkdir(parents=True, exist_ok=True)
        (d / "firmware.md").write_text(
            f"---\nid: {fid}\nname: Zzz Test Fixture\nurl: {FIXTURE_URLS[fid]}\n"
            f"category: multi\nsocs: [esp32-s3]\n---\n\nA fixture firmware.\n"
        )
    yield
    for fid in FIXTURE_IDS:
        shutil.rmtree(tools.FIRMWARE_DIR / fid, ignore_errors=True)


NOW = datetime(2026, 9, 1, 8, 46, 0, tzinfo=timezone.utc)


# ─────────────────────────── (a) authored non-empty: branch + commit + PR ───────────────────────────

def test_authored_creates_branch_named_by_utc_timestamp(fixture_firmware):
    git, gh = _recorder(), _recorder(stdout="https://github.com/x/y/pull/1\n")

    drain_pr.main(run_drain=lambda: {"authored": FIXTURE_IDS}, git=git, gh=gh, now=NOW)

    checkout = git.calls[0]
    assert checkout[:2] == ("checkout", "-B")
    assert checkout[2] == "jr-drain-20260901-0846"


def test_authored_stages_only_new_firmware_and_recipe_paths(fixture_firmware):
    git, gh = _recorder(), _recorder(stdout="https://github.com/x/y/pull/1\n")

    drain_pr.main(run_drain=lambda: {"authored": FIXTURE_IDS}, git=git, gh=gh, now=NOW)

    add_call = next(c for c in git.calls if c[0] == "add")
    staged = set(add_call[1:])
    assert staged == {f"data/firmware/{fid}" for fid in FIXTURE_IDS}


def test_authored_commits_with_conventional_commit_subject(fixture_firmware):
    git, gh = _recorder(), _recorder(stdout="https://github.com/x/y/pull/1\n")

    drain_pr.main(run_drain=lambda: {"authored": FIXTURE_IDS}, git=git, gh=gh, now=NOW)

    commit_call = next(c for c in git.calls if c[0] == "commit")
    assert commit_call[1] == "-m"
    assert commit_call[2] == "feat(firmware): jr drain batch of 2 new entries"


def test_authored_pushes_the_drain_branch(fixture_firmware):
    git, gh = _recorder(), _recorder(stdout="https://github.com/x/y/pull/1\n")

    drain_pr.main(run_drain=lambda: {"authored": FIXTURE_IDS}, git=git, gh=gh, now=NOW)

    push_call = next(c for c in git.calls if c[0] == "push")
    assert "jr-drain-20260901-0846" in push_call


def test_authored_opens_pr_with_every_id_and_source_url_in_body(fixture_firmware):
    git, gh = _recorder(), _recorder(stdout="https://github.com/x/y/pull/1\n")

    drain_pr.main(run_drain=lambda: {"authored": FIXTURE_IDS}, git=git, gh=gh, now=NOW)

    pr_call = next(c for c in gh.calls if c[:2] == ("pr", "create"))
    body = pr_call[pr_call.index("--body") + 1]
    for fid in FIXTURE_IDS:
        assert fid in body
        assert FIXTURE_URLS[fid] in body
    assert "guard" in body.lower() and "green" in body.lower()
    assert pr_call[pr_call.index("--base") + 1] == "main"


def test_authored_returns_a_report_with_the_pr_result(fixture_firmware):
    git, gh = _recorder(), _recorder(stdout="https://github.com/x/y/pull/1\n")

    result = drain_pr.main(run_drain=lambda: {"authored": FIXTURE_IDS}, git=git, gh=gh, now=NOW)

    assert result["authored"] == FIXTURE_IDS
    assert result["pr"]["pr_ok"] is True
    assert result["pr"]["branch"] == "jr-drain-20260901-0846"


# ─────────────────────────── (b) authored empty: no branch, no commit, no PR ───────────────────────────

def test_empty_authored_touches_no_git_or_gh(capsys):
    git, gh = _recorder(), _recorder()

    result = drain_pr.main(run_drain=lambda: {"authored": []}, git=git, gh=gh, now=NOW)

    assert git.calls == []
    assert gh.calls == []
    assert result == {"authored": [], "pr": None}


def test_empty_authored_prints_a_terse_no_new_entries_line(capsys):
    git, gh = _recorder(), _recorder()

    drain_pr.main(run_drain=lambda: {"authored": []}, git=git, gh=gh, now=NOW)

    out = capsys.readouterr().out.strip()
    assert out.count("\n") == 0          # one line, terse
    assert "no new entries" in out.lower()


# ─────────────────────────── (c) never a git command targeting main ───────────────────────────

def test_never_issues_a_git_command_that_references_main(fixture_firmware):
    """The only place "main" may appear anywhere in this flow is the `gh pr create --base main`
    call — that's a GitHub API call, not a git write, and cannot modify main. No `git` call, in
    either the authored or empty-authored path, may reference main at all."""
    git, gh = _recorder(), _recorder(stdout="https://github.com/x/y/pull/1\n")

    drain_pr.main(run_drain=lambda: {"authored": FIXTURE_IDS}, git=git, gh=gh, now=NOW)

    for call in git.calls:
        assert "main" not in call, f"git call referenced main: {call}"
    # the branch created is always the drain branch, never main itself
    assert git.calls[0][2] != "main"


def test_never_touches_git_when_nothing_authored():
    git, gh = _recorder(), _recorder()
    drain_pr.main(run_drain=lambda: {"authored": []}, git=git, gh=gh, now=NOW)
    assert git.calls == []


# ─────────────────────────── branch_name ───────────────────────────

def test_branch_name_format_is_jr_drain_utc_timestamp():
    name = drain_pr.branch_name(NOW)
    assert name == "jr-drain-20260901-0846"
    assert re.fullmatch(r"jr-drain-\d{8}-\d{4}", name)
