"""Tests for jr/publish.py — the tick's only git/GitHub surface.

`git` and `gh` are ALWAYS recorders here: no real git command, no network, no worktree on disk.
The recorder answers each argv with a scripted (returncode, stdout) so the sequence, the
pathspec, the G2 refusal, the protection preflight and the auto-merge decision are all
asserted from the recorded calls alone.

Run: cd jr && python3 -m pytest test_publish.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import memory
import publish

NOW = datetime(2026, 9, 5, 4, 7, 0, tzinfo=timezone.utc)
WT = publish.Worktree(path=Path("/tmp/jr-tick-fake"), base_sha="6190d21")
PROTECTED_OK = publish.ProtectionStatus(True, ("schema", "tests", "jr-tests"), True)


class Proc(SimpleNamespace):
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""


def recorder(script=None):
    """A fake git/gh. `script` maps a tuple-prefix of argv (after any `-C <dir>`) to
    (returncode, stdout). Unmatched calls succeed with empty stdout."""
    calls = []
    script = script or {}

    def fn(*args):
        calls.append(args)
        norm = args[2:] if args[:1] == ("-C",) else args
        for prefix, (rc, out) in script.items():
            if norm[:len(prefix)] == prefix:
                return Proc(returncode=rc, stdout=out)
        return Proc()

    fn.calls = calls
    return fn


def norm_calls(fn):
    return [a[2:] if a[:1] == ("-C",) else a for a in fn.calls]


# --- names and parsing --------------------------------------------------------------------------

def test_branch_name_is_per_tick_utc():
    assert publish.branch_name(NOW) == "jr/tick-20260905-0407"


@pytest.mark.parametrize("url", [
    "https://github.com/fcavalcantirj/esp-atlas.git",
    "https://github.com/fcavalcantirj/esp-atlas",
    "git@github.com:fcavalcantirj/esp-atlas.git",
    "ssh://git@github.com/fcavalcantirj/esp-atlas.git\n",
])
def test_owner_repo_from_https_and_ssh(url):
    assert publish.owner_repo(url) == "fcavalcantirj/esp-atlas"


def test_owner_repo_rejects_non_github():
    with pytest.raises(ValueError):
        publish.owner_repo("https://gitlab.com/a/b.git")


# --- worktree lifecycle -------------------------------------------------------------------------

def test_add_worktree_fetches_then_detaches_at_origin_main(tmp_path):
    git = recorder({("rev-parse", "origin/main"): (0, "abc1234\n")})
    wt = publish.add_worktree(git=git, root=tmp_path / "wt")
    assert git.calls[0] == ("fetch", "origin", "main")
    assert git.calls[1] == ("worktree", "prune")                    # stale entries from a killed tick
    assert git.calls[2] == ("worktree", "add", "--detach", str(tmp_path / "wt"), "origin/main")
    assert wt.base_sha == "abc1234"
    assert wt.path == tmp_path / "wt"


def test_add_worktree_refuses_when_fetch_fails(tmp_path):
    git = recorder({("fetch",): (1, "")})
    with pytest.raises(RuntimeError):
        publish.add_worktree(git=git, root=tmp_path / "wt")
    assert all(c[0] != "worktree" for c in git.calls)


def test_remove_worktree_forces_and_prunes():
    git = recorder()
    publish.remove_worktree(WT, git=git)
    assert git.calls == [("worktree", "remove", "--force", str(WT.path)), ("worktree", "prune")]


def test_is_clean_reads_porcelain_status():
    assert publish.is_clean(WT, git=recorder({("status",): (0, "")}))
    assert not publish.is_clean(WT, git=recorder({("status",): (0, " M data/x\n")}))


# --- protection preflight ----------------------------------------------------------------------

def _gh_with_protection(contexts, allow="true", rc=0):
    rule = json.dumps({"required_status_checks": {"strict": False, "contexts": contexts}})
    return recorder({
        ("api", "repos/o/r/branches/main/protection"): (rc, rule if rc == 0 else ""),
        ("api", "repos/o/r", "-q", ".allow_auto_merge"): (0, allow + "\n"),
    })


def test_protection_ok_when_all_three_checks_required_and_auto_merge_allowed():
    st = publish.protection_status("o/r", gh=_gh_with_protection(["schema", "tests", "jr-tests"]))
    assert st.ok and st.allow_auto_merge and st.required_checks == ("schema", "tests", "jr-tests")


def test_protection_not_ok_when_branch_unprotected():
    st = publish.protection_status("o/r", gh=_gh_with_protection([], rc=1))
    assert not st.ok and "not protected" in st.reason


def test_protection_not_ok_when_a_check_is_missing():
    st = publish.protection_status("o/r", gh=_gh_with_protection(["schema", "tests"]))
    assert not st.ok and "jr-tests" in st.reason


def test_protection_not_ok_when_auto_merge_switched_off():
    st = publish.protection_status("o/r", gh=_gh_with_protection(["schema", "tests", "jr-tests"], allow="false"))
    assert not st.ok and "allow_auto_merge" in st.reason


def test_protection_reads_checks_array_form_too():
    rule = json.dumps({"required_status_checks": {"checks": [{"context": c} for c in ("schema", "tests", "jr-tests")]}})
    gh = recorder({("api", "repos/o/r/branches/main/protection"): (0, rule),
                   ("api", "repos/o/r", "-q", ".allow_auto_merge"): (0, "true")})
    assert publish.protection_status("o/r", gh=gh).ok


# --- publish sequence --------------------------------------------------------------------------

def _git_ok(deletions=""):
    """`deletions` is git's `--name-status --no-renames -z` output: NUL-separated status/path pairs."""
    return recorder({
        ("diff", "--cached", "--quiet"): (1, ""),                 # something IS staged
        ("diff", "--cached", "--name-status", "--no-renames", "-z"): (0, deletions),
        ("rev-parse", "HEAD"): (0, "feedbee\n"),
    })


