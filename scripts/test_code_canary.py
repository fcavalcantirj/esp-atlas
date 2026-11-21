"""scripts/code_canary.py — a code PR the agent reviewer PASSed at this exact head merges itself."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

import code_canary as cc

HEAD = "5e9bb443b1aa89854c94f9d8338fd6204df522f6"
NOW = datetime(2026, 11, 17, 21, 0, tzinfo=timezone.utc)


def verdict(v="PASS", head=HEAD, findings=(), checked=("gh pr diff", "pytest jr/test_board_names.py")):
    return json.dumps({"verdict": v, "head": head, "findings": list(findings), "checked": list(checked)})


class FakeGh:
    def __init__(self, merged=(), queued=(), files=("jr/x.py",), changed=None):
        self.calls, self.merged, self.queued = [], list(merged), list(queued)
        self.files, self.changed = list(files), (len(files) if changed is None else changed)

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("pr", "view") and "files,changedFiles" in args:
            return json.dumps({"files": [{"path": f} for f in self.files], "changedFiles": self.changed})
        assert not (args[:2] == ("pr", "list") and "--label" in args)   # the label search lags: REST only
        if args[:1] == ("api",) and "/issues?state=open" in args[1]:
            assert f"labels={cc.PASS_LABEL}" in args[1]
            return json.dumps([{"number": n, "pull_request": {}} for n in self.queued])
        if args[:1] == ("api",) and "/pulls?state=closed" in args[1]:
            return json.dumps([{"number": n, "merged_at": t, "labels": [{"name": cc.PASS_LABEL}]} for n, t in self.merged])
        return ""

    def writes(self):
        return [c for c in self.calls if c[:2] in {("pr", "merge"), ("pr", "edit")}]


@pytest.fixture
def autonomy(tmp_path):
    def write(on=True):
        f = tmp_path / "autonomy.json"
        f.write_text(json.dumps({"code_automerge": on}))
        return f
    return write


def run(autonomy_path, gh, vj, env=None, **kw):
    args = dict(pr=1797, head=HEAD, verdict_json=vj, repo_slug="o/r", now=NOW, env=env or {}, autonomy_path=autonomy_path, gh=gh)
    args.update(kw)
    return cc.decide(**args)


def test_pass_at_the_exact_head_labels_and_requests_the_merge(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, verdict()) == "merge_requested"
    assert gh.writes() == [("pr", "edit", "1797", "--repo", "o/r", "--add-label", cc.PASS_LABEL),
                           ("pr", "merge", "1797", "--repo", "o/r", "--merge", "--auto", "--match-head-commit", HEAD)]


def test_block_labels_needs_human_and_never_merges(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, verdict("BLOCK", findings=[{"file": "x.py", "summary": "s", "failure": "f"}])) == "block"
    assert gh.writes() == [("pr", "edit", "1797", "--repo", "o/r", "--add-label", cc.HUMAN_LABEL)]


def test_a_verdict_for_another_head_is_no_verdict(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, verdict(head="0000000")) == "stale_verdict" and gh.writes() == []


def test_switches_off_or_an_unreadable_verdict(autonomy):
    gh = FakeGh()
    assert run(autonomy(False), gh, verdict()) == "off" and gh.calls == []
    assert run(autonomy(True), gh, verdict(), env={"JR_CODE_AUTOMERGE": "0"}) == "off"
    with pytest.raises(cc.Unreadable):
        run(autonomy(True), gh, "not json")
    with pytest.raises(cc.Unreadable):
        run(autonomy(True), gh, json.dumps({"verdict": "MAYBE", "head": HEAD}))


def test_one_agent_merge_per_hour(autonomy):
    gh = FakeGh(merged=[(1790, "2026-11-17T20:30:00Z")])
    assert run(autonomy(True), gh, verdict()) == "capped" and gh.writes() == []
    gh = FakeGh(merged=[(1780, "2026-11-17T19:30:00Z")])          # older than an hour: does not count
    assert run(autonomy(True), gh, verdict()) == "merge_requested"


def test_dry_run_never_writes(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, verdict(), dry_run=True) == "dry_run" and gh.writes() == []
    assert run(autonomy(True), gh, verdict("BLOCK"), dry_run=True) == "block" and gh.writes() == []


# --- the verdict comment is the one source of truth (both lanes write it; the canary reads it) --------------

def test_verdict_from_comments_takes_the_newest_marker_comment_for_the_current_head():
    import sys
    sys.path.insert(0, str(cc.REPO / "jr"))
    import agent_review as ar
    older = ar.render_comment(json.loads(verdict("BLOCK", head=HEAD, findings=[{"file": "x.py", "line": 3, "summary": "s", "failure": "f"}])), "subscription")
    newer = ar.render_comment(json.loads(verdict("PASS", head=HEAD)), "api")
    other = ar.render_comment(json.loads(verdict("PASS", head="a" * 40)), "subscription")
    calls = []
    def gh(*args):
        calls.append(args)
        if args[:2] == ("pr", "view"):
            return json.dumps({"headRefOid": HEAD.upper()})
        if args[:1] == ("api",):
            return json.dumps([{"body": "a human comment"}, {"user": {"login": "espatlas-jr"}, "body": older}, {"user": {"login": "espatlas-jr"}, "body": other}, {"user": {"login": "espatlas-jr"}, "body": newer}])
        return ""
    head, vj = cc.verdict_from_comments(gh, "o/r", 1797)
    assert head == HEAD and json.loads(vj)["verdict"] == "PASS" and json.loads(vj)["head"] == HEAD
    head, vj = cc.verdict_from_comments(lambda *a: json.dumps({"headRefOid": "b" * 40}) if a[:2] == ("pr", "view") else json.dumps([{"user": {"login": "espatlas-jr"}, "body": newer}]), "o/r", 1797)
    assert vj is None                                                  # a verdict for another head is no verdict


def test_the_cli_from_comments_is_a_noop_without_a_verdict_and_decides_with_one(monkeypatch, autonomy, capsys):
    import sys
    sys.path.insert(0, str(cc.REPO / "jr"))
    import agent_review as ar
    comment = ar.render_comment(json.loads(verdict("PASS", head=HEAD)), "subscription")
    store = {"comments": []}
    def gh(*args):
        if args[:2] == ("pr", "view") and "files,changedFiles" in args:
            return json.dumps({"files": [{"path": "jr/x.py"}], "changedFiles": 1})
        if args[:2] == ("pr", "view"):
            return json.dumps({"headRefOid": HEAD})
        if args[:1] == ("api",) and "/comments" in args[1]:
            return json.dumps(store["comments"])
        if args[:1] == ("api",):
            return "[]"
        return ""
    monkeypatch.setattr(cc.demand_canary, "default_gh", gh)
    monkeypatch.setattr(cc.demand_canary, "AUTONOMY", autonomy(on=True))
    assert cc.main(["--pr", "1797", "--from-comments", "--dry-run"]) == 0
    assert "outcome: no_verdict" in capsys.readouterr().out
    store["comments"] = [{"user": {"login": "mallory"}, "body": comment}]          # forged: still no verdict
    assert cc.main(["--pr", "1797", "--from-comments", "--dry-run"]) == 0
    assert "outcome: no_verdict" in capsys.readouterr().out
    store["comments"] = [{"user": {"login": "espatlas-jr"}, "body": comment}]
    assert cc.main(["--pr", "1797", "--from-comments", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "outcome: dry_run" in out and f"--match-head-commit {HEAD}" in out



def test_a_pass_already_queued_for_auto_merge_counts_against_the_hourly_cap(autonomy):
    # review BLOCK of #1809: --auto merges wait for checks, so only counting MERGED PRs let two land in one hour
    gh = FakeGh(queued=[1791])
    assert run(autonomy(True), gh, verdict()) == "capped" and gh.writes() == []



def test_a_pass_on_a_pr_touching_the_switches_ci_or_the_reviewer_goes_to_a_human(autonomy):
    for files in (["jr/autonomy.json"], ["jr/x.py", ".github/workflows/validate.yml"], ["scripts/demand_canary.py"],
                  ["jr/agent_review.py"], ["docs/REVIEW-CONTRACT.md"], ["scripts/validate_main.py"]):
        gh = FakeGh(files=files)
        assert run(autonomy(True), gh, verdict()) == "human_only", files
        assert not [c for c in gh.calls if c[:2] == ("pr", "merge")]
    gh = FakeGh(files=["jr/x.py"], changed=150)                         # list cut: cannot see every path
    assert run(autonomy(True), gh, verdict()) == "human_only"


# --- the sweep (2026-11-19): a verdict nobody acted on is acted on within the hour --------------------------
# The runner now posts several verdicts per run and the canary merges one PR an hour: the second PASS printed
# "this one waits for the next run" and there was no next run. A canary run that crashed (the first one ever
# did, on `import yaml`) left its verdict unanswered the same way.

class Repo:
    """A fake `gh` over a few open PRs: {number: dict(head, verdict, labels, draft, fork, files)}."""

    def __init__(self, prs, merged=(), lag=False, merge_fails=False):
        self.lag, self.merge_fails = lag, merge_fails
        import sys
        sys.path.insert(0, str(cc.REPO / "jr"))
        import agent_review as ar
        self.ar, self.prs, self.merged, self.calls = ar, prs, list(merged), []

    def _labels(self, n):
        return self.prs[n].setdefault("labels", [])

    def __call__(self, *args):
        self.calls.append(args)
        assert not (args[:2] == ("pr", "list") and "--label" in args)   # the label search lags: REST only
        if args[:2] == ("pr", "list"):
            return json.dumps([{"number": n, "isDraft": p.get("draft", False), "isCrossRepository": p.get("fork", False),
                                "autoMergeRequest": ({"enabledAt": p.get("armed_at", "x")} if p.get("armed") else None),
                                "labels": [{"name": x} for x in self._labels(n)]} for n, p in self.prs.items()])
        if args[:1] == ("api",) and "/issues?state=open" in args[1]:
            if self.lag:                                             # a read that has not caught up with a write
                return "[]"
            return json.dumps([{"number": n, "pull_request": {}} for n in self.prs if cc.PASS_LABEL in self._labels(n)])
        if args[:1] == ("api",) and "/pulls?state=closed" in args[1]:
            return json.dumps([{"number": n, "merged_at": t, "labels": [{"name": cc.PASS_LABEL}]} for n, t in self.merged])
        n = int(args[2]) if args[:2] in {("pr", "view"), ("pr", "edit"), ("pr", "merge")} else None
        if args[:2] == ("pr", "view") and "files,changedFiles" in args:
            files = self.prs[n].get("files", ["jr/x.py"])
            return json.dumps({"files": [{"path": f} for f in files], "changedFiles": len(files)})
        if args[:2] == ("pr", "view") and "state,autoMergeRequest" in args:
            return json.dumps({"state": self.prs[n].get("state", "OPEN"),
                               "autoMergeRequest": {"enabledAt": "x"} if self.prs[n].get("armed") else None})
        if args[:2] == ("pr", "view") and "mergeable" in args:
            answers = self.prs[n].get("mergeable", "MERGEABLE")
            if isinstance(answers, list):                           # GitHub computes it lazily: UNKNOWN, then the answer
                answers = answers.pop(0) if len(answers) > 1 else answers[0]
            return json.dumps({"mergeable": answers})
        if args[:2] == ("pr", "view"):
            if self.prs[n].get("unreadable"):
                return "not json"
            return json.dumps({"headRefOid": self.prs[n]["head"]})
        if args[:1] == ("api",):
            n = int(args[1].split("/issues/")[1].split("/")[0])
            v = self.prs[n].get("verdict")
            body = self.ar.render_comment(json.loads(verdict(v, head=self.prs[n].get("verdict_head", self.prs[n]["head"]))), "subscription") if v else "hi"
            return json.dumps([{"user": {"login": "espatlas-jr"}, "body": body}])
        if args[:2] == ("pr", "edit") and "--add-label" in args:
            self._labels(n).append(args[args.index("--add-label") + 1])
        if args[:2] == ("pr", "edit") and "--remove-label" in args:
            self._labels(n).remove(args[args.index("--remove-label") + 1])
        if args[:2] == ("pr", "merge") and "--disable-auto" in args:
            self.prs[n]["armed"] = False
            return ""
        if args[:2] == ("pr", "merge"):
            if self.merge_fails == "after":           # GitHub applied it, the answer got lost
                self.prs[n]["state"] = "MERGED"
            if self.merge_fails:
                raise RuntimeError("gh pr merge: HTTP 502")
            self.prs[n]["armed"] = True
        return ""

    def merges(self):
        return [int(c[2]) for c in self.calls if c[:2] == ("pr", "merge") and "--disable-auto" not in c]

    def disarmed(self):
        return [int(c[2]) for c in self.calls if c[:2] == ("pr", "merge") and "--disable-auto" in c]

    def labelled(self):
        return [(int(c[2]), c[c.index("--add-label") + 1]) for c in self.calls if c[:2] == ("pr", "edit") and "--add-label" in c]


def sweep(gh, autonomy_path, **kw):
    args = dict(repo_slug="o/r", now=NOW, env={}, autonomy_path=autonomy_path, gh=gh)
    args.update(kw)
    return cc.sweep(**args)


def h(c):
    return c * 40


def test_the_sweep_merges_the_oldest_standing_pass_and_leaves_the_rest_for_the_next_hour(autonomy):
    gh = Repo({1843: dict(head=h("c"), verdict="PASS"), 1841: dict(head=h("a"), verdict="PASS"), 1842: dict(head=h("b"))})
    out = sweep(gh, autonomy(True))
    assert gh.merges() == [1841]                                   # one an hour; 1843 keeps its verdict
    assert out == {1841: "merge_requested", 1843: "capped"}        # 1842 has no verdict: not mentioned


def test_the_sweep_merges_nothing_while_this_hours_merge_is_used(autonomy):
    gh = Repo({1841: dict(head=h("a"), verdict="PASS")}, merged=[(1799, "2026-11-17T20:30:00Z")])
    assert sweep(gh, autonomy(True)) == {1841: "capped"} and gh.merges() == []


def test_a_block_nobody_labelled_gets_its_label_and_a_labelled_one_costs_no_write(autonomy):
    gh = Repo({1797: dict(head=h("a"), verdict="BLOCK"), 1798: dict(head=h("b"), verdict="BLOCK", labels=[cc.HUMAN_LABEL])})
    out = sweep(gh, autonomy(True))
    assert gh.labelled() == [(1797, cc.HUMAN_LABEL)] and gh.merges() == []
    assert out == {1797: "block", 1798: "block_known"}


def test_a_block_is_still_labelled_after_the_cap_stopped_the_merges(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS"), 2: dict(head=h("b"), verdict="PASS"), 3: dict(head=h("c"), verdict="BLOCK")})
    out = sweep(gh, autonomy(True))
    assert out == {1: "merge_requested", 2: "capped", 3: "block"} and gh.labelled()[-1] == (3, cc.HUMAN_LABEL)


def test_drafts_forks_queued_merges_and_stale_verdicts_are_left_alone(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS", draft=True), 2: dict(head=h("b"), verdict="PASS", fork=True),
               3: dict(head=h("c"), verdict="PASS", labels=[cc.PASS_LABEL], armed=True),
               4: dict(head=h("d"), verdict="PASS", verdict_head=h("e"))})
    assert sweep(gh, autonomy(True)) == {3: "queued"}
    assert gh.merges() == [] and gh.labelled() == []
    assert not [c for c in gh.calls if c[:1] == ("api",) and ("/issues/1/" in c[1] or "/issues/2/" in c[1])]


def test_a_pass_on_a_human_only_path_is_labelled_once_and_never_merged(autonomy):
    gh = Repo({1870: dict(head=h("a"), verdict="PASS", files=[".github/workflows/validate.yml"])})
    assert sweep(gh, autonomy(True)) == {1870: "human_only"} and gh.merges() == []
    assert sweep(gh, autonomy(True)) == {1870: "human_only_known"}
    assert gh.labelled() == [(1870, cc.HUMAN_LABEL)]                # the second sweep wrote nothing


def test_one_unreadable_pr_never_stops_the_sweep(autonomy):
    gh = Repo({1: dict(head=h("a"), unreadable=True), 2: dict(head=h("b"), verdict="PASS")})
    out = sweep(gh, autonomy(True))
    assert out[2] == "merge_requested" and out[1].startswith("unreadable")


def test_the_sweep_does_nothing_with_the_switch_off_or_in_a_dry_run(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS"), 2: dict(head=h("b"), verdict="BLOCK")})
    assert sweep(gh, autonomy(False)) == {} and gh.calls == []
    assert sweep(gh, autonomy(True), env={"JR_CODE_AUTOMERGE": "0"}) == {} and gh.calls == []
    out = sweep(gh, autonomy(True), dry_run=True)
    assert out == {1: "dry_run", 2: "block"} and gh.merges() == [] and gh.labelled() == []


# --- review BLOCK of #1871 (2026-11-19): the cap must hold whatever a read returns ------------------------------

def test_one_sweep_requests_one_merge_even_when_githubs_reads_lag_behind_its_own_writes(autonomy):
    gh = Repo({1841: dict(head=h("a"), verdict="PASS"), 1843: dict(head=h("b"), verdict="PASS"),
               1844: dict(head=h("c"), verdict="PASS")}, lag=True)
    out = sweep(gh, autonomy(True))
    assert gh.merges() == [1841] and out == {1841: "merge_requested", 1843: "capped", 1844: "capped"}


def test_a_merge_already_queued_uses_the_cap_for_the_whole_sweep_even_on_a_lagging_read(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS", labels=[cc.PASS_LABEL], armed=True),
               2: dict(head=h("b"), verdict="PASS")}, lag=True)
    assert sweep(gh, autonomy(True)) == {1: "queued", 2: "capped"} and gh.merges() == []


def test_the_cap_is_never_read_through_the_label_search(autonomy):
    gh = FakeGh(merged=[(1799, "2026-11-17T20:30:00Z")])
    assert run(autonomy(True), gh, verdict()) == "capped"
    assert not [c for c in gh.calls if c[:2] == ("pr", "list")]
    urls = [c[1] for c in gh.calls if c[:1] == ("api",)]
    assert any("/pulls?state=closed" in u for u in urls) and any("/issues?state=open" in u for u in urls)
    old = FakeGh(merged=[(1700, "2026-11-17T19:59:00Z")])                # merged 61 minutes ago: the hour is free
    assert run(autonomy(True), old, verdict()) == "merge_requested"


def test_a_capped_human_only_pass_still_gets_its_label(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS"), 2: dict(head=h("b"), verdict="PASS", files=[".github/x.yml"])})
    assert sweep(gh, autonomy(True)) == {1: "merge_requested", 2: "human_only"}
    assert (2, cc.HUMAN_LABEL) in gh.labelled()


def test_a_merge_request_that_fails_takes_its_label_back(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS")}, merge_fails=True)
    out = sweep(gh, autonomy(True))
    assert out[1].startswith("unreadable") and cc.PASS_LABEL not in gh.prs[1]["labels"]


def test_a_merge_into_a_stacked_base_uses_the_hours_cap_like_any_other(autonomy):
    # 2nd review of #1871: the per-comment path merges a stacked PR into its base branch; the read must see it
    gh = FakeGh(merged=[(10, "2026-11-17T20:50:00Z")])
    assert run(autonomy(True), gh, verdict()) == "capped"
    url = next(c[1] for c in gh.calls if c[:1] == ("api",) and "/pulls?state=closed" in c[1])
    assert "base=" not in url


def test_a_merge_call_that_fails_after_github_applied_it_keeps_its_label_and_the_cap(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS"), 2: dict(head=h("b"), verdict="PASS")}, merge_fails="after", lag=True)
    out = sweep(gh, autonomy(True))
    assert out == {1: "merge_requested", 2: "capped"} and cc.PASS_LABEL in gh.prs[1]["labels"]


def test_a_decision_that_dies_on_a_pass_uses_the_cap_for_the_rest_of_the_sweep(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS"), 2: dict(head=h("b"), verdict="PASS")}, merge_fails=True, lag=True)
    out = sweep(gh, autonomy(True))
    assert out[1].startswith("unreadable") and out[2] == "capped" and gh.merges() == [1]


def test_a_stale_label_on_a_newer_pr_never_caps_an_older_pass(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS"), 2: dict(head=h("b"), verdict="PASS", labels=[cc.PASS_LABEL])})
    assert sweep(gh, autonomy(True)) == {1: "merge_requested", 2: "capped"} and gh.merges() == [1]


def test_an_agent_pass_label_with_no_merge_behind_it_is_dropped_and_the_pr_decided_again(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS", labels=[cc.PASS_LABEL])})       # labelled, never armed
    assert sweep(gh, autonomy(True)) == {1: "merge_requested"} and gh.merges() == [1]
    stale = Repo({2: dict(head=h("b"), verdict="PASS", verdict_head=h("c"), labels=[cc.PASS_LABEL])})
    assert sweep(stale, autonomy(True)) == {} and cc.PASS_LABEL not in stale.prs[2]["labels"]


def test_the_cli_sweep_prints_every_decision_and_exits_zero(monkeypatch, autonomy, capsys):
    gh = Repo({1841: dict(head=h("a"), verdict="PASS")})
    monkeypatch.setattr(cc.demand_canary, "default_gh", gh)
    monkeypatch.setattr(cc.demand_canary, "AUTONOMY", autonomy(True))
    assert cc.main(["--sweep", "--repo-slug", "o/r"]) == 0
    text = capsys.readouterr().out
    assert "sweep: #1841 merge_requested" in text and gh.merges() == [1841]


def test_the_cli_needs_a_pr_or_the_sweep(capsys):
    with pytest.raises(SystemExit):
        cc.main([])


# --- an armed merge that cannot land never holds the hour (2026-11-20) --------------------------------------
# #1851 had a PASS and conflicted with main. The canary armed its merge at 03:14Z; GitHub never merges a
# conflicted PR, the armed merge counted as "this hour's merge" every hour, and four reviewed PRs waited
# behind it until a person disarmed it at 07:55Z.

def test_a_conflicting_pass_is_never_armed_and_never_uses_the_cap(autonomy):
    gh = Repo({1851: dict(head=h("a"), verdict="PASS", mergeable="CONFLICTING"), 1797: dict(head=h("b"), verdict="PASS")})
    out = sweep(gh, autonomy(True), pause=lambda s: None)
    assert out == {1851: "conflict", 1797: "merge_requested"} and gh.merges() == [1797]
    assert gh.labelled() == [(1797, cc.PASS_LABEL)]                 # the conflicting one gets no label at all


def test_mergeability_github_has_not_computed_yet_is_asked_again_before_arming(autonomy):
    waits = []
    gh = Repo({1851: dict(head=h("a"), verdict="PASS", mergeable=["UNKNOWN", "UNKNOWN", "CONFLICTING"])})
    assert sweep(gh, autonomy(True), pause=waits.append) == {1851: "conflict"} and gh.merges() == [] and len(waits) == 2
    gh = Repo({1: dict(head=h("a"), verdict="PASS", mergeable=["UNKNOWN"])})          # never settles: armed, the sweep is the backstop
    assert sweep(gh, autonomy(True), pause=lambda s: None) == {1: "merge_requested"}


def test_the_sweep_disarms_an_armed_merge_that_conflicts_and_gives_the_hour_to_the_next_pass(autonomy):
    gh = Repo({1851: dict(head=h("a"), verdict="PASS", labels=[cc.PASS_LABEL], armed=True, armed_at="2026-11-17T20:50:00Z",
                          mergeable="CONFLICTING"),
               1797: dict(head=h("b"), verdict="PASS"), 1896: dict(head=h("c"), verdict="PASS")}, lag=True)
    out = sweep(gh, autonomy(True), pause=lambda s: None)
    assert gh.disarmed() == [1851] and cc.PASS_LABEL not in gh.prs[1851]["labels"] and gh.prs[1851]["armed"] is False
    assert out == {1851: "conflict", 1797: "merge_requested", 1896: "capped"} and gh.merges() == [1797]


def test_the_sweep_disarms_a_merge_armed_over_an_hour_ago_and_does_not_arm_it_again_in_the_same_sweep(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS", labels=[cc.PASS_LABEL], armed=True, armed_at="2026-11-17T19:59:00Z"),
               2: dict(head=h("b"), verdict="PASS")})
    out = sweep(gh, autonomy(True), pause=lambda s: None)
    assert gh.disarmed() == [1] and out == {1: "disarmed_stuck", 2: "merge_requested"} and gh.merges() == [2]


def test_a_merge_armed_within_the_hour_and_mergeable_still_holds_the_cap(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS", labels=[cc.PASS_LABEL], armed=True, armed_at="2026-11-17T20:01:00Z"),
               2: dict(head=h("b"), verdict="PASS")})
    assert sweep(gh, autonomy(True), pause=lambda s: None) == {1: "queued", 2: "capped"}
    assert gh.disarmed() == [] and gh.merges() == []
    gh = Repo({1: dict(head=h("a"), verdict="PASS", labels=[cc.PASS_LABEL], armed=True, armed_at="not a date"),
               2: dict(head=h("b"), verdict="PASS")})                 # an unreadable date is not "stuck"
    assert sweep(gh, autonomy(True), pause=lambda s: None) == {1: "queued", 2: "capped"} and gh.disarmed() == []


def test_a_dry_run_reports_a_stuck_merge_and_disarms_nothing(autonomy):
    gh = Repo({1: dict(head=h("a"), verdict="PASS", labels=[cc.PASS_LABEL], armed=True, armed_at="2026-11-17T19:00:00Z"),
               2: dict(head=h("b"), verdict="PASS")})
    out = sweep(gh, autonomy(True), dry_run=True, pause=lambda s: None)
    # the label is still on #1 in a dry run, and the next PASS is still reported as free to merge
    assert out == {1: "disarmed_stuck", 2: "dry_run"} and gh.disarmed() == [] and gh.prs[1]["armed"] is True
    assert gh.merges() == [] and cc.PASS_LABEL in gh.prs[1]["labels"]


def test_a_stuck_merge_that_cannot_be_disarmed_keeps_the_cap_and_is_reported(autonomy):
    # lag: GitHub's own read shows nothing queued, so only this sweep's count keeps the hour used
    gh = Repo({1: dict(head=h("a"), verdict="PASS", labels=[cc.PASS_LABEL], armed=True, armed_at="2026-11-17T19:00:00Z"),
               2: dict(head=h("b"), verdict="PASS")}, lag=True)
    real = gh.__call__

    def failing(*args):
        if args[:2] == ("pr", "merge") and "--disable-auto" in args:
            raise RuntimeError("gh pr merge: HTTP 502")
        return real(*args)
    out = cc.sweep(repo_slug="o/r", now=NOW, env={}, autonomy_path=autonomy(True), gh=failing, pause=lambda s: None)
    assert out[1].startswith("unreadable") and out[2] == "capped"     # still armed: the hour stays used
    assert gh.merges() == [] and gh.prs[1]["armed"] is True
