"""A catalogued firmware's id belongs to its own source repository (2026-11-18).

Firmware ids are name slugs, so a namesake fork derives the same id as a catalogued firmware. A catalogued
firmware Jr never admitted had no `merged` record guarding its id, and the fork's decision took the slot:
`by_id["wled"]` held toshihiromakuuchi/wled (846066903, expired) while data/firmware/wled names wled/WLED,
and every tick PR touching `wled` aborted on the identity check (four ticks, Nov 18). 13 catalogued ids on
main named another repository; 14 had no record at all.

- `memory.reconcile_catalogued` gives every catalogued firmware a `merged` record of its own source, and moves
  another repository's TTL'd/expired/seen/merged record to that repo's note key (`repo-note:<owner/repo>`, no
  repo_id), so it stays decided. A human veto or an open proposal is never touched; nothing is deleted.
- `memory._write` backfills a missing repo_id on a refused write ONLY from the same repository: a fork's
  refused rejection must never stamp the fork's id onto the catalogued record.
Pure: temp ledgers only. Run: cd jr && python3 -m pytest test_memory_catalogued.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import ledger_guard
import memory

NOW = datetime(2026, 11, 18, 22, 0, tzinfo=timezone.utc)
FORK = {"id": "wled", "repo": "toshihiromakuuchi/wled", "status": "expired", "timestamp": "2026-09-12T04:00:31+00:00",
        "pr_ref": None, "reason": "below_floor: 0 stars / 0 forks", "expires": "2026-10-12T04:00:31+00:00",
        "expired_at": "2026-10-12T05:00:00+00:00", "repo_id": 846066903}
VETO = {"id": "ghost-esp", "repo": "ghost-esp", "status": "rejected", "timestamp": "2026-09-08T00:00:00+00:00",
        "pr_ref": "#165", "reason": "PR closed unmerged: #165"}
MERGED_OTHER = {"id": "sshclient", "repo": "sub0pt1mal/ssh", "status": "merged", "timestamp": "2026-09-01T00:00:00+00:00",
                "pr_ref": "#99", "repo_id": 779484879}
PROPOSED_OTHER = {"id": "nyan", "repo": "someone/nyan", "status": "proposed", "timestamp": "2026-11-18T00:00:00+00:00", "pr_ref": "#1900"}
SAME = {"id": "bruce", "repo": "brucedevices/firmware", "status": "merged", "timestamp": "2026-09-01T00:00:00+00:00",
        "pr_ref": "#50", "repo_id": 795166961}
IDS = {"wled/wled": 76990209, "fernandofatech/ssh": 734161317, "brucedevices/firmware": 795166961}
SOURCES = {"wled": "wled/wled", "ghost-esp": "spooks4576/ghost_esp", "sshclient": "fernandofatech/ssh",
           "nyan": "temporal/nyan-mode", "bruce": "brucedevices/firmware", "fresh": "o/fresh"}


def _ledger(tmp_path, *records):
    p = tmp_path / "proposed_ledger.json"
    p.write_text(json.dumps({"by_id": {r["id"]: dict(r) for r in records},
                             "by_repo": {r["repo"]: r["id"] for r in records}}))
    return p


def _by_id(p):
    return json.loads(p.read_text())["by_id"]


def test_a_namesake_record_moves_to_its_repo_note_and_the_id_takes_the_catalogued_source(tmp_path):
    p = _ledger(tmp_path, FORK)
    out = memory.reconcile_catalogued({"wled": "wled/wled"}, path=p, now=NOW, resolve_id=IDS.get)
    led = json.loads(p.read_text())
    w, note = led["by_id"]["wled"], led["by_id"]["repo-note:toshihiromakuuchi/wled"]
    assert w["repo"] == "wled/wled" and w["status"] == "merged" and "repo_id" not in w
    assert note["id"] == "repo-note:toshihiromakuuchi/wled" and note["status"] == "expired" and "repo_id" not in note
    assert note["reason"] == FORK["reason"] and note["timestamp"] == FORK["timestamp"]           # history kept
    assert led["by_repo"]["toshihiromakuuchi/wled"] == "repo-note:toshihiromakuuchi/wled" and led["by_repo"]["wled/wled"] == "wled"
    assert out == {"added": [], "moved": ["wled"], "renamed": [], "kept": []}


def test_a_catalogued_firmware_without_a_record_gets_its_merged_record(tmp_path):
    p = _ledger(tmp_path)
    out = memory.reconcile_catalogued({"fresh": "o/fresh"}, path=p, now=NOW, resolve_id=IDS.get)
    assert _by_id(p)["fresh"]["status"] == "merged" and _by_id(p)["fresh"]["repo"] == "o/fresh"
    assert out["added"] == ["fresh"]


def test_a_veto_and_a_proposed_record_are_never_touched(tmp_path):
    p = _ledger(tmp_path, VETO, PROPOSED_OTHER, SAME)
    before = _by_id(p)
    out = memory.reconcile_catalogued({k: SOURCES[k] for k in ("ghost-esp", "nyan", "bruce")}, path=p, now=NOW, resolve_id=IDS.get)
    assert _by_id(p) == before
    assert sorted(out["kept"]) == ["ghost-esp", "nyan"] and out["added"] == out["moved"] == []


def test_a_merged_record_of_a_fork_the_catalog_was_pointed_away_from_moves_too(tmp_path):
    # sshclient: the Sep 1 drain admitted the fork SUB0PT1MAL/…; on Sep 2 the catalog record was pointed
    # at the original fernandofatech/… (68b70010). The fork's merged record still owned the id and its id.
    p = _ledger(tmp_path, MERGED_OTHER)
    out = memory.reconcile_catalogued({"sshclient": "fernandofatech/ssh"}, path=p, now=NOW, resolve_id=IDS.get)
    led = json.loads(p.read_text())
    assert out["moved"] == ["sshclient"] and led["by_id"]["sshclient"]["repo"] == "fernandofatech/ssh"
    note = led["by_id"]["repo-note:sub0pt1mal/ssh"]
    assert note["status"] == "rejected" and note.get("expires") and "repo_id" not in note
    assert led["by_repo"]["sub0pt1mal/ssh"] == "repo-note:sub0pt1mal/ssh"
    assert memory.is_blocked(memory.load(p), repo="sub0pt1mal/ssh", now=NOW)                 # the fork stays decided


def test_the_result_passes_the_ledger_guard_and_a_second_run_changes_nothing(tmp_path):
    p = _ledger(tmp_path, FORK, VETO, MERGED_OTHER, PROPOSED_OTHER, SAME)
    base = json.loads(p.read_text())
    memory.reconcile_catalogued(SOURCES, path=p, now=NOW, resolve_id=IDS.get)
    assert ledger_guard.check(base, json.loads(p.read_text())) == []
    once = p.read_text()
    assert memory.reconcile_catalogued(SOURCES, path=p, now=NOW, resolve_id=IDS.get) == {"added": [], "moved": [], "renamed": [], "kept": ["ghost-esp", "nyan"]}
    assert p.read_text() == once


def test_an_empty_catalog_does_nothing(tmp_path):
    p = _ledger(tmp_path, FORK)
    before = p.read_text()
    assert memory.reconcile_catalogued({}, path=p, now=NOW, resolve_id=IDS.get) == {"added": [], "moved": [], "renamed": [], "kept": []}
    assert p.read_text() == before


def test_a_forks_refused_rejection_never_stamps_its_id_on_the_catalogued_record(tmp_path):
    p = _ledger(tmp_path, {"id": "wled", "repo": "wled/wled", "status": "merged", "timestamp": "2026-11-18T00:00:00+00:00", "pr_ref": None})
    memory.record_rejected("wled", "toshihiromakuuchi/wled", "below_floor: 0 stars / 0 forks", ttl_days=30,
                           repo_id=846066903, path=p, now=NOW)
    assert "repo_id" not in _by_id(p)["wled"]


def test_the_same_repositorys_refused_write_still_backfills_its_id(tmp_path):
    p = _ledger(tmp_path, {"id": "wled", "repo": "wled/wled", "status": "merged", "timestamp": "2026-11-18T00:00:00+00:00", "pr_ref": None})
    memory.record_rejected("wled", "WLED/WLED", "already_catalogued: wled/wled", ttl_days=30, repo_id=76990209, path=p, now=NOW)
    assert _by_id(p)["wled"]["repo_id"] == 76990209 and _by_id(p)["wled"]["status"] == "merged"


def test_a_forks_refused_write_over_a_proposal_never_stamps_its_id_either(tmp_path):
    p = _ledger(tmp_path, {"id": "wled", "repo": "wled/wled", "status": "proposed", "timestamp": "2026-11-18T00:00:00+00:00", "pr_ref": "#1839"})
    memory.record_seen("wled", "toshihiromakuuchi/wled", reason="below floor", repo_id=846066903, path=p, now=NOW)
    assert "repo_id" not in _by_id(p)["wled"]


def test_after_the_repair_the_fork_stays_decided_by_its_note(tmp_path):
    p = _ledger(tmp_path, {**FORK, "status": "rejected", "expires": "2026-12-18T00:00:00+00:00"})
    memory.reconcile_catalogued({"wled": "wled/wled"}, path=p, now=NOW, resolve_id=IDS.get)
    led = memory.load(p)
    assert memory.is_blocked(led, repo="toshihiromakuuchi/wled", now=NOW)
    assert memory.lookup(led, repo="wled/wled")["status"] == "merged"


# --- the tick reads the sources from its own worktree --------------------------------------------------------

def test_the_tick_reads_each_github_source_from_firmware_md(tmp_path):
    import tick
    for fid, url in (("wled", "https://github.com/wled/WLED"), ("x", "https://example.com/x"),
                     ("deep", "https://github.com/o/r/tree/main/fw")):
        (tmp_path / fid).mkdir()
        (tmp_path / fid / "firmware.md").write_text(f"---\nid: {fid}\nurl: {url}\n---\n")
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "firmware.md").write_text("---\nurl: [unclosed\n---\n")
    assert tick._catalog_sources(tmp_path) == {"wled": "wled/wled", "deep": "o/r"}


def test_the_hourly_tick_reconciles_the_catalog_after_reconcile_removed():
    import inspect
    import tick
    src = inspect.getsource(tick.run_tick)
    assert src.index("memory.reconcile_removed(") < src.index("memory.reconcile_catalogued(") < src.index("counts = {")



# --- review of #1855 (2026-11-19) ----------------------------------------------------------------------------

def test_the_next_tick_never_turns_a_moved_note_into_a_veto(tmp_path):
    p = _ledger(tmp_path, MERGED_OTHER)
    memory.reconcile_catalogued({"sshclient": "fernandofatech/ssh"}, path=p, now=NOW, resolve_id=IDS.get)
    once = p.read_text()
    assert memory.reconcile_removed({"sshclient"}, path=p, now=NOW) == []
    assert memory.reconcile_catalogued({"sshclient": "fernandofatech/ssh"}, path=p, now=NOW, resolve_id=IDS.get)["moved"] == []
    assert p.read_text() == once                                              # a second tick changes nothing


def test_a_forks_review_decision_never_stamps_its_id_on_the_catalogued_record(tmp_path):
    p = _ledger(tmp_path, {"id": "wled", "repo": "wled/wled", "status": "merged", "timestamp": "2026-11-18T00:00:00+00:00", "pr_ref": None})
    memory.record_review_decision("wled", "toshihiromakuuchi/wled", "below_floor", repo_id=846066903, path=p, now=NOW)
    assert "repo_id" not in _by_id(p)["wled"]
    assert 846066903 not in memory.load(p).get("by_repo_id", {})


def test_a_trailing_dot_git_is_the_same_repository(tmp_path):
    p = _ledger(tmp_path, {"id": "usbarmyknife", "repo": "i-am-shodan/usbarmyknife.git", "status": "expired",
                           "timestamp": "2026-09-12T00:00:00+00:00", "pr_ref": None})
    out = memory.reconcile_catalogued({"usbarmyknife": "i-am-shodan/usbarmyknife"}, path=p, now=NOW, resolve_id=IDS.get)
    assert out == {"added": [], "moved": [], "renamed": [], "kept": []}


def test_removal_reconciliation_never_vetoes_a_repo_note_even_a_merged_one(tmp_path):
    note = {"id": "repo-note:o/x", "repo": "o/x", "status": "merged", "timestamp": "2026-11-01T00:00:00+00:00", "pr_ref": None}
    p = _ledger(tmp_path, note)
    assert memory.reconcile_removed({"something-else"}, path=p, now=NOW) == []
    assert _by_id(p)["repo-note:o/x"]["status"] == "merged"



# --- 2nd review of #1855 (2026-11-19): identity is the GitHub id, never the name ----------------------------

RENAMED = {"id": "cardputer-microhydra", "repo": "echo-lalia/cardputer-microhydra", "status": "rejected",
           "expires": "2026-12-15T22:00:31+00:00", "timestamp": "2026-11-15T22:00:31+00:00", "pr_ref": None,
           "reason": "already_catalogued", "repo_id": 752958524}


def test_a_record_of_the_same_repository_under_its_old_name_is_renamed_in_place_and_keeps_its_id(tmp_path):
    p = _ledger(tmp_path, RENAMED)
    out = memory.reconcile_catalogued({"cardputer-microhydra": "echo-lalia/microhydra"}, path=p, now=NOW,
                                      resolve_id={"echo-lalia/microhydra": 752958524}.get)
    rec = _by_id(p)["cardputer-microhydra"]
    assert out["renamed"] == ["cardputer-microhydra"] and out["moved"] == []
    assert rec["repo"] == "echo-lalia/microhydra" and rec["repo_id"] == 752958524 and rec["status"] == "merged"
    assert {"id": "cardputer-microhydra", "repo": "echo-lalia/cardputer-microhydra"} in rec["aliases"]
    assert "repo-note:echo-lalia/cardputer-microhydra" not in _by_id(p)
    assert memory.load(p)["by_repo_id"][752958524] == "cardputer-microhydra"


def test_a_record_with_an_id_is_never_moved_when_github_cannot_say(tmp_path):
    p = _ledger(tmp_path, RENAMED)
    before = p.read_text()
    out = memory.reconcile_catalogued({"cardputer-microhydra": "echo-lalia/microhydra"}, path=p, now=NOW,
                                      resolve_id=lambda r: None)
    assert out["kept"] == ["cardputer-microhydra"] and p.read_text() == before
    assert memory.reconcile_catalogued({"cardputer-microhydra": "echo-lalia/microhydra"}, path=p, now=NOW)["kept"] == ["cardputer-microhydra"]