def _z(*pairs):
    return "".join(f"{st}\0{path}\0" for st, path in pairs)


def test_publish_stages_only_the_pathspec_plus_ledger_then_commits_pushes_and_opens_pr():
    git, gh = _git_ok(), recorder({("pr", "create"): (0, "https://github.com/o/r/pull/9\n")})
    res = publish.publish(WT, ["data/firmware/x", "data/recipes/b__x"], "feat(jr): tick", "body",
                          git=git, gh=gh, now=NOW, protection=PROTECTED_OK)
    calls = norm_calls(git)
    assert calls[0] == ("add", "--", "data/firmware/x", "data/recipes/b__x", "jr/proposed_ledger.json")
    assert ("checkout", "-q", "-B", "jr/tick-20260905-0407") in calls
    assert ("commit", "-q", "-m", "feat(jr): tick") in calls
    assert ("push", "-u", "origin", "jr/tick-20260905-0407") in calls
    assert gh.calls[0][:6] == ("pr", "create", "--base", "main", "--head", "jr/tick-20260905-0407")
    assert gh.calls[1] == ("pr", "merge", "https://github.com/o/r/pull/9", "--auto", "--squash")
    assert res.published and res.auto_merge and res.commit == "feedbee"
    assert res.pr_url == "https://github.com/o/r/pull/9"
    # every git write happened inside the worktree, never on the clone's checkout
    for c in git.calls:
        if c[0] != "-C":
            assert c[0] in ("remote",), c
        else:
            assert c[1] == str(WT.path)


def test_publish_with_nothing_staged_touches_no_branch_commit_push_or_pr():
    git = recorder({("diff", "--cached", "--quiet"): (0, "")})
    gh = recorder()
    res = publish.publish(WT, ["data/firmware/x"], "s", "b", git=git, gh=gh, now=NOW, protection=PROTECTED_OK)
    assert not res.published and res.reason == "nothing to publish"
    assert all(c[0] not in ("checkout", "commit", "push") for c in norm_calls(git))
    assert gh.calls == []


def test_publish_refuses_a_record_deletion_and_unstages_it():
    git = _git_ok(deletions=_z(("D", "data/firmware/rogueduck/firmware.md"), ("A", "data/firmware/new/firmware.md")))
    gh = recorder()
    res = publish.publish(WT, ["data/firmware"], "s", "b", git=git, gh=gh, now=NOW, protection=PROTECTED_OK)
    assert not res.published
    assert "deletion refused" in res.reason and "rogueduck" in res.reason
    calls = norm_calls(git)
    assert ("reset", "-q", "--", "data/firmware", "jr/proposed_ledger.json") in calls
    assert all(c[0] not in ("checkout", "commit", "push") for c in calls)
    assert gh.calls == []


def test_publish_opens_pr_but_withholds_auto_merge_for_a_non_record_deletion():
    git = _git_ok(deletions=_z(("D", "jr/state/etags.json")))
    gh = recorder({("pr", "create"): (0, "https://github.com/o/r/pull/3\n")})
    res = publish.publish(WT, ["jr/state"], "s", "b", git=git, gh=gh, now=NOW, protection=PROTECTED_OK)
    assert res.published and not res.auto_merge and "withheld" in res.reason
    assert all(c[:2] != ("pr", "merge") for c in gh.calls)


