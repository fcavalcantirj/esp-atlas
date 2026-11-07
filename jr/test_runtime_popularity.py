"""Offline oracles for the runtime popularity collector (jr/runtime_popularity.py).

Every git repository here lives under tmp_path (a bare "origin" plus a local clone), GitHub is a
fake GraphQL transport, and HOME/git config point into tmp_path: no network, no real home state.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import runtime_popularity as rp
from budget import Budget

NOW = datetime(2026, 11, 7, 19, 0, tzinfo=timezone.utc)
EARLIER = "2026-11-07T18:00:00Z"
SHA = "a" * 40


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    config = home / ".gitconfig"
    config.write_text("[user]\n\tname = Test\n\temail = test@example.invalid\n"
                      "[init]\n\tdefaultBranch = main\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _sh(cwd: Path, *args: str, input: str | None = None) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, input=input)
    assert p.returncode == 0, p.stderr
    return p.stdout.strip()


def _write_firmware(root: Path, fid: str, url: str, pop: dict | None = None) -> None:
    path = root / "data" / "firmware" / fid / "firmware.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    front = {"id": fid, "type": "firmware", "name": fid, "url": url}
    if pop:
        front["popularity"] = pop
    path.write_text("---\n" + yaml.safe_dump(front, sort_keys=False) + "---\n\nBody.\n")


@pytest.fixture
def repos(tmp_path):
    """(origin bare repo, local clone with main checked out and a 3-firmware catalog)."""
    origin = tmp_path / "origin.git"
    _sh(tmp_path, "init", "--bare", "-q", str(origin))
    work = tmp_path / "work"
    _sh(tmp_path, "clone", "-q", str(origin), str(work))
    _write_firmware(work, "alpha", "https://github.com/Octo/Alpha")
    _write_firmware(work, "beta", "https://github.com/octo/beta.git")
    _write_firmware(work, "gamma", "https://github.com/octo/gamma", {"github_repo_id": 30})
    _sh(work, "add", "-A")
    _sh(work, "commit", "-q", "-m", "catalog")
    _sh(work, "push", "-q", "origin", "main")
    return origin, work


class FakeGH:
    """A GraphQL-only `gh` double: answers aliases from `nodes` (repo -> node or None)."""

    def __init__(self, nodes: dict, *, remaining: int = 4000, limited: bool = False, fail: bool = False,
                 limited_from_call: int | None = None):
        self.nodes, self.remaining, self.limited, self.fail = nodes, remaining, limited, fail
        self.limited_from_call = limited_from_call
        self.calls: list[tuple] = []

    def __call__(self, *args, **_timeout):
        self.calls.append(args)
        assert args[:2] == ("api", "graphql"), args
        if self.fail:
            return subprocess.CompletedProcess(args, 1, "", "network down")
        query = args[-1]
        remaining = self.remaining - (len(self.calls) - 1)  # each call spends one point
        data = {"rateLimit": {"cost": 1, "remaining": remaining, "resetAt": "2026-11-07T20:00:00Z"}}
        limited = self.limited or (self.limited_from_call is not None and len(self.calls) >= self.limited_from_call)
        errors = [{"type": "RATE_LIMITED", "message": "rate limit"}] if limited else []
        for alias, owner, name in re.findall(r'(r\d+):repository\(owner:"([^"]+)",name:"([^"]+)"\)', query):
            node = self.nodes.get(f"{owner}/{name}")
            data[alias] = node
            if node is None:
                errors.append({"path": [alias], "message": "not found"})
        body = json.dumps({"data": data, **({"errors": errors} if errors else {})})
        return subprocess.CompletedProcess(args, 1 if errors else 0, f"HTTP/2.0 200 OK\n\n{body}", "")


def node(repo: str, repo_id: int, stars: int, forks: int) -> dict:
    return {"nameWithOwner": repo, "databaseId": repo_id, "fullDatabaseId": str(repo_id),
            "stargazerCount": stars, "forkCount": forks}


GOOD = {"octo/alpha": node("Octo/Alpha", 10, 5, 1), "octo/beta": node("octo/beta", 20, 0, 0),
        "octo/gamma": node("octo/gamma", 30, 7, 3)}


def record(url: str, repo_id: int, stars: int, forks: int, as_of: str = EARLIER) -> dict:
    return {"repository_url": url, "github_repo_id": repo_id, "stars": stars, "forks": forks,
            "github_as_of": as_of}


def snapshot(records: dict, published_at: str = "2026-11-07T18:30:00Z") -> dict:
    return {"schema_version": 1, "version": "v-test", "catalog_revision": SHA,
            "published_at": published_at, "records": records}


# --- schema --------------------------------------------------------------------------------------

VALID = snapshot({"alpha": record("https://github.com/octo/alpha", 10, 0, 0)})


def test_valid_snapshot_round_trips():
    text = json.dumps(VALID)
    assert rp.validate_snapshot(json.loads(text), now=NOW) == []


def _mutate(path: tuple, value):
    doc = copy.deepcopy(VALID)
    target = doc
    for key in path[:-1]:
        target = target[key]
    if value is KeyError:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return doc


@pytest.mark.parametrize("path,value", [
    (("schema_version",), 2), (("schema_version",), True), (("schema_version",), KeyError),
    (("version",), ""), (("version",), 3), (("version",), "x" * 201),
    (("catalog_revision",), "abc"), (("catalog_revision",), "A" * 40),
    (("published_at",), "2026-11-07T18:30:00"), (("published_at",), "yesterday"),
    (("published_at",), "2026-11-08T18:30:00Z"),
    (("records",), []),
    (("records", "alpha", "repository_url"), "http://github.com/octo/alpha"),
    (("records", "alpha", "repository_url"), "https://github.com/Octo/Alpha"),
    (("records", "alpha", "repository_url"), "https://gitlab.com/octo/alpha"),
    (("records", "alpha", "github_repo_id"), 0), (("records", "alpha", "github_repo_id"), "10"),
    (("records", "alpha", "stars"), -1), (("records", "alpha", "stars"), True),
    (("records", "alpha", "forks"), 1.0), (("records", "alpha", "forks"), 2**53),
    (("records", "alpha", "github_as_of"), "2026-11-07T18:31:00Z"),
    (("records", "alpha", "github_as_of"), "2026-11-07"),
    (("records", "alpha", "github_as_of"), KeyError),
    (("records", "alpha", "extra"), 1),
    (("extra",), 1),
])
def test_schema_rejects_bad_snapshots(path, value):
    assert rp.validate_snapshot(_mutate(path, value), now=NOW)


def test_schema_rejects_bad_firmware_ids():
    doc = copy.deepcopy(VALID)
    doc["records"]["Bad_ID"] = doc["records"].pop("alpha")
    assert rp.validate_snapshot(doc, now=NOW)
    assert rp.validate_snapshot("not a dict", now=NOW)


def test_canonical_repository():
    assert rp.canonical_repository("https://github.com/Octo/Alpha.git/") == "https://github.com/octo/alpha"
    assert rp.canonical_repository("https://github.com/octo") is None
    assert rp.canonical_repository("https://github.com/octo/a/tree/main") is None
    assert rp.canonical_repository("https://github.com/../x") is None
    assert rp.canonical_repository(None) is None


# --- catalog at a pinned revision ----------------------------------------------------------------

def test_catalog_is_read_from_the_pinned_revision_not_the_working_tree(repos):
    _, work = repos
    pinned = _sh(work, "rev-parse", "main")
    _sh(work, "checkout", "-q", "-b", "side")
    _write_firmware(work, "alpha", "https://github.com/octo/elsewhere")
    _sh(work, "commit", "-q", "-am", "diverge HEAD from main")
    _write_firmware(work, "uncommitted", "https://github.com/octo/uncommitted")
    revision, entries, excluded = rp.read_catalog(rp.make_git(work), "main")
    assert revision == pinned
    assert [(e.firmware_id, e.repo, e.repository_url, e.catalog_id) for e in entries] == [
        ("alpha", "octo/alpha", "https://github.com/octo/alpha", None),
        ("beta", "octo/beta", "https://github.com/octo/beta", None),
        ("gamma", "octo/gamma", "https://github.com/octo/gamma", 30)]
    assert excluded == {}


def test_catalog_excludes_unusable_sources(tmp_path):
    work = tmp_path / "cat"
    _sh(tmp_path, "init", "-q", str(work))
    _write_firmware(work, "gitlab", "https://gitlab.com/octo/x")
    _write_firmware(work, "nyan", "https://github.com/temporal/nyan-mode")
    (work / "data" / "firmware" / "broken").mkdir(parents=True)
    (work / "data" / "firmware" / "broken" / "firmware.md").write_text("---\n: [\n---\n")
    _sh(work, "add", "-A")
    _sh(work, "commit", "-q", "-m", "c")
    _, entries, excluded = rp.read_catalog(rp.make_git(work), "HEAD")
    assert entries == []
    assert excluded == {"broken": "excluded_invalid_record", "gitlab": "excluded_invalid_url",
                        "nyan": "excluded_wrong_source"}


def test_unresolvable_catalog_ref_is_refused(repos):
    with pytest.raises(rp.Refused):
        rp.read_catalog(rp.make_git(repos[1]), "no-such-ref")


# --- collection ----------------------------------------------------------------------------------

def _entries(repos):
    return rp.read_catalog(rp.make_git(repos[1]), "main")[1]


def _collect(repos, gh, previous=None, budget=None):
    return rp.collect(_entries(repos), previous or {}, gh=gh, budget=budget or Budget(), now=NOW)


def test_fresh_counts_are_published_and_zero_stars_allowed(repos):
    result = _collect(repos, FakeGH(GOOD))
    assert result.records["beta"] == record("https://github.com/octo/beta", 20, 0, 0, "2026-11-07T19:00:00Z")
    assert result.fresh == ["alpha", "beta", "gamma"] and result.kept_last_good == []


def test_counts_may_decrease_against_the_previous_snapshot(repos):
    previous = {"alpha": record("https://github.com/octo/alpha", 10, 500, 90)}
    result = _collect(repos, FakeGH(GOOD), previous)
    assert result.records["alpha"]["stars"] == 5 and result.records["alpha"]["forks"] == 1


def test_identity_change_against_previous_snapshot_quarantines(repos):
    previous = {"alpha": record("https://github.com/octo/alpha", 99, 5, 1)}
    result = _collect(repos, FakeGH(GOOD), previous)
    assert "alpha" not in result.records
    assert result.quarantined == {"alpha": {"repository_url": "https://github.com/octo/alpha",
                                            "pinned_repo_id": 99, "observed_repo_id": 10}}


def test_identity_change_against_catalog_repo_id_quarantines(repos):
    nodes = {**GOOD, "octo/gamma": node("octo/gamma", 31, 7, 3)}
    result = _collect(repos, FakeGH(nodes))
    assert "gamma" not in result.records and result.quarantined["gamma"]["pinned_repo_id"] == 30


def test_failed_fetch_keeps_last_good_with_its_old_timestamp(repos):
    previous = {"beta": record("https://github.com/octo/beta", 20, 4, 2)}
    result = _collect(repos, FakeGH({**GOOD, "octo/beta": None}), previous)
    assert result.records["beta"] == previous["beta"]
    assert result.kept_last_good == ["beta"] and result.fresh == ["alpha", "gamma"]


def test_failed_fetch_without_last_good_is_excluded(repos):
    result = _collect(repos, FakeGH({**GOOD, "octo/beta": None}))
    assert "beta" not in result.records and result.excluded == {"beta": "attempted_graphql_error"}


def test_last_good_from_a_different_repository_is_not_kept(repos):
    previous = {"beta": record("https://github.com/someone/else", 20, 4, 2)}
    result = _collect(repos, FakeGH({**GOOD, "octo/beta": None}), previous)
    assert "beta" not in result.records


def test_transport_failure_keeps_every_last_good(repos):
    previous = {"alpha": record("https://github.com/octo/alpha", 10, 5, 1)}
    result = _collect(repos, FakeGH(GOOD, fail=True), previous)
    assert result.records == previous and result.kept_last_good == ["alpha"]
    assert set(result.excluded) == {"beta", "gamma"}


def test_rate_limited_or_low_quota_attempts_nothing(repos):
    for gh in (FakeGH(GOOD, limited=True), FakeGH(GOOD, remaining=10)):
        result = _collect(repos, gh)
        assert result.records == {} and len(gh.calls) == 1
        assert set(result.excluded.values()) == {"unattempted_rate_limit"}


def test_exhausted_time_budget_attempts_nothing(repos):
    ticks = iter([0.0] + [10_000.0] * 50)
    gh = FakeGH(GOOD)
    result = _collect(repos, gh, budget=Budget(max_seconds=180, clock=lambda: next(ticks)))
    assert gh.calls == [] and set(result.excluded.values()) == {"unattempted_budget"}


def test_repositories_are_batched(repos, monkeypatch):
    monkeypatch.setattr(rp.gql, "BATCH_SIZE", 2)
    gh = FakeGH(GOOD)
    assert _collect(repos, gh).fresh == ["alpha", "beta", "gamma"]
    assert len(gh.calls) == 3  # probe + two batches


def test_rate_limit_mid_run_keeps_last_good_for_the_rest(repos, monkeypatch):
    monkeypatch.setattr(rp.gql, "BATCH_SIZE", 1)
    previous = {"gamma": record("https://github.com/octo/gamma", 30, 9, 9)}
    gh = FakeGH(GOOD, limited_from_call=3)  # probe, alpha, then beta's batch says RATE_LIMITED
    result = _collect(repos, gh, previous)
    # beta's alias still answered in that HTTP-200 envelope, so it counts; gamma is never asked
    assert result.fresh == ["alpha", "beta"] and result.kept_last_good == ["gamma"]
    assert len(gh.calls) == 3


def test_quota_draining_mid_run_stops_before_the_next_batch(repos, monkeypatch):
    monkeypatch.setattr(rp.gql, "BATCH_SIZE", 1)
    gh = FakeGH(GOOD, remaining=51)  # the probe leaves 51, alpha's batch leaves 50
    result = _collect(repos, gh)
    assert result.fresh == ["alpha"] and len(gh.calls) == 2
    assert set(result.excluded.values()) == {"unattempted_rate_limit"}


def test_failed_batch_marks_the_tail_unattempted(repos, monkeypatch):
    monkeypatch.setattr(rp.gql, "BATCH_SIZE", 1)
    calls = []

    def gh(*args, **_):
        calls.append(args)
        if len(calls) == 1:
            return FakeGH(GOOD)(*args)
        return subprocess.CompletedProcess(args, 1, "", "boom")

    result = _collect(repos, gh)
    assert result.excluded == {"alpha": "attempted_query_failure", "beta": "unattempted_query_failure",
                               "gamma": "unattempted_query_failure"}


def test_last_good_contradicting_the_catalog_id_is_not_kept(repos):
    previous = {"gamma": record("https://github.com/octo/gamma", 31, 9, 9)}
    result = _collect(repos, FakeGH({**GOOD, "octo/gamma": None}), previous)
    assert "gamma" not in result.records and result.excluded == {"gamma": "excluded_identity_mismatch"}


def test_invalid_catalog_repo_id_is_excluded(tmp_path):
    work = tmp_path / "cat"
    _sh(tmp_path, "init", "-q", str(work))
    _write_firmware(work, "alpha", "https://github.com/octo/alpha", {"github_repo_id": "10"})
    _sh(work, "add", "-A")
    _sh(work, "commit", "-q", "-m", "c")
    assert rp.read_catalog(rp.make_git(work), "HEAD")[2] == {"alpha": "excluded_invalid_record"}


# --- publishing (parent-SHA compare-and-swap) ----------------------------------------------------

def _remote_ref(origin: Path, ref: str) -> str | None:
    p = subprocess.run(["git", "-C", str(origin), "rev-parse", "--verify", "-q", ref],
                       capture_output=True, text=True)
    return p.stdout.strip() or None


def _valid_for(work: Path) -> dict:
    doc = snapshot({"alpha": record("https://github.com/octo/alpha", 10, 5, 1)})
    doc["catalog_revision"] = _sh(work, "rev-parse", "main")
    return doc


def test_first_publish_creates_an_orphan_holding_only_popularity_json(repos):
    origin, work = repos
    main_before, head_before = _remote_ref(origin, "main"), _sh(work, "rev-parse", "HEAD")
    git = rp.make_git(work)
    parent, previous = rp.observe_branch(git, "origin", rp.BRANCH)
    assert (parent, previous) == (None, None)
    commit = rp.publish(git, remote="origin", branch=rp.BRANCH, parent=None,
                        snapshot=_valid_for(work), now=NOW)
    assert _remote_ref(origin, rp.BRANCH) == commit
    assert _sh(origin, "ls-tree", "-r", "--name-only", commit) == "popularity.json"
    assert _sh(origin, "rev-list", "--parents", "-n1", commit) == commit
    assert json.loads(_sh(origin, "show", f"{commit}:popularity.json")) == _valid_for(work)
    assert _remote_ref(origin, "main") == main_before
    assert _sh(work, "rev-parse", "HEAD") == head_before
    assert _sh(work, "status", "--porcelain") == ""


def test_second_publish_chains_on_the_observed_parent(repos):
    origin, work = repos
    git = rp.make_git(work)
    first = rp.publish(git, remote="origin", branch=rp.BRANCH, parent=None, snapshot=_valid_for(work), now=NOW)
    parent, previous = rp.observe_branch(git, "origin", rp.BRANCH)
    assert parent == first and previous == _valid_for(work)
    second = rp.publish(git, remote="origin", branch=rp.BRANCH, parent=parent, snapshot=_valid_for(work), now=NOW)
    assert _sh(origin, "rev-parse", f"{second}^") == first
    assert _sh(origin, "ls-tree", "-r", "--name-only", second) == "popularity.json"


def test_concurrent_parent_move_refuses_and_leaves_branch_unchanged(repos, tmp_path):
    origin, work = repos
    git = rp.make_git(work)
    first = rp.publish(git, remote="origin", branch=rp.BRANCH, parent=None, snapshot=_valid_for(work), now=NOW)
    observed, _ = rp.observe_branch(git, "origin", rp.BRANCH)
    rival = tmp_path / "rival"
    _sh(tmp_path, "clone", "-q", "-b", rp.BRANCH, str(origin), str(rival))
    _sh(rival, "commit", "-q", "--allow-empty", "-m", "rival")
    _sh(rival, "push", "-q", "origin", rp.BRANCH)
    moved = _remote_ref(origin, rp.BRANCH)
    assert moved != first
    with pytest.raises(rp.LostRace):
        rp.publish(git, remote="origin", branch=rp.BRANCH, parent=observed, snapshot=_valid_for(work), now=NOW)
    assert _remote_ref(origin, rp.BRANCH) == moved


def test_branch_created_by_a_rival_after_observing_absence_refuses(repos, tmp_path):
    origin, work = repos
    git = rp.make_git(work)
    assert rp.observe_branch(git, "origin", rp.BRANCH) == (None, None)
    rival = tmp_path / "rival"
    _sh(tmp_path, "clone", "-q", str(origin), str(rival))
    _sh(rival, "push", "-q", "origin", f"main:refs/heads/{rp.BRANCH}")
    with pytest.raises(rp.LostRace):
        rp.publish(git, remote="origin", branch=rp.BRANCH, parent=None, snapshot=_valid_for(work), now=NOW)
    assert _remote_ref(origin, rp.BRANCH) == _remote_ref(origin, "main")


def test_invalid_snapshot_is_never_published(repos):
    origin, work = repos
    bad = _valid_for(work)
    bad["records"]["alpha"]["stars"] = -1
    with pytest.raises(rp.Refused):
        rp.publish(rp.make_git(work), remote="origin", branch=rp.BRANCH, parent=None, snapshot=bad, now=NOW)
    assert _remote_ref(origin, rp.BRANCH) is None


def test_publishing_to_main_is_refused(repos):
    origin, work = repos
    before = _remote_ref(origin, "main")
    with pytest.raises(rp.Refused):
        rp.publish(rp.make_git(work), remote="origin", branch="main", parent=before,
                   snapshot=_valid_for(work), now=NOW)
    assert _remote_ref(origin, "main") == before


def test_rejected_push_without_a_moved_branch_is_refused(repos):
    origin, work = repos
    hook = origin / "hooks" / "pre-receive"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    with pytest.raises(rp.Refused):
        rp.publish(rp.make_git(work), remote="origin", branch=rp.BRANCH, parent=None,
                   snapshot=_valid_for(work), now=NOW)
    assert _remote_ref(origin, rp.BRANCH) is None


def test_invalid_previous_snapshot_fails_closed(repos):
    origin, work = repos
    git = rp.make_git(work)
    blob = _sh(work, "hash-object", "-w", "--stdin", input="{}")
    tree = _sh(work, "mktree", input=f"100644 blob {blob}\tpopularity.json\n")
    commit = _sh(work, "commit-tree", tree, "-m", "junk")
    _sh(work, "push", "-q", "origin", f"{commit}:refs/heads/{rp.BRANCH}")
    with pytest.raises(rp.Refused):
        rp.observe_branch(git, "origin", rp.BRANCH)


def test_unreachable_remote_is_refused(repos, tmp_path):
    git = rp.make_git(repos[1])
    with pytest.raises(rp.Refused):
        rp.observe_branch(git, str(tmp_path / "missing.git"), rp.BRANCH)


# --- end to end ----------------------------------------------------------------------------------

def _run(repos, tmp_path, gh, **kw):
    return rp.run(git=rp.make_git(repos[1]), gh=gh, remote="origin", branch=rp.BRANCH,
                  catalog_ref="main", budget=Budget(), now=NOW,
                  lock_path=tmp_path / "rp.lock", **kw)


def test_run_publishes_and_reports_receipt_counts(repos, tmp_path):
    origin, work = repos
    receipt = _run(repos, tmp_path, FakeGH({**GOOD, "octo/gamma": node("octo/gamma", 31, 1, 1)}))
    assert receipt.exit_code == 0 and receipt.status == "published"
    assert (receipt.published, receipt.kept_last_good, receipt.excluded, receipt.quarantined) == (2, 0, 0, 1)
    line = receipt.line()
    assert "published=2" in line and "kept_last_good=0" in line and "quarantined=1" in line
    assert "excluded=0" in line and receipt.commit in line and "quarantined_ids=gamma" in line
    doc = json.loads(_sh(origin, "show", f"{rp.BRANCH}:popularity.json"))
    assert rp.validate_snapshot(doc, now=NOW) == [] and sorted(doc["records"]) == ["alpha", "beta"]
    assert doc["catalog_revision"] == _sh(work, "rev-parse", "main")
    assert doc["published_at"] == "2026-11-07T19:00:00Z"

    later = rp.run(git=rp.make_git(work), gh=FakeGH({**GOOD, "octo/beta": None}), remote="origin",
                   branch=rp.BRANCH, catalog_ref="main", budget=Budget(), now=NOW + timedelta(hours=1),
                   lock_path=tmp_path / "rp.lock")
    assert (later.published, later.kept_last_good, later.excluded, later.quarantined) == (2, 1, 0, 0)
    doc = json.loads(_sh(origin, "show", f"{rp.BRANCH}:popularity.json"))
    assert doc["records"]["beta"]["github_as_of"] == "2026-11-07T19:00:00Z"
    assert doc["published_at"] == "2026-11-07T20:00:00Z"
    assert _sh(origin, "rev-parse", f"{rp.BRANCH}^") == receipt.commit


def test_dry_run_writes_locally_and_never_pushes(repos, tmp_path):
    origin, _ = repos
    out = tmp_path / "out" / "popularity.json"
    receipt = _run(repos, tmp_path, FakeGH(GOOD), dry_run=True, out=out)
    assert receipt.exit_code == 0 and receipt.status == "dry_run" and receipt.commit is None
    assert rp.validate_snapshot(json.loads(out.read_text()), now=NOW) == []
    assert _remote_ref(origin, rp.BRANCH) is None


def test_held_lock_refuses_without_side_effects(repos, tmp_path):
    origin, _ = repos
    with rp.exclusive_lock(tmp_path / "rp.lock"):
        gh = FakeGH(GOOD)
        receipt = _run(repos, tmp_path, gh)
    assert receipt.exit_code == 2 and receipt.status == "refused" and gh.calls == []
    assert 'reason="another collector run holds' in receipt.line()
    assert _remote_ref(origin, rp.BRANCH) is None


def test_lost_race_reports_nonzero(repos, tmp_path, monkeypatch):
    origin, work = repos
    real_observe = rp.observe_branch

    def observe_then_rival_moves(git, remote, branch, **kw):
        observed = real_observe(git, remote, branch, **kw)
        _sh(work, "push", "-q", "origin", f"main:refs/heads/{branch}")
        return observed

    monkeypatch.setattr(rp, "observe_branch", observe_then_rival_moves)
    receipt = _run(repos, tmp_path, FakeGH(GOOD))
    assert receipt.exit_code == 3 and receipt.status == "lost_race"
    assert _remote_ref(origin, rp.BRANCH) == _remote_ref(origin, "main")


def test_invalid_output_refuses_publication(repos, tmp_path, monkeypatch):
    origin, _ = repos
    monkeypatch.setattr(rp, "build_snapshot", lambda *a, **k: {"schema_version": 1})
    receipt = _run(repos, tmp_path, FakeGH(GOOD))
    assert receipt.exit_code == 2 and receipt.status == "refused"
    assert _remote_ref(origin, rp.BRANCH) is None


def test_main_dry_run_cli(repos, tmp_path, monkeypatch, capsys):
    _, work = repos
    monkeypatch.setattr(rp, "default_gh", FakeGH(GOOD))
    out = tmp_path / "cli.json"
    code = rp.main(["--repo", str(work), "--dry-run", "--out", str(out),
                    "--lock-path", str(tmp_path / "cli.lock")])
    assert code == 0 and out.exists()
    assert capsys.readouterr().out.startswith("runtime-popularity: status=dry_run")


def test_default_gh_refuses_anything_but_graphql():
    with pytest.raises(ValueError):
        rp.default_gh("pr", "list")


def test_main_reports_a_crash_as_an_error_receipt(monkeypatch, tmp_path, capsys):
    def boom(**_):
        raise OSError("disk gone")

    monkeypatch.setattr(rp, "run", boom)
    assert rp.main(["--repo", str(tmp_path), "--lock-path", str(tmp_path / "x.lock")]) == 1
    assert "status=error" in capsys.readouterr().out


def test_receipt_names_every_excluded_firmware(repos, tmp_path):
    receipt = _run(repos, tmp_path, FakeGH({**GOOD, "octo/beta": None}), dry_run=True, out=tmp_path / "o.json")
    assert receipt.excluded_ids == ["beta"] and "excluded_ids=beta" in receipt.line()


# --- checker round 1: persistent quarantine, cooldown, honest push outcome, total validator -------

def _at(repos, tmp_path, gh, hours: float, **kw):
    return rp.run(git=rp.make_git(repos[1]), gh=gh, remote="origin", branch=rp.BRANCH, catalog_ref="main",
                  budget=Budget(), now=NOW + timedelta(hours=hours), lock_path=tmp_path / "rp.lock", **kw)


def test_quarantine_persists_until_the_pinned_identity_returns(repos, tmp_path):
    origin, _ = repos
    assert _at(repos, tmp_path, FakeGH(GOOD), 0).status == "published"
    swapped = {**GOOD, "octo/alpha": node("Octo/Alpha", 11, 9, 9)}
    for hours in (1, 2):  # the pin must outlive the run that first saw the new identity
        receipt = _at(repos, tmp_path, FakeGH(swapped), hours)
        assert receipt.quarantined_ids == ["alpha"], hours
        doc = json.loads(_sh(origin, "show", f"{rp.BRANCH}:popularity.json"))
        assert "alpha" not in doc["records"]
    fetch_failed = _at(repos, tmp_path, FakeGH({**GOOD, "octo/alpha": None}), 3)
    assert fetch_failed.quarantined_ids == ["alpha"]
    restored = _at(repos, tmp_path, FakeGH(GOOD), 4)
    assert restored.quarantined_ids == [] and restored.published == 3
    assert rp.read_state(rp.make_git(repos[1]), _remote_ref(origin, rp.BRANCH))["quarantine"] == {}


def test_quarantine_pin_is_dropped_when_the_catalog_moves_the_source(repos, tmp_path):
    _, work = repos
    _at(repos, tmp_path, FakeGH(GOOD), 0)
    _at(repos, tmp_path, FakeGH({**GOOD, "octo/alpha": node("Octo/Alpha", 11, 9, 9)}), 1)
    _write_firmware(work, "alpha", "https://github.com/octo/alpha-new")
    _sh(work, "commit", "-q", "-am", "alpha moved")
    receipt = _at(repos, tmp_path, FakeGH({**GOOD, "octo/alpha-new": node("octo/alpha-new", 12, 1, 1)}), 2)
    assert receipt.quarantined_ids == [] and receipt.published == 3


def test_rate_limit_sets_a_cooldown_that_the_next_run_honours(repos, tmp_path):
    origin, _ = repos
    first = _at(repos, tmp_path, FakeGH(GOOD, limited=True), 0)
    assert first.status == "published" and first.cooldown_until == "2026-11-07T20:00:00Z"
    tip = _remote_ref(origin, rp.BRANCH)
    gh = FakeGH(GOOD)
    waiting = _at(repos, tmp_path, gh, 0.5)
    assert waiting.status == "cooldown" and waiting.exit_code == 0 and gh.calls == []
    assert "cooldown_until=2026-11-07T20:00:00Z" in waiting.line()
    assert _remote_ref(origin, rp.BRANCH) == tip
    after = _at(repos, tmp_path, FakeGH(GOOD), 1.5)
    assert after.status == "published" and after.published == 3 and after.cooldown_until is None


def test_low_quota_mid_run_reports_a_cooldown(repos, monkeypatch):
    monkeypatch.setattr(rp.gql, "BATCH_SIZE", 1)
    result = _collect(repos, FakeGH(GOOD, remaining=51))
    assert result.cooldown_until == "2026-11-07T20:00:00Z"


def test_malformed_state_trailer_fails_closed(repos):
    origin, work = repos
    doc = _valid_for(work)
    blob = _sh(work, "hash-object", "-w", "--stdin", input=json.dumps(doc))
    tree = _sh(work, "mktree", input=f"100644 blob {blob}\tpopularity.json\n")
    commit = _sh(work, "commit-tree", tree, "-m", "s", "-m", rp.STATE_TRAILER + "{not json")
    with pytest.raises(rp.Refused):
        rp.read_state(rp.make_git(work), commit)
    bad = _sh(work, "commit-tree", tree, "-m", "s", "-m", rp.STATE_TRAILER + '{"quarantine": {"a": 1}}')
    with pytest.raises(rp.Refused):
        rp.read_state(rp.make_git(work), bad)
    plain = _sh(work, "commit-tree", tree, "-m", "no trailer")  # a hand edit or foreign tool
    with pytest.raises(rp.Refused):
        rp.read_state(rp.make_git(work), plain)


def test_push_that_landed_despite_a_client_error_is_published(repos):
    origin, work = repos
    real = rp.make_git(work)

    def git(*args, **kw):
        p = real(*args, **kw)
        return subprocess.CompletedProcess(args, 124, "", "timed out") if args[0] == "push" else p

    commit = rp.publish(git, remote="origin", branch=rp.BRANCH, parent=None, snapshot=_valid_for(work), now=NOW)
    assert _remote_ref(origin, rp.BRANCH) == commit


def test_rival_moving_after_our_accepted_push_is_not_a_lost_race(repos, tmp_path):
    origin, work = repos
    real = rp.make_git(work)

    def git(*args, **kw):
        p = real(*args, **kw)
        if args[0] == "push" and p.returncode == 0:
            _sh(work, "push", "-q", "--force", "origin", f"main:refs/heads/{rp.BRANCH}")
        return p

    commit = rp.publish(git, remote="origin", branch=rp.BRANCH, parent=None, snapshot=_valid_for(work), now=NOW)
    assert commit and _remote_ref(origin, rp.BRANCH) == _remote_ref(origin, "main")


def test_git_never_runs_once_the_time_budget_is_spent(repos):
    ticks = iter([0.0] + [1_000.0] * 10)
    git = rp.make_git(repos[1], budget=Budget(max_seconds=180, clock=lambda: next(ticks)))
    assert git("rev-parse", "HEAD").returncode == 124


def test_too_little_time_left_refuses_to_push(repos, tmp_path, monkeypatch):
    origin, _ = repos
    monkeypatch.setattr(rp, "PUBLISH_RESERVE_SECONDS", 10**9)
    receipt = _run(repos, tmp_path, FakeGH(GOOD))
    assert receipt.status == "refused" and "time" in receipt.reason
    assert _remote_ref(origin, rp.BRANCH) is None


def test_impossible_dates_are_errors_not_crashes():
    assert rp.validate_snapshot(_mutate(("published_at",), "2026-13-01T00:00:00Z"), now=NOW)
    assert rp.validate_snapshot(_mutate(("records", "alpha", "github_as_of"), "2026-02-30T00:00:00Z"), now=NOW)


# --- checker round 2: pins survive catalog churn, bounded cooldown, total state -------------------

def _quarantine_alpha(repos, tmp_path):
    _at(repos, tmp_path, FakeGH(GOOD), 0)
    assert _at(repos, tmp_path, FakeGH({**GOOD, "octo/alpha": node("Octo/Alpha", 11, 9, 9)}), 1).quarantined_ids == ["alpha"]


def _state_now(repos):
    origin, work = repos
    return rp.read_state(rp.make_git(work), _remote_ref(origin, rp.BRANCH))


def test_quarantine_survives_the_entry_leaving_the_catalog_for_a_run(repos, tmp_path):
    _, work = repos
    _quarantine_alpha(repos, tmp_path)
    path = work / "data" / "firmware" / "alpha" / "firmware.md"
    original = path.read_text()
    path.write_text("---\n: [\n---\n")
    _sh(work, "commit", "-q", "-am", "alpha broken")
    _at(repos, tmp_path, FakeGH(GOOD), 2)
    assert _state_now(repos)["quarantine"]["alpha"]["pinned_repo_id"] == 10
    path.write_text(original)
    _sh(work, "commit", "-q", "-am", "alpha restored")
    receipt = _at(repos, tmp_path, FakeGH({**GOOD, "octo/alpha": node("Octo/Alpha", 11, 9, 9)}), 3)
    assert receipt.quarantined_ids == ["alpha"]


def test_catalog_seeding_the_new_id_does_not_release_a_quarantine(repos, tmp_path):
    # Jr's hourly refresh writes a first-time github_repo_id unreviewed; it must not launder the swap
    _, work = repos
    _quarantine_alpha(repos, tmp_path)
    _write_firmware(work, "alpha", "https://github.com/Octo/Alpha", {"github_repo_id": 11})
    _sh(work, "commit", "-q", "-am", "tick seeds the swapped alpha identity")
    receipt = _at(repos, tmp_path, FakeGH({**GOOD, "octo/alpha": node("Octo/Alpha", 11, 9, 9)}), 2)
    assert receipt.quarantined_ids == ["alpha"]
    assert _state_now(repos)["quarantine"]["alpha"]["pinned_repo_id"] == 10


def test_a_human_state_commit_releases_a_quarantine(repos, tmp_path):
    origin, work = repos
    _quarantine_alpha(repos, tmp_path)
    tip = _remote_ref(origin, rp.BRANCH)
    tree = _sh(origin, "rev-parse", f"{tip}^{{tree}}")
    _sh(work, "fetch", "-q", "origin", rp.BRANCH)
    release = _sh(work, "commit-tree", tree, "-p", tip, "-m", "release alpha",
                  "-m", rp.STATE_TRAILER + '{"cooldown_until":null,"quarantine":{}}')
    _sh(work, "push", "-q", "origin", f"{release}:refs/heads/{rp.BRANCH}")
    receipt = _at(repos, tmp_path, FakeGH({**GOOD, "octo/alpha": node("Octo/Alpha", 11, 9, 9)}), 2)
    assert receipt.quarantined_ids == [] and receipt.published == 3


def _commit_with_state(work: Path, origin: Path, state_json: str) -> None:
    doc = _valid_for(work)
    blob = _sh(work, "hash-object", "-w", "--stdin", input=json.dumps(doc))
    tree = _sh(work, "mktree", input=f"100644 blob {blob}\tpopularity.json\n")
    commit = _sh(work, "commit-tree", tree, "-m", "s", "-m", rp.STATE_TRAILER + state_json)
    _sh(work, "push", "-q", "--force", "origin", f"{commit}:refs/heads/{rp.BRANCH}")


def test_cooldown_beyond_a_day_is_refused_not_obeyed(repos, tmp_path):
    origin, work = repos
    _commit_with_state(work, origin, '{"cooldown_until":"2099-01-01T00:00:00Z","quarantine":{}}')
    gh = FakeGH(GOOD)
    receipt = _run(repos, tmp_path, gh)
    assert receipt.status == "refused" and receipt.exit_code == 2 and gh.calls == []


def test_dry_run_during_a_cooldown_writes_last_good_without_querying(repos, tmp_path):
    origin, work = repos
    _at(repos, tmp_path, FakeGH(GOOD), 0)
    _at(repos, tmp_path, FakeGH(GOOD, limited=True), 1)
    gh, out = FakeGH(GOOD), tmp_path / "cool.json"
    receipt = _at(repos, tmp_path, gh, 1.5, dry_run=True, out=out)
    assert receipt.status == "dry_run" and receipt.exit_code == 0 and gh.calls == []
    assert receipt.cooldown_until == "2026-11-07T21:00:00Z" and receipt.kept_last_good == 3
    assert sorted(json.loads(out.read_text())["records"]) == ["alpha", "beta", "gamma"]


def test_catalog_id_beyond_safe_integers_is_excluded(tmp_path):
    work = tmp_path / "cat"
    _sh(tmp_path, "init", "-q", str(work))
    _write_firmware(work, "alpha", "https://github.com/octo/alpha", {"github_repo_id": 2**53})
    _sh(work, "add", "-A")
    _sh(work, "commit", "-q", "-m", "c")
    assert rp.read_catalog(rp.make_git(work), "HEAD")[2] == {"alpha": "excluded_invalid_record"}


def test_invalid_next_state_is_never_committed(repos, tmp_path, monkeypatch):
    origin, _ = repos
    monkeypatch.setattr(rp, "_next_state", lambda *a, **k: {"quarantine": {"Bad": 1}, "cooldown_until": None})
    receipt = _run(repos, tmp_path, FakeGH(GOOD))
    assert receipt.status == "refused" and _remote_ref(origin, rp.BRANCH) is None


def _foreign_tip(repos) -> str:
    """A valid popularity.json pushed by another producer, with no collector-state trailer."""
    origin, work = repos
    blob = _sh(work, "hash-object", "-w", "--stdin", input=json.dumps(_valid_for(work)))
    tree = _sh(work, "mktree", input=f"100644 blob {blob}\tpopularity.json\n")
    commit = _sh(work, "commit-tree", tree, "-m", "bootstrap by another producer")
    _sh(work, "push", "-q", "origin", f"{commit}:refs/heads/{rp.BRANCH}")
    return commit


def test_unstated_tip_is_refused_unless_explicitly_adopted(repos, tmp_path):
    origin, _ = repos
    foreign = _foreign_tip(repos)
    assert _run(repos, tmp_path, FakeGH(GOOD)).status == "refused"
    assert _remote_ref(origin, rp.BRANCH) == foreign
    adopted = _run(repos, tmp_path, FakeGH(GOOD), adopt_unstated_tip=True)
    assert adopted.status == "published" and adopted.parent == foreign
    assert _sh(origin, "rev-parse", f"{rp.BRANCH}^") == foreign
    assert rp.read_state(rp.make_git(repos[1]), _remote_ref(origin, rp.BRANCH))["quarantine"] == {}


def test_adoption_still_pins_identity_from_the_adopted_snapshot(repos, tmp_path):
    _foreign_tip(repos)  # alpha recorded with id 10
    receipt = _run(repos, tmp_path, FakeGH({**GOOD, "octo/alpha": node("Octo/Alpha", 11, 9, 9)}),
                   adopt_unstated_tip=True)
    assert receipt.quarantined_ids == ["alpha"]


def test_cli_adopt_flag(repos, tmp_path, monkeypatch, capsys):
    _, work = repos
    _foreign_tip(repos)
    monkeypatch.setattr(rp, "default_gh", FakeGH(GOOD))
    code = rp.main(["--repo", str(work), "--adopt-unstated-tip", "--lock-path", str(tmp_path / "c.lock")])
    assert code == 0 and "status=published" in capsys.readouterr().out
