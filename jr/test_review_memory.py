"""Durable owner-review decisions (jr/review_memory.py, memory.record_review_decision —
SPEC-jr-review-routing.md §5). Ledgers live under tmp_path; gh is a recorder. Never the network,
never the real jr/ state files.

Run: cd jr && python3 -m pytest test_review_memory.py -v
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import memory
import review_memory

NOW = datetime(2026, 11, 6, 17, 0, tzinfo=timezone.utc)
RID = 831377003
REPO = "gdantas04/cardputer-system-monitor"
FID = "cardputer-system-monitor"

# main's record on 2026-11-06: an expired floor reject, the decision the incident kept re-asking over
MAIN_EXPIRED = {"expired_at": "2026-11-05T19:01:17.341039+00:00", "expires": "2026-11-05T19:00:58.979878+00:00",
                "id": FID, "pr_ref": None, "reason": "below_floor: 24 stars / 2 forks", "repo": REPO,
                "repo_id": RID, "status": "expired", "timestamp": "2026-10-06T19:00:58.979878+00:00"}

# the rendered section of #1490 (no marker: opened before it existed)
LEGACY_BODY = """### Skipped this tick (not in this PR; remembered with a TTL)
- needs_review_target: 1

### Needs owner review — no ESP target stated (not admitted)
- `gdantas04/cardputer-system-monitor` (`cardputer-system-monitor`) — arduino_sketch https://github.com/gdantas04/cardputer-system-monitor/blob/main/serial_receiver.ino: a .ino but no ESP board named (sketch.yaml fqbn, esp32 build workflow, library.properties architectures=esp32)
Re-checked after the reject TTL; admit by hand if it does target an ESP.

