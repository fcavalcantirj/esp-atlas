"""A committed ledger id is bound to the held firmware.md's source repository (PR 1512, R2i).

The bot's own same-repo tick PR holds `oldtool`: its firmware.md (read at the pinned head) names source
repository n/oldtool, GitHub id 4242. A later editable commit rewrote the PR's jr/proposed_ledger.json
record to a PAIR — repo u/unrelated, repo_id 7777 — and GitHub truthfully answers u/unrelated with
7777. Checking the ledger against itself let the loader hold 7777, release renamed 4242 (n/newtool)
for a second firmware record and recipe, and hydration persist n/oldtool under id 7777. A ledger id
counts only when the firmware.md source at the same head is the ledger's repo and GitHub answers that
source with the same id; any mismatch is a gap the tick fails closed on.

Fake gh only (test_pending_prs's scripted one, test_tick_pending_identity's simulated GitHub); every
file under tmp_path. Run: cd jr && python3 -m pytest test_pending_prs_source.py -v
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

import pending_prs
import tick
from test_pending_prs import LEGACY_FILES, _closed, _gh, _load, _pr
from test_tick_pending_dedup import T0, _staged_for
from test_tick_pending_identity import (OLDTOOL, OTHER_ID, REPO_ID, RenameSim, _admit_first, _new_prs_holding,
                                        _rename_upstream, catalog, sim)  # noqa: F401 — fixtures
from test_tick import wt_dir  # noqa: F401 — a fixture

pytestmark = pytest.mark.usefixtures("esp_sketch_raw")   # the device-build gate passes (conftest)

LEDGER = "jr/proposed_ledger.json"
FIRMWARE_MD_READ = ("api", "-H", pending_prs.RAW_MEDIA, "repos/o/r/contents/data/firmware/oldtool/firmware.md?ref=oid1500")


def _ledger_naming(repo, repo_id):
    return json.dumps({"by_id": {"oldtool": {"id": "oldtool", "repo": repo, "status": "proposed", "repo_id": repo_id}},
                       "by_repo": {}})


def _index(vetoed, ledger, sources=None, calls=None):
    """load() over bot PR #1500 holding oldtool, whose firmware.md at oid1500 names n/oldtool."""
    pr = _pr(1500, LEGACY_FILES)
    gh = _gh([_closed(pr)] if vetoed else [], calls=calls, ledgers={"oid1500": ledger},
             repos={"n/oldtool": REPO_ID, "u/unrelated": OTHER_ID},
             sources={("oid1500", "oldtool"): "n/oldtool"} if sources is None else sources)
    return _load(gh, []) if vetoed else _load(gh, [pr])


def _source_gap(idx):
    assert not idx.complete, "a ledger id not bound to the held firmware's source left the index complete"
    assert any("#1500" in g and "oldtool" in g for g in idx.gaps), idx.gaps
    assert OTHER_ID not in idx.by_repo_id and idx.match("unrelated", OTHER_ID) is None
    assert idx.hold("oldtool").repo_id is None


# --- the loader ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_ledger_pair_substituted_away_from_the_firmware_source_is_a_gap(vetoed):
    _source_gap(_index(vetoed, _ledger_naming("u/unrelated", OTHER_ID)))


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_ledger_id_whose_firmware_source_cannot_be_read_at_the_head_is_a_gap(vetoed):
    idx = _index(vetoed, _ledger_naming("n/oldtool", REPO_ID), sources={})
    assert not idx.complete and any("#1500" in g and "oldtool" in g for g in idx.gaps), idx.gaps
    assert REPO_ID not in idx.by_repo_id


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_ledger_id_bound_to_the_firmware_source_at_the_head_is_held(vetoed):
    calls = []
    idx = _index(vetoed, _ledger_naming("n/oldtool", REPO_ID), calls=calls)
    assert idx.complete, idx.gaps
    assert idx.hold("oldtool").repo_id == REPO_ID and set(idx.by_repo_id) == {REPO_ID}
    assert idx.match("newtool", REPO_ID).firmware == "oldtool"
    assert FIRMWARE_MD_READ in calls                                              # read at the pinned head