def test_publish_withholds_auto_merge_when_needs_human():
    git = _git_ok()
    gh = recorder({("pr", "create"): (0, "https://github.com/o/r/pull/4\n")})
    res = publish.publish(WT, ["data/firmware/x"], "s", "b", git=git, gh=gh, now=NOW,
                          needs_human=True, protection=PROTECTED_OK)
    assert res.published and not res.auto_merge and "needs_human" in res.reason
    assert all(c[:2] != ("pr", "merge") for c in gh.calls)


def test_publish_withholds_auto_merge_when_main_is_unprotected():
    git = _git_ok()
    gh = recorder({("pr", "create"): (0, "https://github.com/o/r/pull/5\n"),
                   ("api", "repos/o/r/branches/main/protection"): (1, "")})
    res = publish.publish(WT, ["data/firmware/x"], "s", "b", git=git, gh=gh, now=NOW, repo_slug="o/r")
    assert res.published and not res.auto_merge
    assert "not protected" in res.reason
    assert all(c[:2] != ("pr", "merge") for c in gh.calls)


def test_publish_derives_repo_slug_from_the_origin_remote_when_not_given():
    git = _git_ok()
    git_script = git  # extend: remote get-url answers an HTTPS url
    script = {("remote", "get-url", "origin"): (0, "https://github.com/o/r.git\n")}
    orig = git_script

    def git2(*args):
        norm = args[2:] if args[:1] == ("-C",) else args
        for prefix, (rc, out) in script.items():
            if norm[:len(prefix)] == prefix:
                orig.calls.append(args)
                return Proc(returncode=rc, stdout=out)
        return orig(*args)
    git2.calls = orig.calls
    gh = recorder({("pr", "create"): (0, "https://github.com/o/r/pull/6\n"),
                   ("api", "repos/o/r/branches/main/protection"): (0, json.dumps({"required_status_checks": {"contexts": ["schema", "tests", "jr-tests"]}})),
                   ("api", "repos/o/r", "-q", ".allow_auto_merge"): (0, "true")})
    res = publish.publish(WT, ["data/firmware/x"], "s", "b", git=git2, gh=gh, now=NOW)
    assert res.published and res.auto_merge
    assert ("api", "repos/o/r/branches/main/protection") in gh.calls


def test_publish_auto_merge_is_requested_only_after_the_pr_exists():
    git = _git_ok()
    gh = recorder({("pr", "create"): (0, "https://github.com/o/r/pull/7\n")})
    publish.publish(WT, ["data/firmware/x"], "s", "b", git=git, gh=gh, now=NOW, protection=PROTECTED_OK)
    kinds = [c[:2] for c in gh.calls]
    assert kinds.index(("pr", "create")) < kinds.index(("pr", "merge"))


def test_publish_reports_a_failed_push_without_opening_a_pr():
    git = recorder({("diff", "--cached", "--quiet"): (1, ""), ("push",): (1, "rejected")})
    gh = recorder()
    res = publish.publish(WT, ["data/firmware/x"], "s", "b", git=git, gh=gh, now=NOW, protection=PROTECTED_OK)
    assert not res.published and res.reason == "push failed"
    assert gh.calls == []


def test_no_git_call_ever_writes_to_main():
    """The only `main`s allowed: `fetch origin main`, `worktree add … origin/main`, and the
    `gh pr create --base main` API call. Never `checkout main`, `push origin main`, `reset` on
    main, `merge`, or a branch named main."""
    git = _git_ok()
    git_calls_before = len(git.calls)
    gh = recorder({("pr", "create"): (0, "https://github.com/o/r/pull/8\n"),
                   ("rev-parse", "origin/main"): (0, "x\n")})
    wt = publish.add_worktree(git=git, root=Path("/tmp/jr-tick-fake"))
    publish.publish(wt, ["data/firmware/x"], "s", "b", git=git, gh=gh, now=NOW, protection=PROTECTED_OK)
    publish.remove_worktree(wt, git=git)
    for c in norm_calls(git)[git_calls_before:]:
        if "main" in c or "origin/main" in c:
            assert c in (("fetch", "origin", "main"),
                         ("worktree", "add", "--detach", "/tmp/jr-tick-fake", "origin/main"),
                         ("rev-parse", "origin/main")), c
        assert c[0] not in ("merge", "rebase", "reset") or c == ("reset", "-q", "--", "data/firmware/x", "jr/proposed_ledger.json"), c
        if c[0] == "push":
            assert "main" not in c