### Summary
"""


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _ledger(tmp_path, *records):
    p = tmp_path / "jr" / "proposed_ledger.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = {"by_id": {r["id"]: r for r in records}, "by_repo": {r["repo"]: r["id"] for r in records}}
    p.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
    return p


def _meta(stars=30, forks=2, homepage=None, pushed="2026-10-01T00:00:00Z"):
    return {"stars": stars, "forks": forks, "homepage": homepage, "pushed_at": pushed}


def _target(rev="r1", **kw):
    return {"id": FID, "repo": REPO, "repo_id": RID, "evidence_rev": rev,
            "reason": "needs_review_target: arduino_sketch: a .ino but no ESP board named", **kw}


def _pr(number, state, created, body, merged=False):
    return {"number": number, "state": state, "createdAt": _iso(created), "body": body,
            "mergedAt": _iso(created + timedelta(hours=1)) if merged else None}


def _gh(prs, rc=0):
    calls = []

    def gh(*args):
        calls.append(args)
        if args[:2] == ("pr", "list"):
            return SimpleNamespace(returncode=rc, stdout=json.dumps(prs) if rc == 0 else "", stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="unexpected")
    gh.calls = calls
    return gh


def _body(*targets):
    return "### Needs owner review\n- x\n" + review_memory.render_marker(list(targets)) + "\n"


# --- evidence revision: meaningful changes only ---------------------------------------------------

def test_a_star_more_or_less_on_the_same_side_of_the_floor_is_the_same_revision():
    assert review_memory.evidence_rev(review_memory.evidence(_meta(stars=30))) == \
        review_memory.evidence_rev(review_memory.evidence(_meta(stars=31)))


@pytest.mark.parametrize("change", [
    {"stars": 24},                                    # falls below the star floor
    {"forks": 25},                                    # crosses the fork floor
    {"homepage": "https://hackaday.io/project/1"},    # gains an independent editorial home
    {"pushed": "2026-11-06T00:00:00Z"},               # a new source revision
])
def test_crossing_a_floor_a_new_editorial_home_or_a_new_push_is_new_evidence(change):
    base = review_memory.evidence_rev(review_memory.evidence(_meta()))
    assert review_memory.evidence_rev(review_memory.evidence(_meta(**change))) != base


def test_downloads_count_only_when_they_cross_the_download_floor():
    rev = lambda d: review_memory.evidence_rev(review_memory.evidence(_meta(), downloads=d))  # noqa: E731
    assert rev(10) == rev(1999) != rev(2000)


def test_evidence_keeps_the_raw_facts_for_a_human():
    ev = review_memory.evidence(_meta(stars=30, forks=2, homepage="https://github.com/x/y"), downloads=7)
    assert ev == {"stars": 30, "forks": 2, "downloads": 7, "editorial_home": None, "source": "2026-10-01T00:00:00Z"}


def test_holds_unless_both_revisions_are_known_and_differ():
    assert review_memory.holds({"review": {"evidence_rev": "a"}}, "a")
    assert review_memory.holds({"review": {"evidence_rev": None}}, "a")     # a legacy raise: unchanged
    assert review_memory.holds({"review": {"evidence_rev": "a"}}, None)
    assert not review_memory.holds({"review": {"evidence_rev": "a"}}, "b")


# --- the PR-body marker -----------------------------------------------------------------------------

def test_the_marker_round_trips_through_a_pr_body():
    body = "intro\n" + review_memory.render_marker([_target(), {"id": "z", "repo": "o/z"}]) + "\noutro"
    got = review_memory.parse_targets(body)
    assert got[0] == _target() and got[1]["repo"] == "o/z" and got[1]["evidence_rev"] is None


def test_a_legacy_pr_body_is_read_from_its_rendered_review_lines():
    assert review_memory.parse_targets(LEGACY_BODY) == [
        {"id": FID, "repo": REPO, "repo_id": None, "evidence_rev": None, "reason": None}]


def test_a_body_without_a_review_section_or_marker_has_no_targets():
    assert review_memory.parse_targets("### Summary\n- `a/b` (`b`) — not a review line") == []
    assert review_memory.parse_targets(None) == []
    assert review_memory.parse_targets("<!-- jr-review-targets: not json -->") == []


# --- reconcile: GitHub's jr-review PRs → the worktree ledger ----------------------------------------

def test_an_open_review_pr_becomes_a_live_decision_over_mains_expired_record(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    raised = NOW - timedelta(hours=2)
    gh = _gh([_pr(1490, "OPEN", raised, _body(_target()))])
    assert review_memory.reconcile(gh, path, NOW) == [FID]
    rec = memory.load(path)["by_id"][FID]
    assert rec["status"] == "rejected" and rec["repo_id"] == RID and rec["reason"].startswith("needs_review_target:")
    assert rec["review"] == {"outcome": "open", "pr_ref": "#1490", "raised_at": raised.isoformat(),
                             "evidence_rev": "r1", "evidence": None}
    assert rec["expires"] == (raised + timedelta(days=memory.NO_BUILD_SIGNAL_DAYS)).isoformat()
    assert rec["history"] == [MAIN_EXPIRED]                       # never deleted: the old decision is kept
    assert memory.is_blocked(memory.load(path), repo=REPO, now=NOW)
    (call,) = gh.calls
    assert call[:2] == ("pr", "list") and "--label" in call and call[call.index("--state") + 1] == "all"


def test_reconcile_is_idempotent_an_unchanged_decision_writes_nothing(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    gh = _gh([_pr(1490, "OPEN", NOW - timedelta(hours=2), _body(_target()))])
    review_memory.reconcile(gh, path, NOW)
    before = path.read_text()
    assert review_memory.reconcile(gh, path, NOW + timedelta(hours=1)) == []
    assert path.read_text() == before


def test_a_closed_unmerged_review_pr_is_a_closed_decision_and_appends_history(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    raised = NOW - timedelta(hours=5)
    review_memory.reconcile(_gh([_pr(1478, "OPEN", raised, _body(_target()))]), path, NOW - timedelta(hours=3))
    assert review_memory.reconcile(_gh([_pr(1478, "CLOSED", raised, _body(_target()))]), path, NOW) == [FID]
    rec = memory.load(path)["by_id"][FID]
    assert rec["review"]["outcome"] == "closed" and rec["review"]["pr_ref"] == "#1478"
    assert [h.get("status") for h in rec["history"]] == ["expired", "rejected"]
    assert rec["history"][1]["review"]["outcome"] == "open" and "history" not in rec["history"][1]


def test_the_most_recent_raise_decides_and_a_merged_one_is_left_to_mains_ledger(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    old, new = NOW - timedelta(hours=9), NOW - timedelta(hours=1)
    review_memory.reconcile(_gh([_pr(1477, "CLOSED", old, LEGACY_BODY), _pr(1490, "OPEN", new, LEGACY_BODY)]), path, NOW)
    assert memory.load(path)["by_id"][FID]["review"]["pr_ref"] == "#1490"
    path2 = _ledger(tmp_path / "b", MAIN_EXPIRED)
    assert review_memory.reconcile(_gh([_pr(1477, "CLOSED", old, LEGACY_BODY),
                                        _pr(1491, "MERGED", new, LEGACY_BODY, merged=True)]), path2, NOW) == []


def test_an_expired_raise_is_not_hydrated_so_the_target_is_reconsidered(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    raised = NOW - timedelta(days=memory.NO_BUILD_SIGNAL_DAYS, hours=1)
    assert review_memory.reconcile(_gh([_pr(1300, "CLOSED", raised, _body(_target()))]), path, NOW) == []
    assert memory.load(path)["by_id"][FID] == MAIN_EXPIRED


def test_a_newer_decision_on_main_is_never_replaced_by_an_older_raise(tmp_path):
    newer = {"id": FID, "repo": REPO, "repo_id": RID, "status": "rejected", "pr_ref": None,
             "reason": "below_floor: 3 stars / 0 forks", "timestamp": NOW.isoformat(),
             "expires": (NOW + timedelta(days=30)).isoformat()}
    path = _ledger(tmp_path, newer)
    assert review_memory.reconcile(_gh([_pr(1490, "CLOSED", NOW - timedelta(days=2), _body(_target()))]), path, NOW) == []
    assert memory.load(path)["by_id"][FID] == newer


def test_a_merged_proposal_or_permanent_veto_is_never_overwritten(tmp_path):
    merged = {"id": FID, "repo": REPO, "status": "merged", "pr_ref": "#9", "timestamp": "2026-01-01T00:00:00+00:00"}
    path = _ledger(tmp_path, merged)
    review_memory.reconcile(_gh([_pr(1490, "OPEN", NOW, _body(_target()))]), path, NOW)
    assert memory.load(path)["by_id"][FID]["status"] == "merged"


def test_a_failed_lookup_returns_none_and_writes_nothing(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    assert review_memory.reconcile(_gh([], rc=1), path, NOW) is None
    assert memory.load(path)["by_id"][FID] == MAIN_EXPIRED


def test_an_unparseable_pr_list_is_a_failed_lookup(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)

    def gh(*a):
        return SimpleNamespace(returncode=0, stdout="not json", stderr="")
    assert review_memory.reconcile(gh, path, NOW) is None


# --- memory.record_review_decision ------------------------------------------------------------------

def test_a_raised_decision_is_keyed_by_repo_id_and_carries_its_evidence(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    ev = review_memory.evidence(_meta())
    memory.record_review_decision(FID, REPO, "needs_review_target: x", repo_id=RID, evidence=ev,
                                  evidence_rev=review_memory.evidence_rev(ev), path=path, now=NOW)
    led = memory.load(path)
    rec = memory.lookup(led, repo_id=RID)
    assert rec["review"]["outcome"] == "raised" and rec["review"]["evidence"] == ev and rec["review"]["pr_ref"] is None
    assert review_memory.live_decision(led, NOW, repo_id=RID) is rec
    assert review_memory.live_decision(led, NOW + timedelta(days=memory.NO_BUILD_SIGNAL_DAYS + 1), repo_id=RID) is None


def test_a_plain_rejection_over_a_review_decision_keeps_its_history(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    memory.record_review_decision(FID, REPO, "needs_review_target: x", repo_id=RID, evidence_rev="a", path=path, now=NOW)
    memory.record_rejected(FID, REPO, "below_floor: 3 stars / 0 forks", ttl_days=30, repo_id=RID, path=path,
                           now=NOW + timedelta(days=1))
    rec = memory.load(path)["by_id"][FID]
    assert rec["reason"].startswith("below_floor") and "review" not in rec
    assert [h["status"] for h in rec["history"]] == ["expired", "rejected"] and rec["history"][1]["review"]["evidence_rev"] == "a"


def test_a_plain_record_without_review_or_history_gains_no_history(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    memory.record_rejected(FID, REPO, "below_floor: 3 stars / 0 forks", ttl_days=30, path=path, now=NOW)
    assert "history" not in memory.load(path)["by_id"][FID]


def test_live_decision_ignores_plain_rejections():
    led = {"by_id": {FID: {**MAIN_EXPIRED, "status": "rejected", "expires": _iso(NOW + timedelta(days=3))}},
           "by_repo": {REPO: FID}, "by_repo_id": {RID: FID}}
    assert review_memory.live_decision(led, NOW, repo=REPO) is None


def test_a_reason_containing_a_comment_terminator_survives_the_marker():
    t = _target(reason="needs_review_target: a --> b")
    assert review_memory.parse_targets(review_memory.render_marker([t])) == [t]


# --- one numeric repo_id, one decision: a rename never shadows a permanent veto --------------------

OLD_FID, OLD_REPO = "a-old-firmware", "espdev/old-firmware"
NEW_FID, NEW_REPO = "z-new-firmware", "espdev/new-firmware"
SHARED_RID = 42
OLD_VETO = {"id": OLD_FID, "repo": OLD_REPO, "repo_id": SHARED_RID, "status": "rejected", "pr_ref": "#12",
            "reason": "human closed #12 unmerged", "timestamp": "2026-01-01T00:00:00+00:00"}


def _renamed(**kw):
    return _target(id=NEW_FID, repo=NEW_REPO, repo_id=SHARED_RID, **kw)


def test_a_renamed_target_never_shadows_a_permanent_veto_for_the_same_repo_id(tmp_path):
    path = _ledger(tmp_path, OLD_VETO)
    gh = _gh([_pr(1495, "OPEN", NOW - timedelta(hours=2), _body(_renamed()))])
    review_memory.reconcile(gh, path, NOW)
    led = memory.load(path)
    assert list(led["by_id"]) == [OLD_FID]                          # one record per repo_id, never two
    rec = led["by_id"][OLD_FID]
    assert memory.is_permanent_rejection(rec) and rec["reason"] == OLD_VETO["reason"]
    assert rec["aliases"] == [{"id": NEW_FID, "repo": NEW_REPO}]    # the new name is remembered
    later = NOW + timedelta(days=61)
    assert led["by_repo_id"][SHARED_RID] == OLD_FID
    assert memory.is_blocked(led, repo_id=SHARED_RID, now=later)
    assert memory.is_blocked(led, repo=NEW_REPO, now=later)
    before = path.read_text()
    assert review_memory.reconcile(gh, path, NOW + timedelta(hours=1)) == []   # idempotent
    assert path.read_text() == before


def test_a_renamed_decision_is_written_under_the_repo_ids_record_keeping_its_history(tmp_path):
    old_expired = {**MAIN_EXPIRED, "id": OLD_FID, "repo": OLD_REPO, "repo_id": SHARED_RID}
    path = _ledger(tmp_path, old_expired)
    assert memory.record_review_decision(NEW_FID, NEW_REPO, "needs_review_target: x", repo_id=SHARED_RID,
                                         evidence_rev="a", path=path, now=NOW)
    led = memory.load(path)
    assert list(led["by_id"]) == [OLD_FID]
    rec = led["by_id"][OLD_FID]
    assert rec["status"] == "rejected" and rec["review"]["evidence_rev"] == "a"
    assert rec["history"] == [old_expired] and rec["aliases"] == [{"id": NEW_FID, "repo": NEW_REPO}]
    assert led["by_repo"][NEW_REPO] == OLD_FID
    assert review_memory.live_decision(led, NOW, repo_id=SHARED_RID) is rec


def test_record_review_decision_never_weakens_a_veto_held_under_another_id(tmp_path):
    path = _ledger(tmp_path, OLD_VETO)
    memory.record_review_decision(NEW_FID, NEW_REPO, "needs_review_target: x", repo_id=SHARED_RID,
                                  evidence_rev="a", path=path, now=NOW)
    led = memory.load(path)
    assert set(led["by_id"]) == {OLD_FID}
    assert {k: v for k, v in led["by_id"][OLD_FID].items() if k != "aliases"} == OLD_VETO
    assert memory.is_blocked(led, repo_id=SHARED_RID, now=NOW + timedelta(days=61))


def test_a_ledger_already_holding_a_shadowing_duplicate_still_resolves_the_repo_id_to_the_veto(tmp_path):
    shadow = {"id": NEW_FID, "repo": NEW_REPO, "repo_id": SHARED_RID, "status": "rejected", "pr_ref": None,
              "reason": "needs_review_target: x", "timestamp": NOW.isoformat(),
              "expires": (NOW + timedelta(days=60)).isoformat(), "review": {"outcome": "open"}}
    led = memory.load(_ledger(tmp_path, OLD_VETO, shadow))
    assert led["by_repo_id"][SHARED_RID] == OLD_FID
    assert memory.is_blocked(led, repo_id=SHARED_RID, now=NOW + timedelta(days=61))


# --- latest_raises groups by the stable repo_id, not the name ---------------------------------------

def test_a_newer_merged_raise_under_a_new_name_supersedes_an_older_open_one_for_the_same_repo_id(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    old, new = NOW - timedelta(hours=9), NOW - timedelta(hours=1)
    prs = [_pr(1480, "OPEN", old, _body(_target(id=OLD_FID, repo=OLD_REPO, repo_id=SHARED_RID))),
           _pr(1494, "MERGED", new, _body(_renamed()), merged=True)]
    assert len(review_memory.latest_raises(prs)) == 1
    before = path.read_text()
    assert review_memory.reconcile(_gh(prs), path, NOW) == []       # main's ledger already has the merge
    assert path.read_text() == before


def test_raises_without_a_repo_id_still_group_by_name():
    old, new = NOW - timedelta(hours=9), NOW - timedelta(hours=1)
    got = review_memory.latest_raises([_pr(1477, "CLOSED", old, LEGACY_BODY), _pr(1490, "OPEN", new, LEGACY_BODY)])
    assert [pr["number"] for _, pr, _ in got.values()] == [1490]


# --- a reconciled marker keeps its raw evidence -----------------------------------------------------

def test_reconcile_persists_the_evidence_a_review_marker_carries(tmp_path):
    path = _ledger(tmp_path, MAIN_EXPIRED)
    ev = review_memory.evidence(_meta())
    t = _target(rev=review_memory.evidence_rev(ev), evidence=ev)
    assert review_memory.reconcile(_gh([_pr(1495, "OPEN", NOW - timedelta(hours=2), _body(t))]), path, NOW) == [FID]
    rec = memory.lookup(memory.load(path), repo_id=RID)
    assert rec["review"]["evidence"] == ev and rec["review"]["evidence_rev"] == t["evidence_rev"]


# --- the numeric repo_id's owner always wins; an id collision never overwrites another repo_id ------

OTHER_RID, OTHER_REPO = 99, "someone/new-firmware"
OLD_OWNER = {**MAIN_EXPIRED, "id": OLD_FID, "repo": OLD_REPO, "repo_id": SHARED_RID}
UNRELATED = {**MAIN_EXPIRED, "id": NEW_FID, "repo": OTHER_REPO, "repo_id": OTHER_RID}


def _repo_id_owners(led):
    return sorted((rec["id"], rec.get("repo_id")) for rec in led["by_id"].values())


def _assert_owner_took_it_and_unrelated_is_untouched(led):
    assert _repo_id_owners(led) == [(OLD_FID, SHARED_RID), (NEW_FID, OTHER_RID)]   # one record per repo_id
    assert led["by_id"][NEW_FID] == UNRELATED
    rec = led["by_id"][OLD_FID]
    assert rec["status"] == "rejected" and rec["review"]["evidence_rev"]
    assert rec["aliases"] == [{"id": NEW_FID, "repo": NEW_REPO}] and rec["history"] == [OLD_OWNER]
    assert led["by_repo_id"] == {SHARED_RID: OLD_FID, OTHER_RID: NEW_FID}
    assert led["by_repo"][NEW_REPO] == OLD_FID and led["by_repo"][OTHER_REPO] == NEW_FID


def test_reconcile_writes_a_renamed_raise_to_the_unprotected_repo_id_owner_not_a_colliding_id(tmp_path):
    path = _ledger(tmp_path, OLD_OWNER, UNRELATED)
    gh = _gh([_pr(1495, "OPEN", NOW - timedelta(hours=2), _body(_renamed()))])
    assert review_memory.reconcile(gh, path, NOW) == [OLD_FID]
    _assert_owner_took_it_and_unrelated_is_untouched(memory.load(path))
    before = path.read_text()
    assert review_memory.reconcile(gh, path, NOW + timedelta(hours=1)) == []   # idempotent
    assert path.read_text() == before


def test_record_review_decision_writes_to_the_unprotected_repo_id_owner_not_a_colliding_id(tmp_path):
    path = _ledger(tmp_path, OLD_OWNER, UNRELATED)
    memory.record_review_decision(NEW_FID, NEW_REPO, "needs_review_target: x", repo_id=SHARED_RID,
                                  evidence_rev="a", path=path, now=NOW)
    _assert_owner_took_it_and_unrelated_is_untouched(memory.load(path))


def test_an_id_colliding_with_another_repo_ids_record_is_never_overwritten_even_without_an_owner(tmp_path):
    path = _ledger(tmp_path, UNRELATED)
    before = path.read_text()
    memory.record_review_decision(NEW_FID, NEW_REPO, "needs_review_target: x", repo_id=SHARED_RID,
                                  evidence_rev="a", path=path, now=NOW)
    assert path.read_text() == before
    gh = _gh([_pr(1495, "OPEN", NOW - timedelta(hours=2), _body(_renamed()))])
    assert review_memory.reconcile(gh, path, NOW) == []
    assert path.read_text() == before
    assert memory.canonical_id(memory.load(path), NEW_FID, SHARED_RID) is None


def test_the_repo_id_owner_winning_never_repoints_a_name_off_a_legacy_veto(tmp_path):
    legacy_veto = {k: v for k, v in OLD_VETO.items() if k != "repo_id"} | {"id": NEW_FID, "repo": NEW_REPO}
    path = _ledger(tmp_path, OLD_OWNER, legacy_veto)
    gh = _gh([_pr(1495, "OPEN", NOW - timedelta(hours=2), _body(_renamed()))])
    assert review_memory.reconcile(gh, path, NOW) == [OLD_FID]
    memory.record_review_decision(NEW_FID, NEW_REPO, "needs_review_target: x", repo_id=SHARED_RID,
                                  evidence_rev="b", path=path, now=NOW + timedelta(hours=1))
    led, later = memory.load(path), NOW + timedelta(days=61)
    assert led["by_id"][NEW_FID] == legacy_veto
    assert memory.is_blocked(led, repo=NEW_REPO, now=later) and memory.is_blocked(led, firmware_id=NEW_FID, now=later)
