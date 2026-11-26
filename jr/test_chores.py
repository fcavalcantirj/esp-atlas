"""Jr's chores (jr/chores.py, SPEC-jr-self-heal.md §1d, 2026-11-18): the routine work a person did on open PRs.

Owner, Nov 18: "make jr automatically do chores. site must be self sufficient." Measured that night: 31 open
PRs, 8 conflicting with main and resolved by hand, every agent BLOCK waiting for a person. Each hourly tick
now (a) records a `conflict:#n` incident for a code PR that conflicts with main, (b) records a
`review-fix:#n` incident for a PR whose agent review is BLOCK at its current head, with the findings as
evidence, (c) resolves those incidents when the PR is fixed, merged or closed, and (d) once a UTC day tells
the owner what still needs a human. Incidents reach the delegate only through `claim --pr-fix` and the
`pr_fix_dispatch` switch. Deterministic, fake gh only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from types import SimpleNamespace

import agent_review as ar
import chores
import ci_watch as cw

@pytest.fixture(autouse=True)
def _the_expiry_never_reaches_git_or_the_network(monkeypatch):
    """chores.run() ends with expire_tick_prs, whose defaults fetch a branch and read live upstreams. No test
    may do that by accident: a test that means to exercise it stubs both itself."""
    def not_stubbed(*a, **k):
        raise RuntimeError("this test did not stub the tick-PR expiry")
    monkeypatch.setattr(chores, "_fetch_branch", not_stubbed)
    monkeypatch.setattr(chores, "_guard", not_stubbed)


def trend_row(date, firmware=170, recipes=348, with_fw=62, zero_fw=59, usb=66):
    return {"date": date, "firmware_count": firmware, "recipe_count": recipes, "boards_with_firmware": with_fw,
            "boards_zero_firmware": zero_fw, "board_fields": {"usb_serial": {"count": usb, "pct": 54.5}}}


def write_trend(path, rows):
    import json as _json
    path.write_text("".join(_json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _a_growing_catalog_unless_a_test_says_otherwise(monkeypatch, tmp_path):
    """The daily line reads the catalog's growth from docs/telemetry/data-trend.jsonl. Every test gets a trend
    that grew by one firmware each day of November, so only the tests about growth see anything else."""
    rows = [trend_row(f"2026-11-{d:02d}", firmware=150 + d) for d in range(1, 31)]
    monkeypatch.setattr(chores, "TREND", write_trend(tmp_path / "data-trend.jsonl", rows))


NOW = "2026-11-19T12:05:00+00:00"
LATER = "2026-11-19T13:05:00+00:00"
H1, H2 = "1" * 40, "2" * 40


def pr(n, state="CLEAN", branch="feat/x", head=H1, labels=(), draft=False, base="main", fork=False,
       updated="2026-11-19T10:00:00Z", created="2026-11-19T09:00:00Z"):
    return {"number": n, "headRefName": branch, "headRefOid": head, "mergeStateStatus": state, "isDraft": draft,
            "labels": [{"name": l} for l in labels], "baseRefName": base, "isCrossRepository": fork,
            "updatedAt": updated, "createdAt": created}


def block(head=H1, findings=("jr/x.py:3 the loop never ends",)):
    v = {"verdict": "BLOCK", "head": head, "findings": list(findings), "checked": ["pytest"]}
    return {"user": {"login": "espatlas-jr"}, "body": ar.render_comment(v, "subscription")}


class Gh:
    def __init__(self, prs, comments=None, states=None, merged=()):
        self.prs, self.comments, self.states, self.calls = prs, comments or {}, states or {}, []
        self.merged = list(merged) if merged is not None else None          # None: the merged list fails

    def __call__(self, *a):
        self.calls.append(a)
        if a[:2] == ("pr", "list") and "merged" in a:
            if self.merged is None:
                return SimpleNamespace(returncode=1, stdout="", stderr="HTTP 502")
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.merged), stderr="")
        if a[:2] == ("pr", "list"):
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.prs), stderr="")
        if a[:2] == ("pr", "view"):
            return SimpleNamespace(returncode=0, stdout=json.dumps({"state": self.states.get(int(a[2]), "OPEN")}), stderr="")
        if a[:1] == ("api",) and "/issues/" in a[1]:
            n = int(a[1].split("/issues/")[1].split("/")[0])
            return SimpleNamespace(returncode=0, stdout=json.dumps(self.comments.get(n, [])), stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="unexpected")


def _store(tmp_path):
    return cw.Store(tmp_path / "incidents.json")


def _incidents(store):
    return {r["context"]["check"]: r for r in store._load()["incidents"].values()}


def test_a_code_pr_conflicting_with_main_is_a_conflict_incident_with_its_branch_and_head(tmp_path):
    store = _store(tmp_path)
    out = chores.run(Gh([pr(7, "DIRTY", branch="feat/y", head=H1), pr(8)]), store, NOW, slug="o/r")
    rec = _incidents(store)["conflict:#7"]
    ev = rec["context"]["evidence"]
    assert ev["pr"] == 7 and ev["pr_branch"] == "feat/y" and ev["pr_head"] == H1 and rec["state"] == "open"
    assert out["recorded"] == [rec["id"]] and len(_incidents(store)) == 1


def test_tick_research_drafts_forks_and_stacked_prs_are_never_chores(tmp_path):
    store = _store(tmp_path)
    prs = [pr(1, "DIRTY", branch="jr/tick-20261118-0700"), pr(2, "DIRTY", branch="jr/research-pam-1"),
           pr(3, "DIRTY", draft=True), pr(4, "DIRTY", fork=True), pr(5, "DIRTY", base="feat/base")]
    chores.run(Gh(prs), store, NOW, slug="o/r")
    assert _incidents(store) == {}


def test_a_heal_pr_in_conflict_is_a_chore(tmp_path):
    store = _store(tmp_path)
    chores.run(Gh([pr(9, "DIRTY", branch="jr/heal-abc123def456")]), store, NOW, slug="o/r")
    assert "conflict:#9" in _incidents(store)


def test_a_block_verdict_at_the_current_head_is_a_review_fix_incident_with_the_findings(tmp_path):
    store = _store(tmp_path)
    gh = Gh([pr(11, labels=["needs-human"], head=H1)], comments={11: [block(H1)]})
    chores.run(gh, store, NOW, slug="o/r")
    ev = _incidents(store)["review-fix:#11"]["context"]["evidence"]
    assert ev["findings"] == ["jr/x.py:3 the loop never ends"] and ev["pr_head"] == H1


def test_a_block_for_an_older_head_is_not_a_review_fix(tmp_path):
    store = _store(tmp_path)
    gh = Gh([pr(11, labels=["needs-human"], head=H2)], comments={11: [block(H1)]})
    chores.run(gh, store, NOW, slug="o/r")
    assert _incidents(store) == {}


def test_comments_are_read_only_for_prs_labelled_needs_human(tmp_path):
    gh = Gh([pr(1), pr(2, "DIRTY"), pr(3, labels=["needs-human"])])
    chores.run(gh, _store(tmp_path), NOW, slug="o/r")
    assert [c[1] for c in gh.calls if c[:1] == ("api",)] == ["repos/o/r/issues/3/comments"]


def test_a_fixed_pr_resolves_its_incident(tmp_path):
    store = _store(tmp_path)
    chores.run(Gh([pr(7, "DIRTY")]), store, NOW, slug="o/r")
    chores.run(Gh([pr(7, "CLEAN", head=H2)]), store, LATER, slug="o/r")
    assert _incidents(store)["conflict:#7"]["state"] == "open"                 # one absent pass may be a blink
    out = chores.run(Gh([pr(7, "CLEAN", head=H2)]), store, "2026-11-19T14:05:00+00:00", slug="o/r")
    assert _incidents(store)["conflict:#7"]["state"] == "resolved" and len(out["resolved"]) == 1


def test_pr_fix_dispatches_never_move_the_human_ack_brake(tmp_path):
    # 5th review of #1857: every "credit" rule for a PR fix could be gamed; PR fixes are bounded on their own
    store = _store(tmp_path)
    chores.run(Gh([pr(n, "DIRTY") for n in (7, 8, 9)]), store, NOW, slug="o/r")
    for _ in range(3):
        assert store.claim(NOW, allow_pr_fix=True)
    assert int(store._load().get("auto_since_ack") or 0) == 0 and not store._load().get("halted")
    chores.run(Gh([], states={7: "MERGED", 8: "CLOSED", 9: "MERGED"}), store, LATER, slug="o/r")
    assert int(store._load().get("auto_since_ack") or 0) == 0
    assert {r["state"] for r in _incidents(store).values()} == {"resolved"}

def test_a_dispatched_fix_that_pushed_a_new_head_is_marked_pushed(tmp_path):
    store = _store(tmp_path)
    chores.run(Gh([pr(7, "DIRTY", head=H1)]), store, NOW, slug="o/r")
    store.claim(NOW, allow_pr_fix=True)
    chores.run(Gh([pr(7, "DIRTY", head=H2)]), store, LATER, slug="o/r")
    rec = _incidents(store)["conflict:#7"]
    assert rec["state"] == "pushed" and rec["pushed_head"] == H2


def merged(*logins):
    return [{"number": 100 + i, "headRefName": "x", "mergedBy": {"login": l}} for i, l in enumerate(logins)]


def merged_jr(*logins, branch="jr/tick-20261119-0100"):
    return [{"number": 200 + i, "headRefName": branch, "mergedBy": {"login": l}} for i, l in enumerate(logins)]


def test_the_daily_line_comes_once_a_utc_day_from_12z_with_the_numbers(tmp_path):
    store = _store(tmp_path)
    prs = [pr(3, branch="jr/tick-20261118-0700", labels=["needs-human"], updated="2026-11-18T12:00:00Z")]
    gh = Gh(prs, merged=merged_jr("espatlas-jr", "espatlas-jr", "fcavalcantirj"))
    early = chores.run(gh, store, "2026-11-19T11:05:00+00:00", slug="o/r")
    first = chores.run(gh, store, NOW, slug="o/r")
    again = chores.run(gh, store, LATER, slug="o/r")
    assert early["digest"] is None and again["digest"] is None
    line = first["digest"]
    assert line.startswith("🧹 Jr daily 2026-11-19") and "merged by Jr 2" in line and "Jr's PRs merged by a person 1" in line
    assert "#3 needs-human 24 h" in line and "self-sufficient 0/7 days" in line


def _day(store, gh, day):
    return chores.run(gh, store, f"2026-11-{day}T12:05:00+00:00", slug="o/r")["digest"]


def test_self_sufficient_days_count_up_and_a_human_merge_breaks_the_run(tmp_path):
    store = _store(tmp_path)
    clean = Gh([], merged=merged("espatlas-jr", "github-actions[bot]"))
    assert "self-sufficient 1/7 days" in _day(store, clean, 19)
    assert "self-sufficient 2/7 days" in _day(store, clean, 20)
    assert "self-sufficient 0/7 days" in _day(store, Gh([], merged=merged_jr("fcavalcantirj")), 21)   # a person merged JR'S PR
    assert "self-sufficient 1/7 days" in _day(store, clean, 22)


def test_a_waiting_needs_human_pr_or_a_halted_heal_is_not_a_self_sufficient_day(tmp_path):
    store = _store(tmp_path)
    assert "self-sufficient 0/7 days" in _day(store, Gh([pr(3, branch="jr/heal-abc", labels=["needs-human"])], merged=[]), 19)
    data = store._load()
    data["halted"] = True
    store._save(data)
    assert "self-sufficient 0/7 days" in _day(store, Gh([pr(1)], merged=[]), 20)


def test_unreadable_merges_never_count_as_a_self_sufficient_day(tmp_path):
    line = _day(_store(tmp_path), Gh([pr(1)], merged=None), 19)
    assert "merges unreadable" in line and "self-sufficient 0/7 days" in line


def test_seven_days_say_so(tmp_path):
    store = _store(tmp_path)
    clean = Gh([], merged=merged("espatlas-jr"))
    lines = [_day(store, clean, d) for d in range(19, 26)]
    assert "self-sufficient 7/7 days" in lines[-1] and "SELF-SUFFICIENT" in lines[-1]
    assert "SELF-SUFFICIENT" not in lines[-2]


def test_a_dry_run_writes_nothing(tmp_path):
    out = chores.run(Gh([pr(7, "DIRTY")]), _store(tmp_path), NOW, slug="o/r", dry_run=True)
    assert out["would"] == ["record conflict:#7"] and not (tmp_path / "incidents.json").exists()


def test_github_unreadable_is_unavailable_never_raises(tmp_path):
    def broken(*a):
        return SimpleNamespace(returncode=1, stdout="", stderr="HTTP 502")
    assert chores.run(broken, _store(tmp_path), NOW, slug="o/r")["status"] == "unavailable"


# --- the claim gate --------------------------------------------------------------------------------------

def _two_kinds(tmp_path):
    store = _store(tmp_path)
    store.record(cw.Verdict(kind="incident", source="main", check="tests", fingerprint="c" * 64), "2026-11-19T01:00:00+00:00")
    chores.run(Gh([pr(7, "DIRTY")]), store, NOW, slug="o/r")
    return store


def test_without_the_pr_fix_flag_claim_never_hands_out_a_pr_fix(tmp_path):
    store = _two_kinds(tmp_path)
    assert store.claim(NOW)["context"]["check"] == "tests"
    assert store.claim(LATER) is None


def test_with_the_flag_pr_fixes_have_their_own_daily_budget(tmp_path):
    store = _store(tmp_path)
    chores.run(Gh([pr(n, "DIRTY") for n in range(1, 7)]), store, NOW, slug="o/r")
    got = [store.claim(NOW, allow_pr_fix=True) for _ in range(6)]
    data = store._load()
    data["auto_since_ack"] = 0
    assert sum(1 for g in got if g) == cw.PR_FIX_DAILY                 # own budget; the ack brake is not theirs


def test_pr_fix_dispatch_needs_the_reviewed_flag_and_no_kill_variable(tmp_path):
    p = tmp_path / "autonomy.json"
    p.write_text(json.dumps({"pr_fix_dispatch": True}))
    assert cw.pr_fix_dispatch_allowed(p, {}) is True
    assert cw.pr_fix_dispatch_allowed(p, {"JR_PR_FIX_DISPATCH": "0"}) is False
    p.write_text(json.dumps({"pr_fix_dispatch": False}))
    assert cw.pr_fix_dispatch_allowed(p, {}) is False
    assert cw.pr_fix_dispatch_allowed(tmp_path / "missing.json", {}) is False


def test_heal_prs_are_reviewed_by_the_agent_too():
    assert not any(p == "jr/heal-" for p in ar.SKIP_PREFIXES)


# --- the hourly tick runs the chores ---------------------------------------------------------------------

def test_the_tick_runs_the_chores_and_sends_their_nudges_and_digest(tmp_path):
    import tick
    from test_tick import git_ok, gh_ok, run
    seen, sent = [], []

    def chores_runner(gh, now, dry_run):
        seen.append(dry_run)
        return {"status": "ok", "recorded": ["abc"], "resolved": [], "nudges": ["🔧 nudge"], "digest": "🧹 Jr chores x"}
    r = run(git=git_ok(tmp_path), gh=gh_ok(rate="120"), chores_runner=chores_runner, notifier=sent.append)
    assert r.aborted and seen == [False] and r.chores["recorded"] == ["abc"]       # runs after an abort too
    assert "🔧 nudge" in sent and "🧹 Jr chores x" in sent


def test_a_broken_chores_runner_never_changes_the_tick(tmp_path):
    from test_tick import git_ok, gh_ok, run

    def boom(gh, now, dry_run):
        raise RuntimeError("x")
    r = run(git=git_ok(tmp_path), gh=gh_ok(rate="120"), chores_runner=boom)
    assert r.aborted == "GitHub rate limit low: 120 < 500" and r.chores["status"] == "unavailable"


def test_the_hourly_main_wires_the_default_chores_runner():
    import inspect
    import tick
    assert "chores_runner=default_chores_runner" in inspect.getsource(tick.main)


def test_the_switch_file_ships_pr_fix_dispatch_on_by_reviewed_pr():
    from pathlib import Path
    doc = json.loads((Path(__file__).resolve().parent / "autonomy.json").read_text())
    assert doc["pr_fix_dispatch"] is True


def test_a_merged_ci_heal_pr_resets_the_ack_brake_too(tmp_path):
    store = _store(tmp_path)
    store.record(cw.Verdict(kind="incident", source="main", check="tests", fingerprint="c" * 64), NOW)
    rec = store.claim(NOW)
    store.progress({rec["branch"]: 42}, NOW)
    data = store._load()
    data["auto_since_ack"] = 3
    data["halted"] = True
    store._save(data)
    store.progress({rec["branch"]: 42}, LATER, merged={41})
    assert store._load()["auto_since_ack"] == 3
    store.progress({rec["branch"]: 42}, LATER, merged={42})
    assert store._load()["auto_since_ack"] == 0 and store._load()["halted"] is False


def test_a_pr_open_a_day_without_any_label_still_waits_on_someone(tmp_path):
    T = "jr/tick-20261117-1200"
    prs = [pr(5, branch=T, created="2026-11-17T12:00:00Z"), pr(6, branch=T, created="2026-11-18T06:00:00Z", updated=NOW),
           pr(7, branch=T), pr(8, branch=T, draft=True, created="2026-11-01T00:00:00Z")]
    line = chores.run(Gh(prs, merged=merged("espatlas-jr")), _store(tmp_path), NOW, slug="o/r")["digest"]
    # Jr's own open PRs are its queue (shown with the oldest's age from createdAt: CI touching #6 changes nothing)
    assert "Jr's own queue: 3 open (oldest #5, 48 h)" in line and "self-sufficient 1/7 days" in line


# --- a red required check on ANY open PR is work, not silence (2026-11-19: tick PR #1828 sat red on `tests`;
#     ci_watch only declares a tick break when the two NEWEST tick PRs fail alike) ---------------------------

LOG = ("2026-11-18T14:29:28Z FAILED apps/core/tests/test_firmware.py::test_recipes_for_firmware_m5_crystal_is_no_longer_orphaned"
       " - AssertionError: assert {'m5cardputer__m5-crystal'} == {'m5stick-cplus2__m5-crystal'}\n"
       "2026-11-18T14:29:28Z E       AssertionError: assert {'m5cardputer__m5-crystal'} == {'m5stick-cplus2__m5-crystal'}\n")


def red(name="tests", run=111, job=222, conclusion="FAILURE"):
    return {"name": name, "conclusion": conclusion, "detailsUrl": f"https://github.com/o/r/actions/runs/{run}/job/{job}"}


class RedGh(Gh):
    def __init__(self, prs, required=("schema", "tests", "jr-tests"), behind=0, **kw):
        super().__init__(prs, **kw)
        self.required, self.behind = list(required), behind

    def __call__(self, *a):
        if a[:1] == ("api",) and "/compare/" in a[1]:
            self.calls.append(a)
            return SimpleNamespace(returncode=0, stdout=json.dumps({"ahead_by": self.behind}), stderr="")
        if a[:2] == ("api", "repos/o/r/branches/main"):
            self.calls.append(a)
            return SimpleNamespace(returncode=0, stdout=json.dumps(
                {"protection": {"required_status_checks": {"contexts": self.required}}}), stderr="")
        if a[:1] == ("api",) and "/actions/jobs/" in a[1]:
            self.calls.append(a)
            return SimpleNamespace(returncode=0, stdout=LOG, stderr="")
        if a[:2] == ("run", "rerun") or (a[:3] == ("api", "-X", "PUT") and a[3].endswith("/update-branch")):
            self.calls.append(a)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return super().__call__(*a)


def tick_pr(n, checks, head=H1, labels=("jr-review",)):
    p = pr(n, branch=f"jr/tick-20261118-07{n % 100:02d}", head=head, labels=labels)
    p["statusCheckRollup"] = checks
    return p


def test_a_red_required_check_is_rerun_once_first(tmp_path):
    store, gh = _store(tmp_path), RedGh([tick_pr(28, [red()])])
    out = chores.run(gh, store, NOW, slug="o/r")
    assert ("run", "rerun", "111", "--failed") in gh.calls and out["reruns"] == [28]
    assert _incidents(store) == {}
    chores.run(gh, store, LATER, slug="o/r")
    assert [c for c in gh.calls if c[:2] == ("run", "rerun")] == [("run", "rerun", "111", "--failed")]   # once per head


def test_a_content_pr_still_red_after_the_rerun_is_a_heal_incident_on_main_keyed_by_the_failing_test(tmp_path):
    store = _store(tmp_path)
    chores.run(RedGh([tick_pr(28, [red()])]), store, NOW, slug="o/r")
    chores.run(RedGh([tick_pr(28, [red()]), tick_pr(35, [red(run=333, job=444)], head=H2)]), store, LATER, slug="o/r")
    recs = [r for r in store._load()["incidents"].values() if r["context"]["check"].startswith("pr-red:")]
    assert len(recs) == 1, recs                                  # one broken test across PRs = one break
    c = recs[0]["context"]
    assert c["failed"].endswith("test_recipes_for_firmware_m5_crystal_is_no_longer_orphaned") and "AssertionError" in (c["assertion"] or "")
    assert c["evidence"]["prs"] == [28] and c["evidence"]["check"] == "tests"
    assert not cw.is_pr_fix(recs[0]) and recs[0]["branch"].startswith("jr/heal-")   # the CI launcher claims it


def test_a_code_pr_still_red_after_the_rerun_is_fixed_in_place(tmp_path):
    p = pr(40, branch="feat/z")
    p["statusCheckRollup"] = [red("jr-tests")]
    store = _store(tmp_path)
    chores.run(RedGh([p]), store, NOW, slug="o/r")
    chores.run(RedGh([p]), store, LATER, slug="o/r")
    rec = _incidents(store)["ci-fix:#40"]
    assert cw.is_pr_fix(rec) and rec["context"]["evidence"]["check"] == "jr-tests"


def test_a_non_required_or_infra_red_is_never_a_chore(tmp_path):
    store, gh = _store(tmp_path), RedGh([tick_pr(28, [red("sources-live"), red("tests", conclusion="CANCELLED")])])
    chores.run(gh, store, NOW, slug="o/r")
    chores.run(gh, store, LATER, slug="o/r")
    assert _incidents(store) == {} and not [c for c in gh.calls if c[:2] == ("run", "rerun")]


def test_a_red_pr_behind_main_gets_main_merged_in_once_before_it_becomes_a_job(tmp_path):
    store = _store(tmp_path)
    chores.run(RedGh([tick_pr(28, [red()])], behind=3), store, NOW, slug="o/r")            # rerun first
    gh = RedGh([tick_pr(28, [red()])], behind=3)
    chores.run(gh, store, LATER, slug="o/r")
    chores.run(gh, store, "2026-11-19T14:05:00+00:00", slug="o/r")
    assert [c for c in gh.calls if c[:3] == ("api", "-X", "PUT")] == [
        ("api", "-X", "PUT", "repos/o/r/pulls/28/update-branch", "-f", f"expected_head_sha={H1}")]   # once per head
    assert [r for r in _incidents(store) if r.startswith("pr-red:")]          # still red, updated: now a job


def test_a_red_content_pr_resolves_its_incident_when_it_turns_green(tmp_path):
    store = _store(tmp_path)
    chores.run(RedGh([tick_pr(28, [red()])]), store, NOW, slug="o/r")
    chores.run(RedGh([tick_pr(28, [red()])]), store, LATER, slug="o/r")
    rec = next(r for r in store._load()["incidents"].values() if r["context"]["check"].startswith("pr-red:"))
    green = RedGh([tick_pr(28, [{"name": "tests", "conclusion": "SUCCESS", "detailsUrl": ""}], head=H2)])
    chores.run(green, store, "2026-11-19T16:05:00+00:00", slug="o/r")
    assert store.get(rec["id"])["state"] == "open"                         # one green pass may be a blink
    chores.run(green, store, "2026-11-19T17:05:00+00:00", slug="o/r")
    assert store.get(rec["id"])["state"] == "resolved"


def test_an_unreadable_compare_never_merges_main_into_a_pr(tmp_path):
    class NoCompare(RedGh):
        def __call__(self, *a):
            if a[:1] == ("api",) and "/compare/" in a[1]:
                return SimpleNamespace(returncode=1, stdout="", stderr="HTTP 502")
            return super().__call__(*a)
    store = _store(tmp_path)
    gh = NoCompare([tick_pr(28, [red()])])
    chores.run(gh, store, NOW, slug="o/r")
    chores.run(gh, store, LATER, slug="o/r")
    assert not [c for c in gh.calls if c[:3] == ("api", "-X", "PUT")]


def test_drafts_and_forks_are_never_rerun(tmp_path):
    a, b = pr(50, draft=True), pr(51, fork=True)
    a["statusCheckRollup"] = b["statusCheckRollup"] = [red()]
    gh = RedGh([a, b])
    chores.run(gh, _store(tmp_path), NOW, slug="o/r")
    assert not [c for c in gh.calls if c[:2] == ("run", "rerun")]



# --- review BLOCK of #1857 (2026-11-19) ------------------------------------------------------------------

def test_rerun_and_merge_main_happen_once_per_failure_not_per_head_so_a_red_pr_becomes_a_job(tmp_path):
    # main moves every hour: each update-branch makes a new head; per-head memory looped forever (0 incidents)
    store = _store(tmp_path)
    heads = ["%040x" % i for i in range(1, 12)]
    for hour, head in enumerate(heads):
        chores.run(RedGh([tick_pr(28, [red()], head=head)], behind=1), store, f"2026-11-19T{hour:02d}:05:00+00:00", slug="o/r")
    data = store._load()
    assert [r for r in data["incidents"].values() if r["context"]["check"].startswith("pr-red:")]
    assert len(data.get("reruns") or {}) == 1 and len(data.get("updated_branch") or {}) == 1


def test_a_person_merging_a_pr_whose_chore_was_never_dispatched_does_not_lift_the_brake(tmp_path):
    store = _store(tmp_path)
    chores.run(Gh([pr(50, "DIRTY")]), store, NOW, slug="o/r")              # recorded, switch off: never dispatched
    data = store._load()
    data.update(auto_since_ack=3, halted=True)
    store._save(data)
    chores.run(Gh([], states={50: "MERGED"}), store, LATER, slug="o/r")
    assert store._load()["auto_since_ack"] == 3 and store._load()["halted"] is True



def test_a_failure_whose_assertion_text_changes_every_run_still_becomes_a_job(tmp_path):
    # 2nd review of #1857: a tmp path in the assertion made a new key every hour -> 24 reruns, 0 incidents
    store = _store(tmp_path)

    class Varying(RedGh):
        n = 0

        def __call__(self, *a):
            if a[:1] == ("api",) and "/actions/jobs/" in a[1]:
                Varying.n += 1
                self.calls.append(a)
                log = LOG.replace("{'m5cardputer__m5-crystal'}", "{'/tmp/pytest-%s/x'}" % ("abcdefgh"[Varying.n % 8] * 6))
                return SimpleNamespace(returncode=0, stdout=log, stderr="")
            return super().__call__(*a)
    for hour in range(6):
        gh = Varying([tick_pr(28, [red()], head="%040x" % (hour + 1))], behind=1)
        chores.run(gh, store, f"2026-11-19T{hour:02d}:05:00+00:00", slug="o/r")
    data = store._load()
    assert len(data["reruns"]) == 1 and len(data["updated_branch"]) == 1
    assert [r for r in data["incidents"].values() if r["context"]["check"].startswith("pr-red:")]



# --- 3rd review of #1857 (2026-11-19): blinks, and the pushed -> productive path ---------------------------

def test_a_dispatched_fix_is_never_resolved_by_a_blink_and_a_pushed_fix_resolves_after_two_clean_passes(tmp_path):
    store = _store(tmp_path)
    chores.run(Gh([pr(7, "DIRTY", head=H1)]), store, NOW, slug="o/r")
    store.claim(NOW, allow_pr_fix=True)
    for t in ("13", "14"):                                                    # blinks while the fix is in flight
        chores.run(Gh([pr(7, "UNKNOWN", head=H1)]), store, f"2026-11-19T{t}:05:00+00:00", slug="o/r")
    assert _incidents(store)["conflict:#7"]["state"] == "dispatched"
    chores.run(Gh([pr(7, "CLEAN", head=H2)]), store, "2026-11-19T15:05:00+00:00", slug="o/r")   # our push
    assert _incidents(store)["conflict:#7"]["state"] == "pushed"
    chores.run(Gh([pr(7, "CLEAN", head=H2)]), store, "2026-11-19T16:05:00+00:00", slug="o/r")
    assert _incidents(store)["conflict:#7"]["state"] == "resolved"


def test_a_one_pass_blink_never_records_a_second_incident(tmp_path):
    store = _store(tmp_path)
    for t, state in (("12", "DIRTY"), ("13", "UNKNOWN"), ("14", "DIRTY")):
        chores.run(Gh([pr(7, state)]), store, f"2026-11-19T{t}:05:00+00:00", slug="o/r")
    assert len(store._load()["incidents"]) == 1 and _incidents(store)["conflict:#7"]["state"] == "open"



# --- 4th review of #1857 (2026-11-19) -------------------------------------------------------------------

def test_a_pr_red_heal_in_flight_is_never_resolved_by_one_pending_pass(tmp_path):
    store = _store(tmp_path)
    chores.run(RedGh([tick_pr(28, [red()])]), store, NOW, slug="o/r")
    chores.run(RedGh([tick_pr(28, [red()])]), store, LATER, slug="o/r")
    rec = store.claim(LATER)
    assert rec and rec["context"]["check"].startswith("pr-red:")
    pending = {"name": "tests", "conclusion": None, "status": "IN_PROGRESS", "detailsUrl": ""}
    chores.run(RedGh([tick_pr(28, [pending])]), store, "2026-11-19T14:05:00+00:00", slug="o/r")
    chores.run(RedGh([tick_pr(28, [red()])]), store, "2026-11-19T15:05:00+00:00", slug="o/r")
    assert store.get(rec["id"])["state"] == "dispatched"
    assert len([r for r in store._load()["incidents"] if r.startswith(rec["id"])]) == 1   # no -2


def test_an_unjudged_push_lifts_no_brake(tmp_path):
    store = _store(tmp_path)
    gh = Gh([pr(11, labels=["needs-human"], head=H1)], comments={11: [block(H1)]})
    chores.run(gh, store, NOW, slug="o/r")
    store.claim(NOW, allow_pr_fix=True)
    data = store._load()
    data.update(auto_since_ack=3, halted=True)
    store._save(data)
    unjudged = Gh([pr(11, labels=["needs-human"], head=H2)], comments={11: [block(H1)]})
    for t in ("13", "14", "15"):
        chores.run(unjudged, store, f"2026-11-19T{t}:05:00+00:00", slug="o/r")
    assert store._load()["auto_since_ack"] == 3 and store._load()["halted"] is True


def test_a_pushed_fix_that_stays_broken_stalls_for_a_human(tmp_path):
    store = _store(tmp_path)
    chores.run(Gh([pr(7, "DIRTY", head=H1)]), store, NOW, slug="o/r")
    store.claim(NOW, allow_pr_fix=True)
    chores.run(Gh([pr(7, "DIRTY", head=H2)]), store, LATER, slug="o/r")
    assert _incidents(store)["conflict:#7"]["state"] == "pushed"
    chores.run(Gh([pr(7, "DIRTY", head=H2)]), store, "2026-11-19T19:05:00+00:00", slug="o/r")
    assert _incidents(store)["conflict:#7"]["state"] == "stalled"



def test_chores_never_merge_main_into_a_pr_whose_fix_is_in_flight(tmp_path):
    p = pr(40, branch="feat/z")
    p["statusCheckRollup"] = [red("jr-tests")]
    store = _store(tmp_path)
    chores.run(Gh([pr(40, "DIRTY", branch="feat/z")]), store, NOW, slug="o/r")
    store.claim(NOW, allow_pr_fix=True)                                      # conflict:#40 is with the delegate
    gh = RedGh([p], behind=2)
    chores.run(gh, store, LATER, slug="o/r")
    chores.run(gh, store, "2026-11-19T14:05:00+00:00", slug="o/r")
    assert not [c for c in gh.calls if c[:3] == ("api", "-X", "PUT")]



# --- 6th review of #1857 (2026-11-19): one fix at a time per PR, from its live head ------------------------

def test_two_fixes_are_never_out_on_the_same_pr_at_once(tmp_path):
    store = _store(tmp_path)
    gh = Gh([pr(7, "DIRTY", labels=["needs-human"], head=H1)], comments={7: [block(H1)]})
    chores.run(gh, store, NOW, slug="o/r")
    assert {"conflict:#7", "review-fix:#7"} <= set(_incidents(store))
    first = store.claim(NOW, allow_pr_fix=True)
    assert first and store.claim(NOW, allow_pr_fix=True) is None              # the other waits for this one


def test_an_open_fix_follows_the_prs_live_head_before_it_is_handed_out(tmp_path):
    store = _store(tmp_path)
    chores.run(Gh([pr(7, "DIRTY", head=H1)]), store, NOW, slug="o/r")
    chores.run(Gh([pr(7, "DIRTY", head=H2)]), store, LATER, slug="o/r")       # a person pushed; still conflicting
    rec = store.claim(LATER, allow_pr_fix=True)
    assert rec["context"]["evidence"]["pr_head"] == H2


# --- 2026-11-19: GitHub computes mergeability lazily -----------------------------------------------------------
# Measured: one listing right after main moved read 17 of 25 PRs as UNKNOWN; 12 s later 6 were CONFLICTING. The
# tick lists once an hour, so conflicts were (almost) never seen: #1835/#1836 stayed conflicting for 14 h although
# review_refresh's dry run said would_refresh. A listing with UNKNOWN in it is read again, a few times.

@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(chores, "SLEEP", slept.append)
    return slept


class Lazy(Gh):
    """The first `after` listings answer UNKNOWN for every PR, then the real state."""
    def __init__(self, prs, after=1, **kw):
        super().__init__(prs, **kw)
        self.after, self.lists = after, 0

    def __call__(self, *a):
        if a[:2] == ("pr", "list") and "merged" not in a:
            self.lists += 1
            if self.lists <= self.after:
                self.calls.append(a)
                return SimpleNamespace(returncode=0, stdout=json.dumps([{**p, "mergeStateStatus": "UNKNOWN"} for p in self.prs]), stderr="")
        return super().__call__(*a)


def test_a_listing_that_reads_unknown_is_read_again_until_github_has_computed_it(tmp_path, no_sleep):
    store, gh = _store(tmp_path), Lazy([pr(7, "DIRTY")], after=1)
    chores.run(gh, store, NOW, slug="o/r")
    assert "conflict:#7" in _incidents(store) and gh.lists == 2 and no_sleep == [chores.SETTLE_WAIT]


def test_the_wait_is_bounded_and_a_still_unknown_pr_is_simply_not_judged(tmp_path, no_sleep):
    store, gh = _store(tmp_path), Lazy([pr(7, "DIRTY")], after=99)
    out = chores.run(gh, store, NOW, slug="o/r")
    assert out["status"] == "ok" and _incidents(store) == {} and gh.lists == chores.SETTLE_TRIES


def test_a_settled_listing_costs_one_call(tmp_path, no_sleep):
    gh = Lazy([pr(7, "CLEAN")], after=0)
    chores.run(gh, _store(tmp_path), NOW, slug="o/r")
    assert gh.lists == 1 and no_sleep == []


# --- the labels the machine needs exist (2026-11-19: agent-pass, needs-human, review-fallback, jr-heal were all
#     missing; every `gh pr edit --add-label` would have raised) ------------------------------------------------

class LabelGh(Gh):
    def __init__(self, prs, labels=(), **kw):
        super().__init__(prs, **kw)
        self.labels = list(labels)

    def __call__(self, *a):
        if a[:2] == ("label", "list"):
            self.calls.append(a)
            return SimpleNamespace(returncode=0, stdout=json.dumps([{"name": n} for n in self.labels]), stderr="")
        if a[:2] == ("label", "create"):
            self.calls.append(a)
            self.labels.append(a[2])
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return super().__call__(*a)


def test_missing_labels_are_created_once_a_day(tmp_path):
    store, gh = _store(tmp_path), LabelGh([pr(1)], labels=["jr-review", "needs-human"])
    out = chores.run(gh, store, NOW, slug="o/r")
    assert sorted(out["labels_created"]) == ["agent-pass", "jr-heal", "review-fallback"]
    chores.run(gh, store, LATER, slug="o/r")
    assert len([c for c in gh.calls if c[:2] == ("label", "list")]) == 1            # once per UTC day
    assert len([c for c in gh.calls if c[:2] == ("label", "create")]) == 3


# --- canary retry (2026-11-19): a Jr content PR the canary did not merge gets another look, once a day -----------
# #1846 (a demand PR) was judged once and never again: chores skip jr/research-*, the tick only refreshes its own
# CONFLICTING tick PRs, and a canary runs only on a pull-request event. "Capped today", a quote page that did
# not answer, a guard fixed on main since: each left the PR waiting for a person.

def check(name, conclusion="SUCCESS", run=900, job=901, status="COMPLETED"):
    return {"name": name, "status": status, "conclusion": conclusion,
            "detailsUrl": f"https://github.com/o/r/actions/runs/{run}/job/{job}"}


def content(n, branch, checks, **kw):
    return {**pr(n, branch=branch, **kw), "statusCheckRollup": checks}


class RetryGh(RedGh):
    def __call__(self, *a):
        if a[:3] == ("api", "-X", "POST") and a[3].endswith("/rerun"):
            self.calls.append(a)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return super().__call__(*a)

    def acts(self):
        return [c for c in self.calls if c[:2] == ("run", "rerun") or c[:3] in {("api", "-X", "PUT"), ("api", "-X", "POST")}]


def _flags(tmp_path, **flags):
    f = tmp_path / "autonomy.json"
    f.write_text(json.dumps({"demand_automerge": True, "tick_automerge": True, **flags}))
    return f


def retry(gh, store, tmp_path, now=NOW, dry_run=False, **flags):
    return chores.canary_retry(gh, "o/r", gh.prs, store, now, dry_run, autonomy_path=_flags(tmp_path, **flags))


GREEN_DEMAND = [check("schema"), check("tests"), check("jr-tests"), check("demand-canary", job=950)]


def test_a_demand_pr_behind_main_is_refreshed_with_main_once_a_day(tmp_path):
    gh = RetryGh([content(1846, "jr/research-pam-c2", GREEN_DEMAND, draft=True)], behind=3)
    store = _store(tmp_path)
    assert retry(gh, store, tmp_path)["update_branch"] == [(1846, H1)]
    assert gh.acts() == [("api", "-X", "PUT", "repos/o/r/pulls/1846/update-branch", "-f", f"expected_head_sha={H1}")]
    again = RetryGh(gh.prs, behind=3)
    assert retry(again, store, tmp_path, now=LATER) == {"update_branch": [], "rerun": [], "failed": []} and again.acts() == []
    tomorrow = RetryGh(gh.prs, behind=3)
    assert retry(tomorrow, store, tmp_path, now="2026-11-20T00:05:00+00:00")["update_branch"] == [(1846, H1)]


def test_a_demand_pr_level_with_main_gets_its_canary_job_run_again(tmp_path):
    gh = RetryGh([content(1846, "jr/research-pam-c2", GREEN_DEMAND, draft=True)], behind=0)
    assert retry(gh, _store(tmp_path), tmp_path)["rerun"] == [(1846, "900")]
    assert gh.acts() == [("api", "-X", "POST", "repos/o/r/actions/jobs/950/rerun")]


def test_a_failed_guard_reruns_the_failed_jobs_so_the_canary_behind_them_runs_too(tmp_path):
    checks = [check("schema"), check("tests"), check("jr-tests"), check("demand-guard", "FAILURE", job=940),
              check("demand-canary", "SKIPPED", job=950)]
    gh = RetryGh([content(1846, "jr/research-pam-c2", checks, draft=True)], behind=0)
    retry(gh, _store(tmp_path), tmp_path)
    assert gh.acts() == [("run", "rerun", "900", "--failed")]


def test_a_review_routed_tick_pr_is_only_ever_rerun_never_merged_with_main(tmp_path):
    checks = [check("schema"), check("tests"), check("jr-tests"), check("tick-canary", job=960)]
    gh = RetryGh([content(1860, "jr/tick-20261119-0200", checks, labels=("jr-review",))], behind=5)
    retry(gh, _store(tmp_path), tmp_path)
    assert gh.acts() == [("api", "-X", "POST", "repos/o/r/actions/jobs/960/rerun")]     # the tick's refresher owns merges


def test_what_is_left_alone(tmp_path):
    running = [check("schema"), check("tests", status="IN_PROGRESS", conclusion=""), check("demand-canary", job=950)]
    prs = [content(1, "jr/research-a", GREEN_DEMAND, labels=("needs-human",)),          # a person was asked
           content(2, "jr/research-b", running),                                          # CI still running
           content(3, "jr/research-c", []),                                               # nothing ever ran
           content(4, "jr/research-d", GREEN_DEMAND, fork=True),
           content(5, "jr/research-e", GREEN_DEMAND, base="feat/x"),
           content(6, "jr/tick-20261119-0500", GREEN_DEMAND),                             # AUTO route: merges itself
           content(7, "feat/x", GREEN_DEMAND)]                                            # a code PR: the sweep's
    gh = RetryGh(prs, behind=3)
    assert retry(gh, _store(tmp_path), tmp_path) == {"update_branch": [], "rerun": [], "failed": []}
    assert gh.acts() == []


def test_a_lane_whose_switch_is_off_is_never_retried(tmp_path):
    checks = [check("schema"), check("tests"), check("jr-tests"), check("tick-canary", job=960)]
    prs = [content(1860, "jr/tick-20261119-0200", checks, labels=("jr-review",)),
           content(1846, "jr/research-pam-c2", GREEN_DEMAND, draft=True)]
    gh = RetryGh(prs, behind=0)
    out = retry(gh, _store(tmp_path), tmp_path, tick_automerge=False)
    assert out["rerun"] == [(1846, "900")]
    off = RetryGh(prs, behind=0)
    assert retry(off, _store(tmp_path / "x"), tmp_path, tick_automerge=False, demand_automerge=False)["rerun"] == []
    (tmp_path / "autonomy.json").write_text("not json")
    assert chores.canary_retry(off, "o/r", prs, _store(tmp_path / "y"), NOW, False, autonomy_path=tmp_path / "autonomy.json")["rerun"] == []


def test_at_most_two_retries_a_tick_oldest_first_and_the_rest_come_next_hour(tmp_path):
    prs = [content(n, f"jr/research-{n}", GREEN_DEMAND, draft=True) for n in (30, 10, 20)]
    store = _store(tmp_path)
    gh = RetryGh(prs, behind=1)
    assert [n for n, _ in retry(gh, store, tmp_path)["update_branch"]] == [10, 20]
    nxt = RetryGh(prs, behind=1)
    assert [n for n, _ in retry(nxt, store, tmp_path, now=LATER)["update_branch"]] == [30]


def test_a_pr_whose_fix_the_delegate_is_working_on_is_never_moved_under_it(tmp_path):
    store = _store(tmp_path)
    store.record(cw.pr_fix_verdict("conflict", 1846, "jr/research-pam-c2", H1), NOW)
    assert store.claim(NOW, allow_pr_fix=True)
    gh = RetryGh([content(1846, "jr/research-pam-c2", GREEN_DEMAND, draft=True)], behind=3)
    assert retry(gh, store, tmp_path, now=LATER)["update_branch"] == [] and gh.acts() == []


def test_a_dry_run_names_the_retry_and_does_and_remembers_nothing(tmp_path):
    gh = RetryGh([content(1846, "jr/research-pam-c2", GREEN_DEMAND, draft=True)], behind=3)
    store = _store(tmp_path)
    assert retry(gh, store, tmp_path, dry_run=True)["update_branch"] == [(1846, H1)] and gh.acts() == []
    assert "canary_retry" not in store._load()


def test_a_refused_retry_is_reported_remembered_and_never_stops_the_others(tmp_path):
    class Refusing(RetryGh):
        def __call__(self, *a):
            if a[:3] == ("api", "-X", "PUT") and "/pulls/10/" in a[3]:
                self.calls.append(a)
                return SimpleNamespace(returncode=1, stdout="", stderr="HTTP 422: merge conflict")
            return super().__call__(*a)
    prs = [content(n, f"jr/research-{n}", GREEN_DEMAND, draft=True) for n in (10, 20)]
    store = _store(tmp_path)
    out = retry(Refusing(prs, behind=1), store, tmp_path)
    assert out["failed"] == [10] and out["update_branch"] == [(20, H1)]
    assert retry(Refusing(prs, behind=1), store, tmp_path, now=LATER) == {"update_branch": [], "rerun": [], "failed": []}


def test_the_chores_run_the_retry_and_report_it(tmp_path):
    gh = RetryGh([content(1846, "jr/research-pam-c2", GREEN_DEMAND, draft=True)], behind=3)
    out = chores.run(gh, _store(tmp_path), NOW, slug="o/r", autonomy_path=_flags(tmp_path))
    assert out["status"] == "ok" and out["canary_retries"] == [1846]
    dry = chores.run(RetryGh(gh.prs, behind=3), _store(tmp_path / "d"), NOW, slug="o/r", dry_run=True, autonomy_path=_flags(tmp_path))
    assert "canary retry #1846 (merge main)" in dry["would"]


def test_a_red_required_check_belongs_to_red_prs_not_to_the_retry(tmp_path):
    checks = [check("schema"), check("tests", "FAILURE", job=930), check("jr-tests"), check("demand-canary", "SKIPPED", job=950)]
    gh = RetryGh([content(1846, "jr/research-pam-c2", checks)], behind=3)                # not a draft: red_prs has it
    assert retry(gh, _store(tmp_path), tmp_path) == {"update_branch": [], "rerun": [], "failed": []} and gh.acts() == []


# --- review BLOCK of #1874: the tick's GitHub budget can end the run between two calls ---------------------------

class Budget(Exception):
    pass


def test_a_retry_cut_short_by_the_call_budget_is_still_remembered_for_the_day(tmp_path):
    class Limited(RetryGh):
        def __call__(self, *a):
            if a[:3] == ("api", "-X", "PUT"):
                self.calls.append(a)
                raise Budget("call budget spent")            # the PUT left; nothing after it ran
            return super().__call__(*a)
    prs = [content(n, f"jr/research-{n}", GREEN_DEMAND, draft=True) for n in (10, 20)]
    store = _store(tmp_path)
    gh = Limited(prs, behind=1)
    with pytest.raises(Budget):
        retry(gh, store, tmp_path)
    assert store._load()["canary_retry"] == {"10": "2026-11-19"}
    nxt = RetryGh(prs, behind=1)
    assert [n for n, _ in retry(nxt, store, tmp_path, now=LATER)["update_branch"]] == [20]     # 10 is not sent again


def test_the_retry_runs_after_the_reruns_red_prs_already_remembered(tmp_path):
    prs = [tick_pr(28, [red()]), content(1846, "jr/research-pam-c2", GREEN_DEMAND, draft=True)]
    gh = RetryGh(prs, behind=3)
    chores.run(gh, _store(tmp_path), NOW, slug="o/r", autonomy_path=_flags(tmp_path))
    acts = gh.acts()
    assert acts.index(("run", "rerun", "111", "--failed")) < acts.index(
        ("api", "-X", "PUT", "repos/o/r/pulls/1846/update-branch", "-f", f"expected_head_sha={H1}"))


def test_the_retry_never_overwrites_what_the_other_chores_wrote_to_the_store(tmp_path):
    prs = [tick_pr(28, [red()]), content(1846, "jr/research-pam-c2", GREEN_DEMAND, draft=True)]
    store = _store(tmp_path)
    chores.run(RetryGh(prs, behind=3), store, NOW, slug="o/r", autonomy_path=_flags(tmp_path))
    data = store._load()
    assert data["canary_retry"] == {"1846": "2026-11-19"} and len(data["reruns"]) == 1


def test_a_failure_in_another_workflows_run_is_not_what_gets_rerun(tmp_path):
    checks = [check("agent-review", "FAILURE", run=700, job=701), check("schema"), check("tests"), check("jr-tests"),
              check("demand-canary", job=950)]
    gh = RetryGh([content(1846, "jr/research-pam-c2", checks, draft=True)], behind=0)
    retry(gh, _store(tmp_path), tmp_path)
    assert gh.acts() == [("api", "-X", "POST", "repos/o/r/actions/jobs/950/rerun")]


def test_a_draft_demand_pr_with_a_red_required_check_is_the_retrys_since_red_prs_skips_drafts(tmp_path):
    checks = [check("schema"), check("tests", "FAILURE", job=930), check("jr-tests"), check("demand-canary", "SKIPPED", job=950)]
    gh = RetryGh([content(1846, "jr/research-pam-c2", checks, draft=True)], behind=3)
    assert retry(gh, _store(tmp_path), tmp_path)["update_branch"] == [(1846, H1)]
    level = RetryGh([content(1846, "jr/research-pam-c2", checks, draft=True)], behind=0)
    retry(level, _store(tmp_path / "l"), tmp_path)
    assert level.acts() == [("run", "rerun", "900", "--failed")]


def test_a_pr_without_its_lanes_canary_check_is_left_alone(tmp_path):
    gh = RetryGh([content(1846, "jr/research-pam-c2", [check("schema"), check("tests"), check("jr-tests")], draft=True)], behind=3)
    assert retry(gh, _store(tmp_path), tmp_path) == {"update_branch": [], "rerun": [], "failed": []}


# --- 2nd review of #1874 (notes): the memory trim and a failure that is not in the canary's way ------------------

def test_the_days_memory_keeps_every_pr_of_today_whatever_its_number_and_drops_older_days(tmp_path):
    store = _store(tmp_path)
    data = store._load()
    data["canary_retry"] = {**{str(n): "2026-11-19" for n in range(2000, 2400)}, "1846": "2026-11-19", "7": "2026-11-18"}
    store._save(data)
    gh = RetryGh([content(1846, "jr/research-pam-c2", GREEN_DEMAND, draft=True),
                  content(1900, "jr/research-other", GREEN_DEMAND, draft=True)], behind=3)
    assert [n for n, _ in retry(gh, store, tmp_path)["update_branch"]] == [1900]          # 1846 already had today's
    kept = store._load()["canary_retry"]
    assert kept["1846"] == "2026-11-19" and kept["1900"] == "2026-11-19" and "7" not in kept and len(kept) == 402


def test_a_failure_beside_a_canary_that_ran_reruns_the_canary_not_the_failed_job(tmp_path):
    checks = [check("schema"), check("tests"), check("jr-tests"), check("sources-live", "FAILURE", job=970),
              check("demand-canary", "SUCCESS", job=950)]
    gh = RetryGh([content(1846, "jr/research-pam-c2", checks, draft=True)], behind=0)
    retry(gh, _store(tmp_path), tmp_path)
    assert gh.acts() == [("api", "-X", "POST", "repos/o/r/actions/jobs/950/rerun")]


def test_the_fix_prompt_tells_the_agent_how_to_correct_a_pr_description_and_to_leave_a_conflict_job_small():
    # 2026-11-19: 8 PRs were blocked on a future check tagged [REAL] in their description, and #1840 was blocked
    # again after its code fix because the description still told the old mechanism. The fix agent could push
    # commits but had no way to change a description, so those blocks could never clear.
    prompt = (Path(chores.__file__).resolve().parent.parent / "docs" / "ops" / "HEAL-PROMPT.md").read_text()
    section = prompt[prompt.index("## When `INCIDENT.context.check` starts with `conflict:`"):]
    assert "`PR_DESCRIPTION`" in section and "the relay replaces" in section
    assert "`[REAL]` only on something already observed" in section
    assert "git commit --allow-empty" in section                       # a verdict is tied to the head
    assert "do not refactor or split files" in section                 # the 516-line split the relay refused
    assert "Never create a virtualenv" in prompt and "`PYTHON`" in prompt   # /tmp filled up and reviews stopped


# --- Jr never parks a PR on a person (2026-11-19) ----------------------------------------------------------------

def _third_block(tmp_path, branch):
    store = _store(tmp_path)
    for day in ("2026-11-15", "2026-11-16"):                                 # two fix rounds that did not end it
        rec = store.record(cw.pr_fix_verdict("review-fix", 11, branch, H1), f"{day}T09:00:00+00:00")
        data = store._load()
        data["incidents"][rec["id"]]["state"] = "resolved"
        store._save(data)
    gh = Gh([pr(11, branch=branch, labels=["needs-human"], head=H1)], comments={11: [block(H1)]})
    out = chores.run(gh, store, NOW, slug="o/r")
    return store, gh, out


def test_the_third_block_on_a_persons_pr_is_given_up_with_one_comment_and_the_pr_stays_open(tmp_path):
    store, gh, out = _third_block(tmp_path, "feat/x")
    rec = _incidents(store)["review-fix:#11"]
    assert rec["state"] == "abandoned"
    said = [c for c in gh.calls if c[:2] == ("pr", "comment")]
    assert len(said) == 1 and said[0][2] == "11" and "Nobody is waited on" in said[0][-1]
    assert not [c for c in gh.calls if c[:2] == ("pr", "close")]
    again = Gh(gh.prs, comments=gh.comments)
    chores.run(again, store, LATER, slug="o/r")                              # next tick: said once, never again
    assert not [c for c in again.calls if c[:2] in {("pr", "comment"), ("pr", "close")}]
    assert store.claim(LATER, allow_pr_fix=True) is None                     # and never handed to the delegate


def test_the_third_block_on_jrs_own_heal_pr_closes_it(tmp_path):
    store, gh, out = _third_block(tmp_path, "jr/heal-0cf1acb95f79")
    closed = [c for c in gh.calls if c[:2] == ("pr", "close")]
    assert len(closed) == 1 and closed[0][2] == "11" and "Jr stops here" in closed[0][-1]


def test_a_pause_is_named_in_the_daily_line_only_on_its_own_day(tmp_path):
    store = _store(tmp_path)
    data = store._load()
    data.update(halted=True, halted_day="2026-11-19")
    store._save(data)
    assert "self-heal paused until 00:00 UTC" in _day(store, Gh([], merged=[]), 19)


# --- the scoreboard measures Jr, not people (2026-11-19) ------------------------------------------------------
# The first daily line read "by a person 18 · waiting 6 → 0/7": the 18 were a person's own infrastructure PRs and
# the 6 were a person's PRs blocked by review. Under that rule one ordinary merge by anyone, or one human PR left
# open a day, reset the count for good: it could never reach 7 while anybody worked on the repository.

def test_people_merging_and_holding_their_own_prs_never_break_a_self_sufficient_day(tmp_path):
    store = _store(tmp_path)
    prs = [pr(1840, branch="feat/analytics", labels=["needs-human"], created="2026-11-17T00:00:00Z"),   # a person's, blocked
           pr(1852, branch="perf/inline-css", created="2026-11-16T00:00:00Z")]                           # a person's, idle
    gh = Gh(prs, merged=merged("fcavalcantirj", "fcavalcantirj") + merged_jr("espatlas-jr", "github-actions[bot]"))
    line = _day(store, gh, 19)
    assert "self-sufficient 1/7 days" in line and "nothing of Jr's waits on a person" in line
    assert "merged by Jr 2" in line and "Jr's PRs merged by a person 0" in line
    assert "people's own: 2 merged, 2 open (1 blocked by review)" in line
    row = store._load()["scoreboard"][-1]
    assert row["ok"] is True and row["by_person"] == 0 and row["own_merged"] == 2 and row["own_open"] == 2


@pytest.mark.parametrize("branch", ["jr/tick-20261119-0100", "jr/research-pam-abc", "jr/heal-0cf1acb95f79"])
def test_a_person_merging_any_of_jrs_own_prs_breaks_the_day(tmp_path, branch):
    line = _day(_store(tmp_path), Gh([], merged=merged_jr("fcavalcantirj", branch=branch)), 19)
    assert "Jr's PRs merged by a person 1" in line and "self-sufficient 0/7 days" in line


def test_the_machine_merging_a_persons_pr_is_jrs_work(tmp_path):
    line = _day(_store(tmp_path), Gh([], merged=merged("github-actions[bot]", "espatlas-jr")), 19)
    assert "merged by Jr 2" in line and "self-sufficient 1/7 days" in line


def test_jrs_own_pr_labelled_needs_human_still_breaks_the_day(tmp_path):
    labelled = [pr(1897, branch="jr/heal-0cf1acb95f79", labels=["needs-human"])]
    assert "self-sufficient 0/7 days" in _day(_store(tmp_path / "b"), Gh(labelled, merged=[]), 19)



# --- Jr's own tick PRs never wait for a person (2026-11-19) -------------------------------------------------------
# A review-routed tick PR the evidence check cannot vouch for sat open until a person reviewed it: on Nov 19 four
# of them were 25 to 38 hours old. Jr now closes such a PR itself after EXPIRE_HOURS, with the reasons, and keeps
# the ones that ARE eligible: those only wait for the tick canary's daily slot, which is Jr's own throttle.

OLD, YOUNG = "2026-11-16T10:00:00Z", "2026-11-18T10:00:00Z"            # 74 h and 26 h before NOW


def review_tick(n, created=OLD, labels=("jr-review",), **kw):
    return pr(n, branch=f"jr/tick-202611{n % 28 + 1:02d}-0700", labels=labels, created=created, **kw)


class ExpGh(Gh):
    def __call__(self, *a):
        if a[:2] == ("pr", "close"):
            self.calls.append(a)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return super().__call__(*a)

    def closed(self):
        return [int(c[2]) for c in self.calls if c[:2] == ("pr", "close")]


def expire(gh, verdicts, now=NOW, dry_run=False):
    """`verdicts`: {branch suffix or pr number: problems list | Exception}."""
    fetched = []
    def guard(repo, *, base, head, branch):
        got = verdicts.get(branch, [])
        if isinstance(got, Exception):
            raise got
        return got, ["E1 …"]
    out = chores.expire_tick_prs(gh, gh.prs, now, dry_run, guard=guard, fetch=lambda b: fetched.append(b))
    return out, fetched


def test_a_review_tick_pr_the_guard_cannot_vouch_for_is_closed_after_three_days_with_the_reasons(tmp_path):
    p = review_tick(1828)
    gh = ExpGh([p])
    out, fetched = expire(gh, {p["headRefName"]: ["E1 data/recipes/lilygo-t-deck__esp32-template/recipe.md: no evidence receipt"]})
    assert out["closed"] == [1828] and gh.closed() == [1828] and fetched == [p["headRefName"]]
    text = next(c for c in gh.calls if c[:2] == ("pr", "close"))[-1]
    assert "no evidence receipt" in text and "72 h" in text and "30 days" in text


def test_an_eligible_one_is_kept_whatever_its_age_and_a_young_one_is_not_even_looked_at(tmp_path):
    old_ok, young = review_tick(1827), review_tick(1875, created=YOUNG)
    gh = ExpGh([old_ok, young])
    out, fetched = expire(gh, {young["headRefName"]: ["E1 no receipt"]})
    assert out == {"closed": [], "kept": [1827], "unreadable": []} and gh.closed() == []
    assert fetched == [old_ok["headRefName"]]


def test_an_unreadable_upstream_or_fetch_never_closes_anything(tmp_path):
    p = review_tick(1839)
    gh = ExpGh([p])
    out, _ = expire(gh, {p["headRefName"]: RuntimeError("GitHub API: HTTP 502")})
    assert out == {"closed": [], "kept": [], "unreadable": [1839]} and gh.closed() == []


def test_only_review_routed_tick_prs_of_this_repo_on_main_are_ever_closed(tmp_path):
    bad = ["E1 no receipt"]
    prs = [review_tick(1, labels=()),                                     # AUTO route: merges itself
           review_tick(2, draft=True), review_tick(3, fork=True), review_tick(4, base="feat/x"),
           pr(5, branch="jr/research-pam-x", labels=["jr-review"], created=OLD),    # demand: its own lane
           pr(6, branch="jr/heal-abc", labels=["jr-review"], created=OLD),          # heal: the agent review
           pr(7, branch="feat/x", labels=["jr-review"], created=OLD)]               # a person's
    gh = ExpGh(prs)
    out, fetched = expire(gh, {p["headRefName"]: bad for p in prs})
    assert out["closed"] == [] and fetched == [] and gh.closed() == []


def test_at_most_two_a_tick_oldest_first_and_a_dry_run_closes_nothing(tmp_path):
    prs = [review_tick(30, created="2026-11-15T10:00:00Z"), review_tick(10, created="2026-11-13T10:00:00Z"),
           review_tick(20, created="2026-11-14T10:00:00Z")]
    bad = {p["headRefName"]: ["E1 no receipt"] for p in prs}
    gh = ExpGh(prs)
    assert expire(gh, bad)[0]["closed"] == [10, 20]
    dry = ExpGh(prs)
    assert expire(dry, bad, dry_run=True)[0]["closed"] == [10, 20] and dry.closed() == []


def test_the_chores_run_the_expiry_and_report_it(tmp_path, monkeypatch):
    p = review_tick(1828)
    monkeypatch.setattr(chores, "_guard", lambda repo, *, base, head, branch: (["E1 no receipt"], []))
    monkeypatch.setattr(chores, "_fetch_branch", lambda branch: None)
    gh = ExpGh([p])
    out = chores.run(gh, _store(tmp_path), NOW, slug="o/r")
    assert out["status"] == "ok" and out["expired"] == [1828] and gh.closed() == [1828]
    dry = chores.run(ExpGh([p]), _store(tmp_path / "d"), NOW, slug="o/r", dry_run=True)
    assert "close tick PR #1828 (72 h, not eligible)" in dry["would"]


def test_jrs_queued_tick_prs_are_shown_but_are_not_waiting_on_a_person(tmp_path):
    # an eligible tick PR waits for the canary's daily slot, a not-eligible one for its own expiry: Jr's queue
    prs = [review_tick(1827), review_tick(1875, created=YOUNG)]
    line = _day(_store(tmp_path), Gh(prs, merged=merged_jr("espatlas-jr")), 19)
    assert "self-sufficient 1/7 days" in line and "nothing of Jr's waits on a person" in line
    assert "Jr's own queue: 2 open (oldest #1827, 74 h)" in line


# --- the tick says so when the backup reviewer answers nothing (2026-11-19) ---------------------------------------

def test_a_backup_reviewer_that_gave_no_verdict_today_is_a_warning_in_the_chores_output(tmp_path):
    state = tmp_path / "agent-review.json"
    state.write_text(json.dumps({"fallback_empty": {"day": "2026-11-19", "prs": [1840, 1843]}}))
    line = chores.review_lane_warning(NOW, state)
    assert "#1840, #1843" in line and "NO verdict today" in line and "credit" in line
    assert chores.review_lane_warning("2026-11-20T12:05:00+00:00", state) is None       # yesterday's is not today's
    assert chores.review_lane_warning(NOW, tmp_path / "missing.json") is None
    state.write_text("not json")
    assert chores.review_lane_warning(NOW, state) is None


def test_the_chores_carry_that_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(chores, "review_lane_warning", lambda now, state_path=None: "the backup reviewer … NO verdict today")
    out = chores.run(Gh([]), _store(tmp_path), NOW, slug="o/r")
    assert out["warnings"] == ["the backup reviewer … NO verdict today"]
    monkeypatch.setattr(chores, "review_lane_warning", lambda now, state_path=None: None)
    assert chores.run(Gh([]), _store(tmp_path / "b"), NOW, slug="o/r")["warnings"] == []


def test_the_tick_line_carries_the_chores_warnings(tmp_path):
    from test_tick import git_ok, gh_ok, run

    def chores_runner(gh, now, dry_run):
        return {"status": "ok", "recorded": [], "warnings": ["the backup reviewer was asked and gave NO verdict today (#1840)"]}
    r = run(git=git_ok(tmp_path), gh=gh_ok(rate="120"), chores_runner=chores_runner, notifier=lambda m: None)
    assert any("backup reviewer was asked and gave NO verdict" in w for w in r.warnings)


# --- a self-sufficient day is a day the catalog grew (2026-11-21) -----------------------------------------------
# Nov 20 counted 36 merges by Jr, none by a person, nothing waiting: by the old rule a good day. Every one of those
# merges was bookkeeping (the ledger, telemetry); the catalog stayed at 170 firmware / 348 recipes and every lane
# yielded 0 for 24 ticks. Seven such days would have read SELF-SUFFICIENT with nothing added.

def _clean():
    return Gh([], merged=merged("espatlas-jr", "github-actions[bot]"))


def test_a_day_the_catalog_did_not_grow_is_not_self_sufficient(tmp_path, monkeypatch):
    monkeypatch.setattr(chores, "TREND", write_trend(tmp_path / "t.jsonl", [trend_row("2026-11-18"), trend_row("2026-11-19")]))
    store = _store(tmp_path)
    line = _day(store, _clean(), 19)
    assert "catalog did not grow (2026-11-18→2026-11-19)" in line and "self-sufficient 0/7 days" in line
    row = store._load()["scoreboard"][-1]
    assert row["ok"] is False and row["grew"] == 0 and row["by_person"] == 0 and row["waiting"] == 0


def test_any_new_firmware_recipe_board_or_filled_board_field_is_growth(tmp_path, monkeypatch):
    for i, change in enumerate((dict(firmware=171), dict(recipes=349), dict(zero_fw=60),
                                dict(with_fw=63, zero_fw=58, recipes=349), dict(usb=67))):
        monkeypatch.setattr(chores, "TREND", write_trend(tmp_path / f"t{i}.jsonl",
                                                         [trend_row("2026-11-18"), trend_row("2026-11-19", **change)]))
        (tmp_path / f"s{i}").mkdir()
        store = _store(tmp_path / f"s{i}")
        line = _day(store, _clean(), 19)
        assert "self-sufficient 1/7 days" in line and "catalog +" in line, change


def test_growth_is_measured_up_to_todays_trend_row_and_a_missing_or_broken_trend_proves_nothing(tmp_path, monkeypatch):
    cases = {
        "no trend row for 2026-11-19": [trend_row("2026-11-17"), trend_row("2026-11-18", firmware=171)],
        "fewer than two trend rows": [trend_row("2026-11-19")],
        "catalog growth unreadable": None,
    }
    for i, (says, rows) in enumerate(cases.items()):
        path = tmp_path / f"t{i}.jsonl"
        if rows is None:
            path.write_text("{not json\n", encoding="utf-8")
        else:
            write_trend(path, rows)
        monkeypatch.setattr(chores, "TREND", path)
        line = _day(_store(tmp_path / f"s{i}"), _clean(), 19)
        assert says in line and "self-sufficient 0/7 days" in line, says
    monkeypatch.setattr(chores, "TREND", tmp_path / "absent.jsonl")
    assert "self-sufficient 0/7 days" in _day(_store(tmp_path / "s9"), _clean(), 19)


def test_a_catalog_that_shrank_is_not_growth(tmp_path, monkeypatch):
    monkeypatch.setattr(chores, "TREND", write_trend(tmp_path / "t.jsonl", [trend_row("2026-11-18"), trend_row("2026-11-19", recipes=347)]))
    line = _day(_store(tmp_path), _clean(), 19)
    assert "catalog -1 (2026-11-18→2026-11-19)" in line and "self-sufficient 0/7 days" in line


def test_the_growth_rule_reads_the_newest_row_per_day_in_date_order(tmp_path, monkeypatch):
    rows = [trend_row("2026-11-19", firmware=172), trend_row("2026-11-18"), trend_row("2026-11-19", firmware=171)]
    monkeypatch.setattr(chores, "TREND", write_trend(tmp_path / "t.jsonl", rows))     # an appended re-run of the 19th
    assert "catalog +1 (2026-11-18→2026-11-19)" in _day(_store(tmp_path), _clean(), 19)


# --- a fix that lands on main through ANY PR reaches the red PR (2026-11-25) ------------------------------------
# Measured: #2053 went red on a test main fixed at 18:35Z through #2084 (not a Jr heal). red_prs had already used
# its one merge of main for that failure, and a second one only followed a MERGED Jr heal, so #2053 stayed red and
# its incident was abandoned with the fix already on main.

class MainGreenGh(RedGh):
    def __init__(self, prs, main_conclusion="success", **kw):
        super().__init__(prs, **kw)
        self.main_conclusion = main_conclusion

    def __call__(self, *a):
        if a[:1] == ("api",) and "/commits/main/check-runs" in a[1]:
            self.calls.append(a)
            runs = [] if self.main_conclusion is None else [
                {"name": "tests", "status": "completed", "conclusion": self.main_conclusion, "started_at": "2026-11-19T13:00:00Z"}]
            return SimpleNamespace(returncode=0, stdout=json.dumps({"check_runs": runs}), stderr="")
        return super().__call__(*a)


def _puts(gh):
    return [c for c in gh.calls if c[:3] == ("api", "-X", "PUT")]


def test_a_red_pr_gets_main_again_once_a_day_when_main_is_green_on_that_check(tmp_path):
    store = _store(tmp_path)
    chores.run(RedGh([tick_pr(28, [red()])], behind=3), store, NOW, slug="o/r")                 # rerun first
    chores.run(RedGh([tick_pr(28, [red()])], behind=3), store, LATER, slug="o/r")               # first merge of main
    gh = MainGreenGh([tick_pr(28, [red()], head=H2)], behind=2)
    chores.run(gh, store, "2026-11-19T15:05:00+00:00", slug="o/r")
    assert _puts(gh) == [("api", "-X", "PUT", "repos/o/r/pulls/28/update-branch", "-f", f"expected_head_sha={H2}")]
    gh2 = MainGreenGh([tick_pr(28, [red()], head=H2)], behind=2)
    chores.run(gh2, store, "2026-11-19T16:05:00+00:00", slug="o/r")
    assert _puts(gh2) == []                                                                    # once per UTC day


def test_no_second_merge_of_main_while_main_is_red_or_unreadable_on_that_check(tmp_path):
    for conclusion in ("failure", None):
        store = _store(tmp_path / str(conclusion))
        chores.run(RedGh([tick_pr(28, [red()])], behind=3), store, NOW, slug="o/r")
        chores.run(RedGh([tick_pr(28, [red()])], behind=3), store, LATER, slug="o/r")
        gh = MainGreenGh([tick_pr(28, [red()], head=H2)], main_conclusion=conclusion, behind=2)
        chores.run(gh, store, "2026-11-19T15:05:00+00:00", slug="o/r")
        assert _puts(gh) == []


# --- a green, armed demand snapshot that fell behind main gets main merged in (2026-11-26) ------------------------
# Its owner is the publisher's auto-merge; with strict protection a BEHIND PR never merges by itself (#2057 sat
# BEHIND for 22 h). Once per PR per UTC day, only when every required check passed and the merge is armed.

def _snap(n=2057, behind=True, armed=True, checks=None, branch="jr/demand-20261124-1115"):
    p = pr(n, branch=branch, head=H1)
    p["mergeStateStatus"] = "BEHIND" if behind else "CLEAN"
    p["autoMergeRequest"] = {"enabledAt": "2026-11-24T11:16:29Z"} if armed else None
    p["statusCheckRollup"] = checks if checks is not None else [
        {"name": n_, "conclusion": "SUCCESS", "status": "COMPLETED", "detailsUrl": "https://github.com/o/r/actions/runs/1/job/2"}
        for n_ in ("schema", "tests", "jr-tests")]
    return p


def test_a_green_armed_snapshot_behind_main_is_updated_once_a_day(tmp_path):
    store, gh = _store(tmp_path), RedGh([_snap()])
    chores.run(gh, store, NOW, slug="o/r")
    chores.run(gh, store, LATER, slug="o/r")
    puts = [c for c in gh.calls if c[:3] == ("api", "-X", "PUT")]
    assert puts == [("api", "-X", "PUT", "repos/o/r/pulls/2057/update-branch", "-f", f"expected_head_sha={H1}")]


@pytest.mark.parametrize("kw", [{"behind": False}, {"armed": False},
                                {"checks": [red("tests")]}, {"branch": "feat/x"}])
def test_no_update_when_not_behind_not_armed_red_or_not_a_snapshot(tmp_path, kw):
    store, gh = _store(tmp_path), RedGh([_snap(**kw)])
    chores.run(gh, store, NOW, slug="o/r")
    assert not [c for c in gh.calls if c[:3] == ("api", "-X", "PUT") and "/2057/" in c[3]]
