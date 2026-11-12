"""jr/ci_watch.py — SPEC-jr-self-heal.md §1-§5, offline. Fixtures are the real jr-tests job logs of
2026-11-12: two red tick PRs (12:00Z, 17:00Z) on ubuntu-26.04 and the last green main run (11:34Z,
ubuntu-24.04), trimmed to the runner-image group and the pytest outcome lines."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import ci_watch as cw

FIX = Path(__file__).with_name("fixtures") / "ci_watch"
RED_1200 = (FIX / "tick-1200.log").read_text()
RED_1700 = (FIX / "tick-1700.log").read_text()
GREEN = (FIX / "main-green.log").read_text()
REQUIRED = ["schema", "tests", "jr-tests"]
NOW = "2026-11-12T18:00:00+00:00"


def obs(source, number, sha, checks, attempt=1):
    """An observation: checks maps name -> (conclusion, log text or None)."""
    return cw.Observation(source=source, number=number, sha=sha, attempt=attempt, run_id=1000 + (number or 0),
                          checks={k: v[0] for k, v in checks.items()},
                          logs={k: v[1] for k, v in checks.items() if v[1] is not None})


def green(source="tick", number=1, sha="a" * 40):
    return obs(source, number, sha, {"schema": ("SUCCESS", None), "tests": ("SUCCESS", None), "jr-tests": ("SUCCESS", GREEN)})


def red(number, log, source="tick", sha=None, check="jr-tests", conclusion="FAILURE", attempt=1):
    checks = {"schema": ("SUCCESS", None), "tests": ("SUCCESS", None), "jr-tests": ("SUCCESS", GREEN)}
    checks[check] = (conclusion, log)
    return obs(source, number, sha or f"{number:040x}", checks, attempt=attempt)


# --- parsing the real logs -------------------------------------------------------------------------

def test_the_real_red_log_names_the_failing_test_the_assertion_and_the_image():
    p = cw.parse_job_log(RED_1200)
    assert p.failed == "jr/test_image_sandbox.py::test_without_the_guard_no_host_file_is_there_to_read"
    assert p.assertion.startswith("AssertionError: {'token file':")
    assert p.image == "ubuntu-26.04 20261101.186.1"


def test_the_green_log_has_no_failure_and_the_old_image():
    p = cw.parse_job_log(GREEN)
    assert p.failed is None and p.assertion is None
    assert p.image == "ubuntu-24.04 20261101.360.1"


def test_one_break_seen_six_hours_apart_has_one_fingerprint():
    # the two logs differ in timestamps and object addresses (0x75efd... vs 0x7162...)
    assert RED_1200 != RED_1700
    assert cw.fingerprint("jr-tests", cw.parse_job_log(RED_1200)) == cw.fingerprint("jr-tests", cw.parse_job_log(RED_1700))


def test_a_different_failing_test_is_a_different_fingerprint():
    other = RED_1200.replace("test_without_the_guard_no_host_file_is_there_to_read", "test_something_else")
    assert cw.fingerprint("jr-tests", cw.parse_job_log(other)) != cw.fingerprint("jr-tests", cw.parse_job_log(RED_1200))


def test_the_same_failure_in_another_check_is_a_different_fingerprint():
    p = cw.parse_job_log(RED_1200)
    assert cw.fingerprint("tests", p) != cw.fingerprint("jr-tests", p)


def test_a_log_without_pytest_lines_falls_back_to_the_first_error_line():
    log = "2026-11-12T12:00:00.0000000Z ##[error]Process completed with exit code 2.\n"
    p = cw.parse_job_log(log)
    assert p.failed is None and p.error == "Process completed with exit code 2."
    assert cw.fingerprint("schema", p) is not None


# --- deciding ----------------------------------------------------------------------------------------

def test_two_red_tick_prs_with_the_same_break_are_an_incident_with_its_context():
    v = cw.evaluate([red(1678, RED_1700), red(1677, RED_1200), green("main", None, "d9beef5f" + "0" * 32)], REQUIRED)
    assert v.kind == "incident"
    assert v.check == "jr-tests" and v.failed.endswith("no_host_file_is_there_to_read")
    assert v.red_image == "ubuntu-26.04 20261101.186.1" and v.green_image == "ubuntu-24.04 20261101.360.1"
    assert v.first_red_sha == f"{1677:040x}" and v.last_green_sha.startswith("d9beef5f")


def test_one_red_tick_pr_with_a_green_main_is_not_an_incident():
    v = cw.evaluate([red(1678, RED_1700), green("tick", 1677), green("main", None)], REQUIRED)
    assert v.kind == "none"


def test_two_red_tick_prs_with_different_breaks_are_not_an_incident():
    other = RED_1200.replace("test_without_the_guard_no_host_file_is_there_to_read", "test_something_else")
    v = cw.evaluate([red(1678, RED_1700), red(1677, other), green("main", None)], REQUIRED)
    assert v.kind == "none"


def test_a_red_main_is_an_incident_on_its_own():
    v = cw.evaluate([green("tick", 1678), red(None, RED_1200, source="main", sha="b" * 40)], REQUIRED)
    assert v.kind == "incident" and v.source == "main"


def test_a_non_required_check_failing_is_ignored():
    v = cw.evaluate([red(1678, RED_1700, check="sources-live"), red(1677, RED_1200, check="sources-live")], REQUIRED)
    assert v.kind == "none"


def test_a_cancelled_required_check_is_rerun_once_not_an_incident():
    v = cw.evaluate([red(1678, None, conclusion="CANCELLED"), green("main", None)], REQUIRED)
    assert v.kind == "rerun" and v.run_id == 1000 + 1678


def test_a_cancelled_check_on_its_second_attempt_is_an_incident():
    v = cw.evaluate([red(1678, None, conclusion="TIMED_OUT", attempt=2),
                     red(1677, None, conclusion="TIMED_OUT", attempt=2), green("main", None)], REQUIRED)
    assert v.kind == "incident" and v.fingerprint


def test_pending_checks_are_not_judged():
    v = cw.evaluate([obs("tick", 1679, "f" * 40, {"jr-tests": ("", None)}), red(1678, RED_1700), green("main", None)],
                    REQUIRED)
    assert v.kind == "none"


# --- the incident record ------------------------------------------------------------------------------

def incident():
    return cw.evaluate([red(1678, RED_1700), red(1677, RED_1200), green("main", None)], REQUIRED)


def test_an_incident_is_recorded_once_with_its_branch(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    first = store.record(incident(), NOW)
    again = store.record(incident(), NOW)
    assert first["state"] == "open" and first["branch"] == "jr/heal-" + first["fingerprint"][:12]
    assert again is None
    assert len(json.loads((tmp_path / "incidents.json").read_text())["incidents"]) == 1


def test_a_resolved_fingerprint_coming_back_is_a_new_incident_with_a_suffix(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    rec = store.record(incident(), NOW)
    store.resolve_green(["jr-tests"], "2026-11-12T19:00:00+00:00")
    assert store.get(rec["id"])["state"] == "resolved"
    back = store.record(incident(), "2026-11-13T09:00:00+00:00")
    assert back["id"] == rec["id"] + "-2" and back["branch"] == rec["branch"] + "-2"


def test_claim_hands_out_one_open_incident_and_marks_it_dispatched(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    rec = store.record(incident(), NOW)
    got = store.claim(NOW)
    assert got["id"] == rec["id"] and got["state"] == "dispatched"
    assert store.claim(NOW) is None


def test_claim_stops_at_two_dispatches_per_utc_day(tmp_path):
    store = cw.Store(tmp_path / "incidents.json")
    for n in range(3):
        log = RED_1200.replace("no_host_file_is_there_to_read", f"case_{n}")
        store.record(cw.evaluate([red(2, log), red(1, log), green("main", None)], REQUIRED), NOW)
    assert store.claim(NOW) and store.claim(NOW)
    assert store.claim(NOW) is None
    assert store.claim("2026-11-13T00:30:00+00:00") is not None


def test_an_unreadable_store_is_refused_not_overwritten(tmp_path):
    p = tmp_path / "incidents.json"
    p.write_text("{not json")
    with pytest.raises(cw.StoreError):
        cw.Store(p).record(incident(), NOW)
    assert p.read_text() == "{not json"


# --- reading GitHub (fail open: the tick keeps running) -------------------------------------------------

class FakeGh:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, *args):
        self.calls.append(args)
        for key, value in self.routes.items():
            if key in " ".join(args):
                rc, out = value
                return SimpleNamespace(returncode=rc, stdout=out, stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="no route")


def test_required_checks_come_from_branch_protection():
    gh = FakeGh({"protection/required_status_checks": (0, json.dumps({"contexts": REQUIRED}))})
    assert cw.required_checks(gh, "o/r") == REQUIRED


def test_an_unreadable_protection_reads_as_unavailable():
    assert cw.required_checks(FakeGh({}), "o/r") is None


def test_watch_never_raises_and_reports_unavailable_when_github_fails(tmp_path):
    out = cw.watch(FakeGh({}), "o/r", cw.Store(tmp_path / "i.json"), NOW)
    assert out == {"status": "unavailable", "why": "required checks unreadable"}


# --- the relay's hard limits (§3) ------------------------------------------------------------------------

def repo_with(tmp_path, files: dict, changes: dict, body=""):
    """A git repo whose main holds `files`, with a branch applying `changes` (None deletes)."""
    def git(*a):
        subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q", "-b", "main"); git("config", "user.email", "t@t"); git("config", "user.name", "t")
    for path, text in files.items():
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True); (tmp_path / path).write_text(text)
    git("add", "-A"); git("commit", "-qm", "base")
    git("checkout", "-qb", "jr/heal-abc")
    for path, text in changes.items():
        if text is None:
            git("rm", "-q", path)
        else:
            (tmp_path / path).parent.mkdir(parents=True, exist_ok=True); (tmp_path / path).write_text(text)
    git("add", "-A"); git("commit", "-qm", "fix")
    return cw.relay_problems(tmp_path, "main", "jr/heal-abc", body)


TEST = "def test_x():\n    assert 1 == 1\n"


def test_a_plain_code_fix_passes_the_relay(tmp_path):
    assert repo_with(tmp_path, {"jr/a.py": "x = 1\n", "jr/test_a.py": TEST}, {"jr/a.py": "x = 2\n"}) == []


@pytest.mark.parametrize("changes,needle", [
    ({"data/boards/x/board.md": "y\n"}, "data/"),
    ({"docs/demand/work-receipts.json": "{}\n"}, "docs/demand/"),
    ({"jr/test_a.py": "import pytest\n@pytest.mark.skip\n" + TEST}, "skip"),
    ({"jr/test_a.py": "import pytest\n@pytest.mark.xfail\n" + TEST}, "xfail"),
    ({"jr/test_a.py": None}, "deletes test file"),
    ({".github/workflows/v.yml": "permissions:\n  contents: write\n"}, "workflow"),
    ({"jr/big.py": "x = 1\n" * 301}, "300"),
])
def test_the_relay_refuses_what_the_spec_forbids(tmp_path, changes, needle):
    files = {"jr/a.py": "x = 1\n", "jr/test_a.py": TEST, "data/boards/x/board.md": "x\n",
             "docs/demand/work-receipts.json": "[]\n", ".github/workflows/v.yml": "on: push\n"}
    problems = repo_with(tmp_path, files, changes)
    assert problems and any(needle in p for p in problems), problems


def test_a_removed_assert_needs_the_pr_body_to_name_it(tmp_path):
    files = {"jr/test_a.py": TEST}
    changes = {"jr/test_a.py": "def test_x():\n    assert 2 == 2\n"}
    assert any("assert" in p for p in repo_with(tmp_path, files, changes, body="fix"))


def test_a_removed_assert_named_in_the_body_with_evidence_passes(tmp_path):
    files = {"jr/test_a.py": TEST}
    changes = {"jr/test_a.py": "def test_x():\n    assert 2 == 2\n"}
    body = "Assertion changed: jr/test_a.py `assert 1 == 1` was wrong because the evidence shows ..."
    assert repo_with(tmp_path, files, changes, body=body) == []


# --- watch() on GitHub's real response shapes, cost, dry run --------------------------------------------

def rollup(run, job, concl):
    url = f"https://github.com/o/r/actions/runs/{run}/job/{job}"
    return [{"name": "schema", "conclusion": "SUCCESS", "detailsUrl": url},
            {"name": "tests", "conclusion": "SUCCESS", "detailsUrl": url},
            {"name": "jr-tests", "conclusion": concl, "detailsUrl": url}]


def github(tick_concl=("FAILURE", "FAILURE"), main_concl="success"):
    prs = [{"number": 1678, "headRefName": "jr/tick-20261112-1700", "headRefOid": "c" * 40,
            "createdAt": "2026-11-12T17:02:30Z", "statusCheckRollup": rollup(78, 781, tick_concl[0])},
           {"number": 1677, "headRefName": "jr/tick-20261112-1600", "headRefOid": "b" * 40,
            "createdAt": "2026-11-12T16:02:51Z", "statusCheckRollup": rollup(77, 771, tick_concl[1])},
           {"number": 1663, "headRefName": "dasbrow/fix-2", "headRefOid": "e" * 40,
            "createdAt": "2026-11-12T03:44:29Z", "statusCheckRollup": rollup(63, 631, "FAILURE")}]
    jobs = {"jobs": [{"name": n, "id": i, "conclusion": main_concl} for n, i in (("schema", 1), ("tests", 2), ("jr-tests", 3))]}
    return FakeGh({
        "protection/required_status_checks": (0, json.dumps({"contexts": REQUIRED})),
        "run list": (0, json.dumps([{"databaseId": 10, "headSha": "d9beef5f" + "0" * 32, "attempt": 1, "status": "completed"}])),
        "runs/10/jobs": (0, json.dumps(jobs)),
        "jobs/781/logs": (0, RED_1700), "jobs/771/logs": (0, RED_1200), "jobs/3/logs": (0, GREEN),
        "pr list": (0, json.dumps(prs)),
    })


def test_watch_turns_two_red_tick_prs_into_one_incident_with_both_images(tmp_path):
    gh, store = github(), cw.Store(tmp_path / "i.json")
    out = cw.watch(gh, "o/r", store, NOW)
    assert out["status"] == "ok" and out["verdict"] == "incident"
    rec = store.get(out["incident"])
    assert rec["context"]["red_image"] == "ubuntu-26.04 20261101.186.1"
    assert rec["context"]["green_image"] == "ubuntu-24.04 20261101.360.1"
    assert rec["context"]["first_red_number"] == 1677
    assert len(gh.calls) <= 8, gh.calls
    assert not any(c[:2] == ("run", "rerun") for c in gh.calls)


def test_watch_on_a_green_ci_costs_at_most_four_calls_and_fetches_no_log(tmp_path):
    gh = github(tick_concl=("SUCCESS", "SUCCESS"))
    out = cw.watch(gh, "o/r", cw.Store(tmp_path / "i.json"), NOW)
    assert out["verdict"] == "none" and len(gh.calls) <= 4, gh.calls
    assert not any("logs" in " ".join(c) for c in gh.calls)


def test_watch_in_a_dry_run_writes_no_store_and_reruns_nothing(tmp_path):
    p = tmp_path / "i.json"
    out = cw.watch(github(), "o/r", cw.Store(p), NOW, dry_run=True)
    assert out["verdict"] == "incident" and out["would"] == "record incident" and not p.exists()
    gh = github(tick_concl=("CANCELLED", "SUCCESS"))
    out = cw.watch(gh, "o/r", cw.Store(p), NOW, dry_run=True)
    assert out["verdict"] == "rerun" and not any(c[:2] == ("run", "rerun") for c in gh.calls)


def test_watch_reruns_a_cancelled_required_check_once(tmp_path):
    gh = github(tick_concl=("CANCELLED", "SUCCESS"))
    gh.routes["actions/runs/78"] = (0, json.dumps({"run_attempt": 1}))
    gh.routes["run rerun"] = (0, "")
    out = cw.watch(gh, "o/r", cw.Store(tmp_path / "i.json"), NOW)
    assert out["verdict"] == "rerun" and out["rerun"] == 78
    assert ("run", "rerun", "78", "--failed") in gh.calls


# --- no loop: per-break cap, cap without a human, stall timeout, one nudge per change ---------------------

def resolved_again(store, times, start_day=12):
    """Record and resolve the same break `times` times, a day apart; returns the last record."""
    rec = None
    for n in range(times):
        day = f"2026-11-{start_day + n:02d}"
        rec = store.record(incident(), f"{day}T09:00:00+00:00")
        if n < times - 1:
            store.resolve_green(["jr-tests"], f"{day}T20:00:00+00:00")
    return rec


def test_the_same_break_a_third_time_needs_a_human_and_is_never_dispatched(tmp_path):
    store = cw.Store(tmp_path / "i.json")
    third = resolved_again(store, 3)
    assert third["state"] == "needs_human" and third["id"].endswith("-3")
    assert store.claim("2026-11-14T10:00:00+00:00") is None


def test_at_most_three_dispatches_without_a_human_ack_then_halt_until_ack(tmp_path):
    store = cw.Store(tmp_path / "i.json")
    for n in range(4):
        log = RED_1200.replace("no_host_file_is_there_to_read", f"case_{n}")
        store.record(cw.evaluate([red(2, log), red(1, log), green("main", None)], REQUIRED), NOW)
    days = ["2026-11-12T10:00:00+00:00", "2026-11-12T11:00:00+00:00", "2026-11-13T10:00:00+00:00"]
    assert all(store.claim(d) for d in days)
    assert store.claim("2026-11-14T10:00:00+00:00") is None
    assert store._load()["halted"] is True
    store.ack("2026-11-14T12:00:00+00:00")
    assert store.claim("2026-11-14T13:00:00+00:00") is not None


def test_a_dispatch_with_no_pr_after_the_stall_window_is_stalled_not_retried(tmp_path):
    store = cw.Store(tmp_path / "i.json")
    rec = store.record(incident(), NOW)
    store.claim("2026-11-12T18:00:00+00:00")
    assert store.progress({}, "2026-11-12T21:00:00+00:00") == []
    assert store.progress({}, "2026-11-12T22:30:00+00:00") == [rec["id"]]
    assert store.get(rec["id"])["state"] == "stalled"
    assert store.claim("2026-11-13T10:00:00+00:00") is None


def test_a_heal_pr_on_the_incident_branch_moves_it_to_pr_opened(tmp_path):
    store = cw.Store(tmp_path / "i.json")
    rec = store.record(incident(), NOW)
    store.claim(NOW)
    store.progress({rec["branch"]: 1700}, "2026-11-12T19:00:00+00:00")
    got = store.get(rec["id"])
    assert got["state"] == "pr_opened" and got["pr"] == 1700


def test_every_state_change_nudges_once_and_a_repeat_hour_nudges_nothing(tmp_path):
    store = cw.Store(tmp_path / "i.json")
    rec = store.record(incident(), NOW)
    first = store.nudges()
    assert len(first) == 1 and rec["id"] in first[0] and "jr-tests" in first[0]
    assert store.nudges() == []
    assert store.record(incident(), NOW) is None and store.nudges() == []
    store.claim(NOW)
    assert any("dispatched" in m for m in store.nudges())
    store.progress({}, "2026-11-13T00:00:00+00:00")
    assert any("stalled" in m and "human" in m for m in store.nudges())


def test_the_halt_nudges_once_with_the_ack_command(tmp_path):
    store = cw.Store(tmp_path / "i.json")
    for n in range(4):
        log = RED_1200.replace("no_host_file_is_there_to_read", f"case_{n}")
        store.record(cw.evaluate([red(2, log), red(1, log), green("main", None)], REQUIRED), NOW)
    for d in ("2026-11-12T10:00:00+00:00", "2026-11-12T11:00:00+00:00", "2026-11-13T10:00:00+00:00", "2026-11-14T10:00:00+00:00"):
        store.claim(d)
    halts = [m for m in store.nudges() if "halted" in m]
    assert len(halts) == 1 and "jr/ci_watch.py ack" in halts[0]
    store.claim("2026-11-15T10:00:00+00:00")
    assert not any("halted" in m for m in store.nudges())