# --- the tick and its hydration (simulated GitHub) ------------------------------------------------------

def _substitute_ledger_pair(pr):
    """A later commit on `pr` rewrote its ledger record for oldtool to another repository AND its id."""
    led = json.loads(pr["tree"][LEDGER])
    led["by_id"]["oldtool"].update(repo="u/unrelated", repo_id=OTHER_ID)
    pr["tree"][LEDGER] = json.dumps(led)


def _later_owners_of(sim, repo_id, after):
    """Firmware ids any ledger written after PR `after` records as `repo_id`: main's, the worktree's, newer PRs'."""
    texts = [p["tree"].get(LEDGER) for p in sim.prs if p["number"] > after] + [sim.main.get(LEDGER)]
    wt_ledger = sim.wt / LEDGER
    texts.append(wt_ledger.read_text() if wt_ledger.is_file() else None)
    return {fid for t in texts if t for fid, rec in json.loads(t)["by_id"].items() if rec.get("repo_id") == repo_id}


def _held_pr(sim, catalog, substituted, vetoed=False):
    pr = _admit_first(sim, catalog, OLDTOOL, "oldtool", REPO_ID)
    if substituted:
        _substitute_ledger_pair(pr)
    if vetoed:
        sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    sim.serve("u/unrelated", OTHER_ID)
    _rename_upstream(sim, catalog)                    # 4242 is now n/newtool; n/oldtool redirects to it
    return pr


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_substituted_ledger_pair_fails_the_tick_closed_and_4242_stays_protected(sim, catalog, vetoed):
    pr = _held_pr(sim, catalog, substituted=True, vetoed=vetoed)
    prs_before, main_before = len(sim.prs), dict(sim.main)
    r = sim.tick(T0 + timedelta(hours=3))
    assert _staged_for(r, "newtool") == [] and r.paths == [], r.paths          # no firmware, no recipe for 4242
    assert not _new_prs_holding(sim, "newtool", pr["number"])
    assert "incomplete" in (r.aborted or "") and f"#{pr['number']}" in r.aborted, r.aborted
    assert len(sim.prs) == prs_before and sim.main == main_before
    assert _later_owners_of(sim, OTHER_ID, pr["number"]) == set(), "unrelated 7777 was persisted"


def _hydrated_record(sim, tmp_path):
    """oldtool's record after hydrating a fresh ledger from the open PRs, with the index the loader built."""
    now = T0 + timedelta(hours=3)
    open_prs = json.loads(sim.gh("pr", "list", "--state", "open").stdout)
    pending = pending_prs.load(sim.gh, open_prs, now, slug="o/r", open_limit=500)
    ledger = tmp_path / "hydrated_ledger.json"
    ledger.write_text(json.dumps({"by_id": {}, "by_repo": {}}) + "\n")
    tick.hydrate_open_pr_ledger(sim.gh, now, ledger, repo_slug="o/r", pending=pending)
    return pending, json.loads(ledger.read_text())["by_id"]["oldtool"]


def test_hydration_never_persists_a_substituted_foreign_id(sim, catalog, tmp_path):
    _held_pr(sim, catalog, substituted=True)
    pending, rec = _hydrated_record(sim, tmp_path)
    assert rec["repo"] == "n/oldtool" and rec.get("repo_id") is None, rec      # never n/oldtool under 7777
    assert not pending.complete, pending.gaps


def test_hydration_persists_the_id_bound_to_the_firmware_source(sim, catalog, tmp_path):
    _held_pr(sim, catalog, substituted=False)
    pending, rec = _hydrated_record(sim, tmp_path)
    assert pending.complete, pending.gaps
    assert rec["repo"] == "n/oldtool" and rec["repo_id"] == REPO_ID, rec
