"""scripts/demand_canary.py — a demand PR every machine check accepts merges itself; everything else is a
printed decision and no action. Fakes: `gh` recorded, pages injected, the records to check injected."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import check_quotes as cq
import demand_canary as dc

FIX = Path(__file__).resolve().parent / "fixtures" / "quotes"
RECORD = FIX / "freenove-esp32-wrover.board.md"
PREFACE = (FIX / "freenove-fnk0060-preface.txt").read_text()
PREFACE_URL = "https://docs.freenove.com/projects/fnk0060/en/latest/fnk0060/codes/C/Preface.html"
REPO_URL = "https://github.com/Freenove/Freenove_ESP32_WROVER_Board"
HEAD = "fd0359e403921a33c999412735c802c6feb59e9a"
BRANCH = "jr/research-pam-23266c59174397dbf41b0a7b"


class FakeGh:
    def __init__(self, merged=(), queued=()):
        self.calls, self.merged, self.queued = [], list(merged), list(queued)

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("pr", "list") and args[args.index("--state") + 1] == "open":
            return json.dumps([{"headRefName": b, "autoMergeRequest": {"enabledAt": "x"}} for b in self.queued])
        if args[:2] == ("pr", "list"):
            return json.dumps([{"headRefName": b, "mergedAt": f"{d}T10:00:00Z"} for b, d in self.merged])
        return ""

    def writes(self):
        return [c for c in self.calls if c[:2] in {("pr", "ready"), ("pr", "merge"), ("pr", "comment"), ("pr", "edit")}]


def pages(preface=PREFACE):
    fm, _ = cq.parse_frontmatter(RECORD)
    p = {u: "unrelated page" for u in cq.cited_urls(fm)}
    p[PREFACE_URL] = preface
    p[REPO_URL] = "Freenove_ESP32_WROVER_Board kit"
    return p


def fake_fetch(p):
    return lambda url: cq.Page(url, cq.normalize(p[url]) if p.get(url) is not None else None, "fake" if p.get(url) is not None else "HTTP 429")


@pytest.fixture
def autonomy(tmp_path):
    def write(on=True):
        f = tmp_path / "autonomy.json"
        f.write_text(json.dumps({"demand_automerge": on}))
        return f
    return write


@pytest.fixture(autouse=True)
def changed(monkeypatch):
    monkeypatch.setattr(cq, "changed_records", lambda base, repo=None: [RECORD])


def run(autonomy_path, gh, fetch, env=None, **kw):
    args = dict(pr=1800, head=HEAD, branch=BRANCH, base="origin/main", repo_slug="o/r", today="2026-11-17",
                env=env or {}, autonomy_path=autonomy_path, gh=gh, fetch=fetch)
    args.setdefault("paths", ["data/boards/x/board.md"])
    args.update(kw)
    return dc.decide(**args)


def test_the_happy_path_marks_ready_and_requests_the_merge_at_the_exact_head(autonomy, capsys):
    gh = FakeGh()
    assert run(autonomy(True), gh, fake_fetch(pages())) == "merge_requested"
    assert gh.writes() == [("pr", "ready", "1800", "--repo", "o/r"),
                           ("pr", "merge", "1800", "--repo", "o/r", "--merge", "--auto", "--match-head-commit", HEAD)]
    out = capsys.readouterr().out
    assert "D4 daily cap free" in out and "D5 quotes PASS" in out and "D6 #1800 marked ready" in out


def test_the_file_switch_off_means_no_gh_call_at_all(autonomy, capsys):
    gh = FakeGh()
    assert run(autonomy(False), gh, fake_fetch(pages())) == "off"
    assert gh.calls == [] and "a reviewed PR turns it on" in capsys.readouterr().out


def test_the_repository_variable_zero_is_the_kill_switch(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, fake_fetch(pages()), env={"JR_DEMAND_AUTOMERGE": "0"}) == "off"
    assert gh.calls == []
    assert run(autonomy(True), gh, fake_fetch(pages()), env={"JR_DEMAND_AUTOMERGE": "1"}) == "merge_requested"


def test_an_unreadable_autonomy_file_is_off(tmp_path):
    gh = FakeGh()
    assert run(tmp_path / "missing.json", gh, fake_fetch(pages())) == "off" and gh.calls == []


def test_not_a_demand_branch_does_nothing(autonomy):
    gh = FakeGh()
    assert run(autonomy(True), gh, fake_fetch(pages()), branch="feat/x") == "not_demand" and gh.calls == []


def test_one_demand_merge_per_utc_day(autonomy, capsys):
    gh = FakeGh(merged=[("jr/research-pam-other", "2026-11-17"), ("jr/tick-20261117-1200", "2026-11-17")])
    assert run(autonomy(True), gh, fake_fetch(pages())) == "capped"
    assert gh.writes() == [] and "jr/research-pam-other" in capsys.readouterr().out
    gh = FakeGh(merged=[("jr/research-pam-other", "2026-11-16")])                 # yesterday's does not count
    assert run(autonomy(True), gh, fake_fetch(pages())) == "merge_requested"


def test_a_failing_quote_comments_labels_and_never_merges(autonomy, capsys):
    gh = FakeGh()
    bad = pages(preface=PREFACE.replace("CH340 to download codes", "CH341 to download codes"))
    assert run(autonomy(True), gh, fake_fetch(bad)) == "fail"
    kinds = [c[:2] for c in gh.writes()]
    assert kinds == [("pr", "comment"), ("pr", "edit")]
    comment = gh.writes()[0]
    assert "ESP32 uses CH340 to download codes" in comment[comment.index("--body") + 1]
    assert gh.writes()[1][-2:] == ("--add-label", dc.LABEL)
    assert "D5 quotes FAIL" in capsys.readouterr().out


def test_an_inconclusive_page_waits_for_the_next_run_without_acting(autonomy, capsys):
    gh = FakeGh()
    assert run(autonomy(True), gh, fake_fetch(pages(preface=None))) == "inconclusive"
    assert gh.writes() == [] and "re-checked on the next run" in capsys.readouterr().out


def test_dry_run_decides_but_never_writes(autonomy, capsys):
    gh = FakeGh()
    assert run(autonomy(True), gh, fake_fetch(pages()), dry_run=True) == "dry_run"
    assert gh.writes() == [] and "would mark #1800 ready" in capsys.readouterr().out
    bad = pages(preface=PREFACE.replace("CH340 to download codes", "CH341 to download codes"))
    assert run(autonomy(True), gh, fake_fetch(bad), dry_run=True) == "fail" and gh.writes() == []


def test_a_pr_with_no_quoted_text_still_merges_on_the_other_checks(autonomy, tmp_path, monkeypatch, capsys):
    plain = tmp_path / "board.md"
    plain.write_text("---\nid: x\nname: Plain\nsources:\n- field: '*'\n  url: https://x/\n---\nBody.\n")
    monkeypatch.setattr(cq, "changed_records", lambda base, repo=None: [plain])
    gh = FakeGh()
    assert run(autonomy(True), gh, fake_fetch({})) == "merge_requested"
    assert "no quoted text" in capsys.readouterr().out


def test_the_shipped_autonomy_file_is_the_reviewed_state():
    # every lane turned on by a reviewed PR (owner, 2026-11-19); the tick lane after evidence rules v4 (#1864)
    doc = json.loads((Path(__file__).resolve().parent.parent / "jr" / "autonomy.json").read_text())
    assert doc["demand_automerge"] is True and doc["code_automerge"] is True and doc["tick_automerge"] is True



# --- review BLOCK of #1809 (2026-11-19): a PR could switch its own canary on, or carry code the canary would merge

def test_a_pr_that_changes_anything_outside_its_scope_is_never_merged(autonomy):
    for paths in (["jr/autonomy.json"], ["data/boards/x/board.md", "scripts/demand_canary.py"], [".github/workflows/validate.yml"]):
        gh = FakeGh()
        assert run(autonomy(True), gh, fake_fetch(pages()), paths=paths) == "out_of_scope", paths
        assert not [c for c in gh.calls if c[:2] in (("pr", "merge"), ("pr", "ready"), ("pr", "edit"))]
    import demand_canary
    assert demand_canary.out_of_scope(None, demand_canary.DEMAND_SCOPE) is None          # unreadable: never merged


def test_the_switch_is_read_from_main_never_from_the_prs_tree(tmp_path):
    import subprocess as sp
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t", "PATH": __import__("os").environ["PATH"]}
    g = lambda *a: sp.run(["git", *a], cwd=tmp_path, env=env, check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    (tmp_path / "jr").mkdir()
    (tmp_path / "jr" / "autonomy.json").write_text('{"demand_automerge": false, "tick_automerge": false}')
    g("add", "."), g("commit", "-qm", "main")
    g("checkout", "-qb", "pr")
    (tmp_path / "jr" / "autonomy.json").write_text('{"demand_automerge": true, "tick_automerge": true}')
    g("commit", "-qam", "the PR turns itself on")
    import demand_canary
    p = demand_canary.trusted_autonomy("main", tmp_path)
    assert __import__("json").loads(p.read_text()) == {"demand_automerge": False, "tick_automerge": False}
    assert not demand_canary.trusted_autonomy("no-such-ref", tmp_path).exists()



def test_a_merge_already_queued_today_counts_against_the_daily_cap(autonomy):
    gh = FakeGh(queued=["jr/research-pam-other"])
    assert run(autonomy(True), gh, fake_fetch(pages())) == "capped" and gh.writes() == []
