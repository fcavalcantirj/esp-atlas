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


def test_the_switch_file_ships_pr_fix_dispatch_off():
    from pathlib import Path
    doc = json.loads((Path(__file__).resolve().parent / "autonomy.json").read_text())
    assert doc["pr_fix_dispatch"] is False


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
