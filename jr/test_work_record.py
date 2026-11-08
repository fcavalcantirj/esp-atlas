"""jr/work_record.py — the executor's only write path into docs/demand/research-queue.json and
docs/demand/work-receipts.json (SPEC-demand-work-consumer.md, Required execution path 2-4; decision
2026-11-08). Every command re-reads both files, applies one change, re-runs the broker's own
fail-closed readers (research_work._readable_receipt, readable_validation, inconsistent_closures,
_work) and refuses to write a pair plan_work would DEFER on. Writes go through the queue's atomic
writer, queue first. No network, no git, no gh.

Run: cd jr && python3 -m pytest test_work_record.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import demand_broker as broker
import research_queue
import research_work as rw
import work_record
from test_demand_broker import REAL_SNAPSHOT, gh_remote
from test_demand_closure import (KEY as FNK_KEY, PR_URL as FNK_PR, QUEUE, RECEIPTS, demand_dir)
from test_pam_work_intake import DAY, NEXT, ledger, prepare, reserve

PAM_PR = "https://github.com/fcavalcantirj/esp-atlas/pull/1600"
VALIDATION = {"validated_by": "executor test", "primary_sources": ["https://vendor.example/board-n.pdf"],
              "expected_ids": ["board-n"], "forbidden_ids": ["board-c"], "notes": "distinct from ES3C28P"}


def pam_dir(tmp_path):
    """A demand dir whose only receipt is a fresh PAM reservation (candidate `new`, queue empty)."""
    prepare(tmp_path, catalog=[])
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_PAM)
    assert out.action == rw.START and out.key.startswith("pam-")
    return tmp_path, out.key


def queue(d):
    return json.loads((d / QUEUE).read_text())


def receipt(d, key):
    return next(r for r in ledger(d)["receipts"] if r["key"] == key)


def pair(d):
    return (d / QUEUE).read_bytes(), (d / RECEIPTS).read_bytes()


def plan(d, key_class, today=DAY):
    """What the broker would do next for that class (offline: no remote work exists)."""
    return reserve(d, REAL_SNAPSHOT, source_class=key_class, today=today, gh=gh_remote())


# --- adopt: the PAM candidate becomes a committed queue row -------------------------------------------

def test_adopt_materializes_the_receipts_candidate_under_its_pam_key(tmp_path):
    d, key = pam_dir(tmp_path)
    assert key not in queue(d)["candidates"]
    c = work_record.adopt(d, key, today=DAY)
    assert queue(d)["candidates"][key] == c == receipt(d, key)["candidate"]
    assert rw.candidate_key(c) == key and c["status"] == "new" and "window" not in c
    assert plan(d, rw.CLASS_PAM).action == rw.RECONCILE          # same-day reservation: nothing else changes


def test_adopt_is_idempotent_and_never_rewrites_a_present_row(tmp_path):
    d, key = pam_dir(tmp_path)
    work_record.adopt(d, key, today=DAY)
    before = pair(d)
    work_record.adopt(d, key, today=DAY)
    assert pair(d) == before


def test_adopt_refuses_a_search_receipt_and_an_unknown_key(tmp_path):
    d = demand_dir(tmp_path)
    before = pair(d)
    with pytest.raises(work_record.RecordError):
        work_record.adopt(d, FNK_KEY, today=NEXT)
    with pytest.raises(work_record.RecordError):
        work_record.adopt(d, "pam-" + "0" * 24, today=NEXT)
    assert pair(d) == before


# --- validate: the identity/primary-source receipt ------------------------------------------------------

def test_validate_writes_a_readable_validation_and_promotes_the_candidate(tmp_path):
    d, key = pam_dir(tmp_path)
    work_record.adopt(d, key, today=DAY)
    c = work_record.validate(d, key, VALIDATION, today=DAY)
    assert c["status"] == "validated"
    v = c["validation"]
    assert v["identity_verified"] is True and v["term_key"] == rw.term_key(c["term"])
    assert v["verified_on"] == DAY and v["verification_kind"] == rw.KIND_CATALOG_PART
    assert v["expected_ids"] == ["board-n"] and v["forbidden_ids"] == ["board-c"]
    assert rw.readable_validation(queue(d)["candidates"][key]) == v
    assert plan(d, rw.CLASS_PAM, today=NEXT).action == rw.RESUME     # authoring may now resume tomorrow


def test_validate_of_a_search_candidate_defaults_to_catalog_search(tmp_path):
    d = demand_dir(tmp_path)
    q = queue(d)
    q["candidates"]["fnk0104s"].update(status="new", validation=None, linked_work=[])
    (d / QUEUE).write_text(json.dumps(q))
    r = ledger(d)
    r["receipts"][0].update(phase="research", linked_work=[])
    r["receipts"][0].pop("pr_url", None)
    (d / RECEIPTS).write_text(json.dumps(r))
    c = work_record.validate(d, FNK_KEY, {**VALIDATION, "expected_ids": ["freenove-fnk0104s"],
                                          "forbidden_ids": ["freenove-fnk0104a"]}, today=NEXT)
    assert c["validation"]["verification_kind"] == rw.KIND_CATALOG_SEARCH


@pytest.mark.parametrize("bad", [
    {"expected_ids": []},
    {"primary_sources": []},
    {"validated_by": ""},
    {"forbidden_ids": ["board-n"]},                       # forbidden and expected overlap
    {"verification_kind": "vibes"},
    {"verified_on": "20261106"},
])
def test_validate_refuses_an_unreadable_receipt_and_writes_nothing(tmp_path, bad):
    d, key = pam_dir(tmp_path)
    work_record.adopt(d, key, today=DAY)
    before = pair(d)
    with pytest.raises(work_record.RecordError):
        work_record.validate(d, key, {**VALIDATION, **bad}, today=DAY)
    assert pair(d) == before


def test_validate_needs_the_candidate_in_the_committed_queue(tmp_path):
    d, key = pam_dir(tmp_path)                                   # not adopted
    with pytest.raises(work_record.RecordError, match="adopt"):
        work_record.validate(d, key, VALIDATION, today=DAY)


# --- link: the reviewed PR ----------------------------------------------------------------------------

def test_link_records_the_pr_on_both_files_and_moves_the_work_to_author(tmp_path):
    d, key = pam_dir(tmp_path)
    work_record.adopt(d, key, today=DAY)
    work_record.validate(d, key, VALIDATION, today=DAY)
    c = work_record.link(d, key, PAM_PR, today=NEXT)
    assert c["status"] == "linked" and c["linked_work"] == [PAM_PR]
    r = receipt(d, key)
    assert r["pr_url"] == PAM_PR and r["phase"] == "author" and r["last_attempt_on"] == NEXT
    assert PAM_PR in r["linked_work"] and rw._readable_receipt(r)
    assert plan(d, rw.CLASS_PAM, today=NEXT).action == rw.RECONCILE   # the broker now verifies, never duplicates


def test_link_refuses_an_unvalidated_candidate_a_second_pr_and_a_non_url(tmp_path):
    d, key = pam_dir(tmp_path)
    work_record.adopt(d, key, today=DAY)
    before = pair(d)
    with pytest.raises(work_record.RecordError):
        work_record.link(d, key, PAM_PR, today=DAY)             # still `new`
    assert pair(d) == before
    work_record.validate(d, key, VALIDATION, today=DAY)
    work_record.link(d, key, PAM_PR, today=DAY)
    before = pair(d)
    with pytest.raises(work_record.RecordError):
        work_record.link(d, key, PAM_PR.replace("1600", "1601"), today=DAY)
    with pytest.raises(work_record.RecordError):
        work_record.link(d, key, "pull 1600", today=DAY)
    assert pair(d) == before
    assert work_record.link(d, key, PAM_PR, today=DAY)["linked_work"] == [PAM_PR]   # the same PR again: no-op


# --- attempt: today's try, so RESUME becomes RECONCILE ---------------------------------------------------

def test_attempt_stamps_the_receipt(tmp_path):
    d, key = pam_dir(tmp_path)
    assert plan(d, rw.CLASS_PAM, today=NEXT).action == rw.RESUME
    r = work_record.attempt(d, key, today=NEXT)
    assert r["last_attempt_on"] == NEXT and receipt(d, key) == r
    assert plan(d, rw.CLASS_PAM, today=NEXT).action == rw.RECONCILE


# --- settle: abandoned / rejected ---------------------------------------------------------------------

def test_settle_abandons_a_search_receipt_so_the_next_item_can_start(tmp_path):
    prepare(tmp_path, catalog=[])
    out = reserve(tmp_path, REAL_SNAPSHOT, source_class=rw.CLASS_SEARCH)
    key = out.key
    r = work_record.settle(tmp_path, key, state="abandoned", reason="not catalog content", today=NEXT)
    assert r["state"] == "abandoned"
    assert r["resolution"] == {"status": "abandoned", "reason": "not catalog content", "closed_on": NEXT,
                               "evidence": {"settled_by": work_record.SETTLED_BY}}
    assert rw._readable_receipt(receipt(tmp_path, key))
    nxt = plan(tmp_path, rw.CLASS_SEARCH, today=NEXT)
    assert nxt.action == rw.START and nxt.key != key                 # keeloq_mfcodes takes the slot


def test_settle_closes_an_adopted_pam_candidate_consistently(tmp_path):
    d, key = pam_dir(tmp_path)
    work_record.adopt(d, key, today=DAY)
    work_record.settle(d, key, state="rejected", reason="kit, not a board", today=NEXT)
    c = queue(d)["candidates"][key]
    assert c["status"] == "closed" and c["closed_on"] == NEXT
    assert c["outcome"] == {"status": "rejected", "reason": "kit, not a board"}
    assert c["history"][-1] == {"event": "closed", "date": NEXT, "resolution": "rejected", "work": key,
                                "reason": "kit, not a board"}
    assert rw.inconsistent_closures(queue(d), ledger(d)["receipts"]) == []
    nxt = plan(d, rw.CLASS_PAM, today=NEXT)
    assert nxt.action == rw.START and nxt.key != key                 # the next lead; this one is handled


@pytest.mark.parametrize("state", ["delivered", "proposed", "done"])
def test_settle_accepts_only_abandoned_or_rejected(tmp_path, state):
    d, key = pam_dir(tmp_path)
    before = pair(d)
    with pytest.raises(work_record.RecordError):
        work_record.settle(d, key, state=state, reason="x", today=DAY)
    assert pair(d) == before


def test_settle_needs_a_reason_and_a_live_receipt(tmp_path):
    d, key = pam_dir(tmp_path)
    with pytest.raises(work_record.RecordError):
        work_record.settle(d, key, state="abandoned", reason="  ", today=DAY)
    work_record.settle(d, key, state="abandoned", reason="dup", today=DAY)
    before = pair(d)
    with pytest.raises(work_record.RecordError, match="not live"):
        work_record.settle(d, key, state="abandoned", reason="again", today=DAY)
    assert pair(d) == before


# --- the guard: nothing plan_work would refuse is ever written ----------------------------------------

def test_a_change_that_would_leave_the_pair_blocked_is_refused(tmp_path):
    d, key = pam_dir(tmp_path)
    work_record.adopt(d, key, today=DAY)
    q = queue(d)
    q["candidates"][key]["status"] = "half-validated"             # a foreign corruption already on disk
    (d / QUEUE).write_text(json.dumps(q))
    before = pair(d)
    with pytest.raises(work_record.RecordError, match="unknown status"):
        work_record.attempt(d, key, today=DAY)
    assert pair(d) == before


def test_check_reports_the_broker_view_without_writing(tmp_path):
    d, key = pam_dir(tmp_path)
    before = pair(d)
    report = work_record.check(d, today=NEXT)
    assert report["problems"] == [] and key in report["live"]
    assert pair(d) == before


# --- the CLI ---------------------------------------------------------------------------------------------

def test_cli_round_trip_adopt_validate_link(tmp_path, capsys):
    d, key = pam_dir(tmp_path)
    v = tmp_path / "v.json"
    v.write_text(json.dumps(VALIDATION))
    base = ["--demand-dir", str(d), "--date", DAY]
    assert work_record.main([*base, "adopt", key]) == 0
    assert work_record.main([*base, "validate", key, "--json", str(v)]) == 0
    assert work_record.main([*base, "link", key, PAM_PR]) == 0
    out = capsys.readouterr().out
    assert key in out and "linked" in out
    assert queue(d)["candidates"][key]["status"] == "linked" and receipt(d, key)["pr_url"] == PAM_PR


def test_cli_dry_run_writes_nothing_and_prints_the_plan(tmp_path, capsys):
    d, key = pam_dir(tmp_path)
    before = pair(d)
    rc = work_record.main(["--demand-dir", str(d), "--date", NEXT, "--dry-run", "settle", key,
                           "--state", "abandoned", "--reason", "test"])
    assert rc == 0 and pair(d) == before
    out = capsys.readouterr().out
    assert "dry-run" in out and "abandoned" in out


def test_cli_errors_exit_1_and_write_nothing(tmp_path, capsys):
    d, key = pam_dir(tmp_path)
    before = pair(d)
    rc = work_record.main(["--demand-dir", str(d), "--date", DAY, "link", key, PAM_PR])   # still `new`
    assert rc == 1 and pair(d) == before
    assert "work-record:" in capsys.readouterr().err
    with pytest.raises(SystemExit):                                                       # argparse: exit 2
        work_record.main(["--demand-dir", str(d), "settle", key, "--state", "delivered", "--reason", "x"])
    assert pair(d) == before


def test_cli_never_writes_under_data(tmp_path):
    with pytest.raises(ValueError):
        research_queue.write_bytes(b"{}", research_queue.REPO / "data" / "x.json")
    assert Path(work_record.DEFAULT_DEMAND_DIR).name == "demand"


# --- the executor prompt and the CLI cannot drift ------------------------------------------------------

PROMPT = Path(__file__).resolve().parent.parent / "docs" / "demand" / "EXECUTOR-PROMPT.md"


def prompt_command_lines():
    """Every `python3 jr/work_record.py …` command the executor prompt quotes, placeholders filled."""
    import re
    import shlex
    text = PROMPT.read_text(encoding="utf-8")
    found = re.findall(r"`python3 jr/work_record\.py ([^`]+)`", text)
    assert found, "the prompt quotes no work_record command"
    subs = {"WORK_KEY": "pam-" + "0" * 24, "TODAY": "2026-11-09", "<file>": "v.json", "<pr url>": PAM_PR,
            '"<one sentence with the evidence url>"': '"evidence"', '"<one sentence with the\n   evidence url>"': '"evidence"',
            '"already catalogued as\n     <id>: <evidence>"': '"already catalogued"'}
    out = []
    for cmd in found:
        cmd = " ".join(cmd.split())                     # the prompt wraps long commands over two lines
        for k, v in subs.items():
            cmd = cmd.replace(" ".join(k.split()), v)
        cmd = re.sub(r'"<[^"]*>"', '"text"', cmd)       # any other quoted placeholder
        out.append(shlex.split(cmd))
    return out


@pytest.mark.parametrize("argv", prompt_command_lines(), ids=lambda a: " ".join(a[:3]))
def test_every_command_the_executor_prompt_quotes_parses(argv):
    args = work_record.build_parser().parse_args(argv)
    assert args.cmd in {"check", "attempt", "adopt", "validate", "link", "settle"}
    assert args.date == "2026-11-09"                    # --date after the subcommand reaches the run


def test_date_and_dry_run_are_accepted_before_or_after_the_subcommand():
    before = work_record.build_parser().parse_args(["--date", "2026-11-09", "--dry-run", "check"])
    after = work_record.build_parser().parse_args(["check", "--date", "2026-11-09", "--dry-run"])
    assert (before.date, before.dry_run) == (after.date, after.dry_run) == ("2026-11-09", True)
    plain = work_record.build_parser().parse_args(["check"])
    assert not hasattr(plain, "dry_run") and not hasattr(plain, "date")   # main() fills today / False


def test_cli_date_after_the_subcommand_reaches_the_record(tmp_path):
    d, key = pam_dir(tmp_path)
    assert work_record.main(["--demand-dir", str(d), "attempt", key, "--date", NEXT]) == 0
    assert receipt(d, key)["last_attempt_on"] == NEXT
