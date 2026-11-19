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


def test_the_daily_line_comes_once_a_utc_day_from_12z_with_the_numbers(tmp_path):
    store = _store(tmp_path)
    prs = [pr(3, labels=["needs-human"], updated="2026-11-18T12:00:00Z")]
    gh = Gh(prs, merged=merged("espatlas-jr", "espatlas-jr", "fcavalcantirj"))
    early = chores.run(gh, store, "2026-11-19T11:05:00+00:00", slug="o/r")
    first = chores.run(gh, store, NOW, slug="o/r")
    again = chores.run(gh, store, LATER, slug="o/r")
    assert early["digest"] is None and again["digest"] is None
    line = first["digest"]
    assert line.startswith("🧹 Jr daily 2026-11-19") and "merged by Jr 2" in line and "by a person 1" in line
    assert "#3 needs-human 24 h" in line and "self-sufficient 0/7 days" in line


def _day(store, gh, day):
    return chores.run(gh, store, f"2026-11-{day}T12:05:00+00:00", slug="o/r")["digest"]


def test_self_sufficient_days_count_up_and_a_human_merge_breaks_the_run(tmp_path):
    store = _store(tmp_path)
    clean = Gh([], merged=merged("espatlas-jr", "github-actions[bot]"))
    assert "self-sufficient 1/7 days" in _day(store, clean, 19)
    assert "self-sufficient 2/7 days" in _day(store, clean, 20)
    assert "self-sufficient 0/7 days" in _day(store, Gh([], merged=merged("fcavalcantirj")), 21)
    assert "self-sufficient 1/7 days" in _day(store, clean, 22)


def test_a_waiting_needs_human_pr_or_a_halted_heal_is_not_a_self_sufficient_day(tmp_path):
    store = _store(tmp_path)
    assert "self-sufficient 0/7 days" in _day(store, Gh([pr(3, labels=["needs-human"])], merged=[]), 19)
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
    prs = [pr(5, created="2026-11-17T12:00:00Z"), pr(6, created="2026-11-18T06:00:00Z", updated=NOW), pr(7),
           pr(8, draft=True, created="2026-11-01T00:00:00Z")]
    line = chores.run(Gh(prs, merged=merged("espatlas-jr")), _store(tmp_path), NOW, slug="o/r")["digest"]
    assert "2 PR(s) open ≥ 24 h (oldest #5, 48 h)" in line and "self-sufficient 0/7 days" in line   # CI touching #6 changes nothing


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

