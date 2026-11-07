"""Hydration never pairs a source read at a moved branch with an id verified at the pinned head (PR 1512, R2i).

pending_prs verifies repository id 4242 for `oldtool` from the ledger and firmware.md committed at the
open PR's pinned head (oid A: n/oldtool). hydrate_open_pr_ledger re-reads the firmware.md at the PR's
mutable branch name; when the branch advanced to B (its firmware.md now names u/unrelated) it persisted
repo u/unrelated with id 4242 — another repository's id. The id rides only with the source it was
verified for: a source read that names another repository records no id (unknown), never the old one.

Simulated GitHub only (test_tick_pending_identity's RenameSim); every file under tmp_path.
Run: cd jr && python3 -m pytest test_tick_hydration_head.py -v
"""
from __future__ import annotations

import base64
import json
from datetime import timedelta

import pytest

from test_pending_prs_source import LEDGER, _hydrated_record
from test_tick import Proc, wt_dir  # noqa: F401 — a fixture
from test_tick_pending_dedup import T0, _staged_for
from test_tick_pending_identity import OLDTOOL, REPO_ID, RenameSim, _admit_first, _rename_upstream, catalog  # noqa: F401

pytestmark = pytest.mark.usefixtures("esp_sketch_raw")   # the device-build gate passes (conftest)

FW = "data/firmware/oldtool/firmware.md"


class MovingHeadSim(RenameSim):
    """RenameSim whose PR branches can advance past the head the pending index pins: a read by branch
    name (`?ref=jr/tick-…`) answers the moved tree, a read at the pinned oid still answers the old one."""

    def gh(self, *a):
        if a[:1] == ("api",) and a[1].startswith("repos/o/r/contents/") and "?ref=jr/" in a[1]:
            path, ref = a[1].removeprefix("repos/o/r/contents/").split("?ref=")
            pr = next(p for p in self.prs if p["headRefName"] == ref)
            text = pr.get("moved", pr["tree"]).get(path)
            self.calls.append(a)
            return Proc(returncode=0 if text else 1, stdout=base64.b64encode(text.encode()).decode() if text else "")
        return super().gh(*a)


@pytest.fixture
def sim(wt_dir, catalog):
    return MovingHeadSim(wt_dir)


def _advance(pr, source):
    """A later commit on `pr`'s branch: its firmware.md for oldtool now names `source`."""
    pr["moved"] = {**pr["tree"], FW: pr["tree"][FW].replace("n/oldtool", source)}
    assert pr["moved"][FW] != pr["tree"][FW] or source == "n/oldtool"


def _held(sim, catalog, moved_to=None):
    pr = _admit_first(sim, catalog, OLDTOOL, "oldtool", REPO_ID)
    assert "n/oldtool" in pr["tree"][FW]
    if moved_to:
        _advance(pr, moved_to)
    _rename_upstream(sim, catalog)                    # 4242 is now n/newtool; n/oldtool redirects to it
    return pr


def _mixed(records):
    """Records pairing a source with an id verified for another one (4242 belongs to n/oldtool only)."""
    return {fid: r for fid, r in records.items()
            if r.get("repo_id") == REPO_ID and r.get("repo") not in ("n/oldtool", "n/newtool")}


# --- hydrate_open_pr_ledger directly ---------------------------------------------------------------------

def test_hydration_after_the_head_moved_to_another_source_records_no_id(sim, catalog, tmp_path):
    _held(sim, catalog, moved_to="u/unrelated")
    pending, rec = _hydrated_record(sim, tmp_path)
    assert pending.complete and pending.hold("oldtool").repo_id == REPO_ID, pending.gaps
    assert rec["repo"] == "u/unrelated" and rec.get("repo_id") is None, rec   # never u/unrelated under 4242


def test_hydration_after_the_head_moved_within_the_same_source_keeps_the_verified_id(sim, catalog, tmp_path):
    _held(sim, catalog, moved_to="n/oldtool")
    _, rec = _hydrated_record(sim, tmp_path)
    assert rec["repo"] == "n/oldtool" and rec["repo_id"] == REPO_ID, rec


def test_hydration_on_a_stable_head_records_the_verified_id(sim, catalog, tmp_path):
    _held(sim, catalog)
    _, rec = _hydrated_record(sim, tmp_path)
    assert rec["repo"] == "n/oldtool" and rec["repo_id"] == REPO_ID, rec


def test_hydration_whose_branch_read_fails_records_the_verified_pair_not_the_id_alone(sim, catalog, tmp_path):
    pr = _held(sim, catalog)
    pr["moved"] = {k: v for k, v in pr["tree"].items() if k != FW}
    _, rec = _hydrated_record(sim, tmp_path)
    assert rec["repo"] == "n/oldtool" and rec["repo_id"] == REPO_ID, rec   # the tuple pending_prs verified


# --- the real tick ---------------------------------------------------------------------------------------

def _tick_ledger(sim):
    r = sim.tick(T0 + timedelta(hours=3))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "newtool") == [], r.paths                          # 4242 stays held by #1500
    return json.loads((sim.wt / LEDGER).read_text())


def test_a_tick_whose_held_pr_head_moved_to_another_source_persists_no_mixed_pair(sim, catalog):
    _held(sim, catalog, moved_to="u/unrelated")
    led = _tick_ledger(sim)
    assert _mixed(led["by_id"]) == {}, led["by_id"]
    assert led["by_id"]["oldtool"]["repo"] == "u/unrelated" and led["by_id"]["oldtool"].get("repo_id") is None


def test_a_tick_whose_held_pr_head_is_stable_persists_the_verified_id(sim, catalog):
    _held(sim, catalog)
    led = _tick_ledger(sim)
    assert led["by_id"]["oldtool"]["repo"] == "n/oldtool" and led["by_id"]["oldtool"]["repo_id"] == REPO_ID
    assert _mixed(led["by_id"]) == {}
