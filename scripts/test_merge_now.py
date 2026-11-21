"""demand_canary.request_merge: the one way the three canaries ask GitHub to merge (2026-11-21).

GitHub refuses to switch auto-merge on for a PR that can merge right now ("Pull request is in unstable
status (enablePullRequestAutoMerge)", or "clean status"). The demand canary died on that refusal (exit 2) and
#1935 (SparkFun Thing Plus S3, quotes 12/12 PASS) never merged; its own red check then kept the PR unstable."""
import json

import pytest

import code_canary as cc
import demand_canary as dc
import tick_canary as tc

HEAD = "a" * 40
REFUSED = "gh pr merge 1935: GraphQL: Pull request Pull request is in unstable status (enablePullRequestAutoMerge)"


class Gh:
    def __init__(self, refuse=None, checks=(("schema", "pass"), ("tests", "pass"), ("jr-tests", "pass")), checks_fail=False):
        self.calls, self.refuse, self.checks, self.checks_fail = [], refuse, list(checks), checks_fail

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("pr", "merge") and "--auto" in args and self.refuse:
            raise dc.Unreadable(self.refuse)
        if args[:2] == ("pr", "checks"):
            assert "--required" in args
            if self.checks_fail:                      # gh exits non-zero while a required check is pending/failing
                raise dc.Unreadable("gh pr checks 1935: some checks were not successful")
            return json.dumps([{"name": n, "bucket": b} for n, b in self.checks])
        return ""

    def merges(self):
        return [c for c in self.calls if c[:2] == ("pr", "merge")]


def test_auto_merge_is_requested_as_before_when_github_accepts_it():
    gh = Gh()
    assert dc.request_merge(gh, "o/r", 7, HEAD) == "auto"
    assert gh.merges() == [("pr", "merge", "7", "--repo", "o/r", "--merge", "--auto", "--match-head-commit", HEAD)]


@pytest.mark.parametrize("state", ["unstable", "clean"])
def test_a_pr_that_can_merge_now_is_merged_at_its_exact_head_when_every_required_check_passed(state):
    gh = Gh(refuse=REFUSED.replace("unstable", state))
    assert dc.request_merge(gh, "o/r", 7, HEAD) == "merged"
    assert gh.merges()[-1] == ("pr", "merge", "7", "--repo", "o/r", "--merge", "--match-head-commit", HEAD)


def test_a_required_check_that_did_not_pass_is_never_merged_around():
    for gh in (Gh(refuse=REFUSED, checks=(("schema", "pass"), ("tests", "fail"))), Gh(refuse=REFUSED, checks=()),
               Gh(refuse=REFUSED, checks_fail=True)):
        with pytest.raises(dc.Unreadable):
            dc.request_merge(gh, "o/r", 7, HEAD)
        assert len(gh.merges()) == 1                                  # only the refused --auto request


def test_any_other_refusal_still_stops():
    gh = Gh(refuse="gh pr merge 7: GraphQL: Head branch was modified")
    with pytest.raises(dc.Unreadable):
        dc.request_merge(gh, "o/r", 7, HEAD)
    assert len(gh.merges()) == 1


def test_all_three_canaries_ask_through_it():
    import inspect
    dsrc = inspect.getsource(dc)
    assert dsrc.count('"--auto"') == 1 and '"--auto"' in inspect.getsource(dc.request_merge)   # only the helper arms it
    for mod in (tc, cc):
        src = inspect.getsource(mod)
        assert '"--auto"' not in src and "demand_canary.request_merge(" in src, mod.__name__