# --- post-merge purge ---------------------------------------------------------------------------

def test_revalidate_catalog_posts_bearer_and_reports_status():
    seen = {}

    def http(url, headers, timeout):
        seen.update(url=url, headers=headers)
        return 200, '{"revalidated":true,"tag":"catalog"}'
    res = publish.revalidate_catalog("s3cret", http=http)
    assert res == {"ok": True, "status": 200, "body": '{"revalidated":true,"tag":"catalog"}'}
    assert seen["url"] == "https://esp-atlas.com/api/revalidate"
    assert seen["headers"] == {"Authorization": "Bearer s3cret"}


@pytest.mark.parametrize("status,body", [(503, '{"error":"revalidation not configured"}'),
                                          (401, '{"error":"unauthorized"}'), (0, "URLError: down")])
def test_revalidate_catalog_never_raises_on_failure(status, body):
    res = publish.revalidate_catalog("s3cret", http=lambda u, h, t: (status, body))
    assert res["ok"] is False and res["status"] == status


def test_revalidate_catalog_skips_without_a_secret():
    assert publish.revalidate_catalog(None, http=lambda *a: (200, "")) == {"ok": False, "skipped": "no REVALIDATE_SECRET"}
    assert publish.revalidate_catalog("", http=lambda *a: (200, ""))["skipped"]


def test_ledger_is_always_part_of_the_pathspec():
    assert memory.staged_paths() == ["jr/proposed_ledger.json"]
    git = recorder({("diff", "--cached", "--quiet"): (0, "")})
    publish.publish(WT, [], "s", "b", git=git, gh=recorder(), now=NOW, protection=PROTECTED_OK)
    assert norm_calls(git)[0] == ("add", "--", "jr/proposed_ledger.json")


# --- review-driven guards (adversarial review of the tick branch) ------------------------------

def test_g2_sees_a_deletion_hidden_behind_a_rename_and_a_non_ascii_path():
    """git's default rename detection reports delete+add of similar files as `R100 old new`;
    with --no-renames -z the deletion is a plain D and the path is not C-quoted."""
    git = _git_ok(deletions=_z(("D", "data/firmware/a/firmware.md"), ("A", "data/firmware/c/firmware.md"),
                               ("D", "data/recipes/caf\u00e9__x/im\u00e1gem.png")))
    res = publish.publish(WT, ["data/firmware", "data/recipes"], "s", "b", git=git, gh=recorder(), now=NOW, protection=PROTECTED_OK)
    assert not res.published and "data/firmware/a/firmware.md" in res.reason and "im\u00e1gem" in res.reason
    assert ("diff", "--cached", "--name-status", "--no-renames", "-z") in norm_calls(git)


def test_a_failed_git_add_is_reported_not_read_as_nothing_to_publish():
    git = recorder({("add",): (128, ""), ("diff", "--cached", "--quiet"): (0, "")})
    git_calls_with_err = git
    res = publish.publish(WT, ["data/does-not-exist"], "s", "b", git=git_calls_with_err, gh=recorder(), now=NOW, protection=PROTECTED_OK)
    assert not res.published and res.reason.startswith("git add failed")
    assert all(c[0] not in ("checkout", "commit", "push") for c in norm_calls(git))


def test_add_worktree_prunes_first_and_removes_the_temp_dir_when_add_fails(tmp_path):
    d = tmp_path / "wt"
    d.mkdir()
    git = recorder({("worktree", "add"): (128, "fatal: nope")})
    with pytest.raises(RuntimeError):
        publish.add_worktree(git=git, root=d)
    assert not d.exists()
    assert git.calls[1] == ("worktree", "prune")


def test_cleanup_branch_deletes_the_local_ref_only():
    git = recorder()
    publish.cleanup_branch("jr/tick-20260905-0407", git=git)
    assert git.calls == [("branch", "-D", "jr/tick-20260905-0407")]


def test_protection_distinguishes_a_403_from_an_unprotected_branch():
    gh = recorder({("api", "repos/o/r/branches/main/protection"): (1, "")})
    def gh403(*args):
        p = gh(*args)
        if args[:2] == ("api", "repos/o/r/branches/main/protection"):
            p.stderr = "gh: Resource not accessible by personal access token (HTTP 403)"
        return p
    st = publish.protection_status("o/r", gh=gh403)
    assert not st.ok and "403" in st.reason
    assert not publish.protection_status("o/r", gh=gh).ok
