"""Sequential multi-tick regressions: a held firmware keeps its identity across an upstream rename.

Reviewers' reproduction (PR 1512, R2): GitHub repository id 4242 sits in an open tick PR (or a veto)
as `oldtool`; upstream renames it, the launcher now lists `n/newtool` — the SAME repository id. The
slug-only pending index never kept the id, so `newtool` was admitted again: a second firmware record
and recipe for one repository. The index now carries the stable numeric id each tick PR verified
(its body's identity marker), matches by id before slug, and fails closed when the id and the slug
disagree. Name similarity is never identity.

Runs the REAL jr/tick.py (preflight index, ledger hydration, publish) with the real stage_admit over
the simulated GitHub of test_tick_pending_dedup (fake gh/git only, every file under tmp_path). Only
admission runs: boardmap's holds are catalogued ids, which no rename moves (test_tick_pending_dedup).

Run: cd jr && python3 -m pytest test_tick_pending_identity.py -v
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

import pending_prs
import stage_admit
import tools
from test_tick_pending_dedup import NEW_META, T0, AtlasSim, _ours, _staged_for
from test_tick import Proc, run, wt_dir  # noqa: F401 — wt_dir is a fixture

pytestmark = pytest.mark.usefixtures("esp_sketch_raw")   # the device-build gate passes (conftest)

REPO_ID, OTHER_ID, UNRELATED_ID = 4242, 7777, 5151
SKETCH_TREE = {"tree": [{"path": "main.ino", "type": "blob"}, {"path": "sketch.yaml", "type": "blob"}]}


def _entry(owner_repo, name):
    return {"name": name, "description": "A Cardputer tool", "category": "cardputer",
            "github": f"https://github.com/{owner_repo}", "download": 100}


OLDTOOL = _entry("n/oldtool", "Old Tool")
NEWTOOL = _entry("n/newtool", "New Tool")                 # oldtool after the upstream rename
NEWTOOL_ELSEWHERE = _entry("m/newtool", "New Tool")       # another repository that slugs the same
FMTCHECK = _entry("n/fmtcheck", "Fmt Check")              # another repository, another name


class RenameSim(AtlasSim):
    """AtlasSim whose upstream repositories can be renamed: GitHub answers an old name with the
    renamed repository (same id), as its API redirects do."""

    def __init__(self, wt):
        super().__init__(wt)
        self.repos: dict = {}

    def serve(self, full_name, repo_id, *old_names):
        meta = {**NEW_META, "full_name": full_name, "id": repo_id}
        for name in (full_name, *old_names):
            self.repos[name] = meta

    def gh(self, *a):
        if a[:1] == ("api",) and a[1].startswith("repos/") and not a[1].startswith("repos/o/r"):
            parts = a[1].removeprefix("repos/").split("/")
            meta = self.repos.get("/".join(parts[:2]))
            if meta is None:
                return Proc(returncode=1, stderr="404 not found")
            if len(parts) == 2:
                return Proc(stdout=json.dumps(meta))
            if parts[2:4] == ["git", "trees"]:
                return Proc(stdout=json.dumps(SKETCH_TREE))
            return Proc(returncode=1, stderr="404 not found")
        return super().gh(*a)

    def tick(self, now):
        self.now, self.snapshot = now, {}
        return run(git=self.git, gh=self.gh, now=now, stages=[lambda ctx: stage_admit.run(ctx, budget=1)],
                   env={"JR_REPO_SLUG": "o/r"})


@pytest.fixture
def catalog(monkeypatch):
    entries: list = []
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: list(entries))
    return entries


@pytest.fixture
def sim(wt_dir, catalog):
    return RenameSim(wt_dir)


def _admit_first(sim, catalog, entry, fid, repo_id):
    catalog[:] = [entry]
    sim.serve(entry["github"].removeprefix("https://github.com/"), repo_id)
    r = sim.tick(T0)
    assert not r.aborted, r.aborted
    pr = sim.prs[-1]
    assert f"data/firmware/{fid}/firmware.md" in pr["files"], pr["files"]
    return pr


def _admit(r):
    return next(s for s in r.stages if s["name"] == "admit")


def _new_prs_holding(sim, fid, after):
    return [p for p in sim.prs if p["number"] > after and any(_ours(f, fid) for f in p["files"])]


def _rename_upstream(sim, catalog):
    catalog[:] = [NEWTOOL]
    sim.serve("n/newtool", REPO_ID, "n/oldtool")


# --- the same repository id under a new slug stays held ------------------------------------------------

def test_a_renamed_repository_held_by_an_open_pr_is_not_admitted_again(sim, catalog):
    pr = _admit_first(sim, catalog, OLDTOOL, "oldtool", REPO_ID)
    _rename_upstream(sim, catalog)
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "newtool") == [], "a second record for repository 4242"
    assert not _new_prs_holding(sim, "newtool", pr["number"])
    assert r.rejects.get("already_proposed") == 1, r.rejects
    summary = _admit(r)["summary"]
    assert f"#{pr['number']}" in summary and "oldtool" in summary and str(REPO_ID) in summary, summary


def test_a_renamed_repository_stays_held_when_the_ledger_hydration_is_blind(sim, catalog):
    _admit_first(sim, catalog, OLDTOOL, "oldtool", REPO_ID)
    _rename_upstream(sim, catalog)
    sim.view_rc = 1                                    # `gh pr view --json files` fails: nothing hydrated
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "newtool") == []
    assert r.rejects.get("already_proposed") == 1, r.rejects


def test_a_renamed_repository_vetoed_inside_the_ttl_is_not_admitted_again(sim, catalog):
    pr = _admit_first(sim, catalog, OLDTOOL, "oldtool", REPO_ID)
    sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    _rename_upstream(sim, catalog)
    for when in (T0 + timedelta(hours=3), T0 + timedelta(days=pending_prs.VETO_TTL_DAYS - 1)):
        r = sim.tick(when)
        assert not r.aborted, r.aborted
        assert _staged_for(r, "newtool") == [], when
        assert r.rejects.get("vetoed") == 1, (when, r.rejects)
    assert not _new_prs_holding(sim, "newtool", pr["number"])


# --- id and slug disagree: never admitted, never guessed ------------------------------------------------

@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_another_repository_with_a_held_slug_is_routed_fail_closed(sim, catalog, vetoed):
    pr = _admit_first(sim, catalog, NEWTOOL, "newtool", REPO_ID)
    if vetoed:
        sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    catalog[:] = [NEWTOOL_ELSEWHERE]
    sim.serve("m/newtool", OTHER_ID)
    r = sim.tick(T0 + timedelta(hours=3))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "newtool") == []
    assert not _new_prs_holding(sim, "newtool", pr["number"])
    assert r.rejects.get("identity_ambiguous") == 1, r.rejects
    assert not {"already_proposed", "vetoed"} & set(r.rejects), r.rejects   # not claimed as the held one
    summary = _admit(r)["summary"]
    assert str(OTHER_ID) in summary and str(REPO_ID) in summary and f"#{pr['number']}" in summary, summary


def test_a_held_slug_whose_id_the_pr_never_verified_still_holds(sim, catalog):
    pr = _admit_first(sim, catalog, NEWTOOL, "newtool", REPO_ID)
    pr["body"] = ""                                    # a PR older than the identity marker: id unknown
    catalog[:] = [NEWTOOL_ELSEWHERE]
    sim.serve("m/newtool", OTHER_ID)
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "newtool") == []
    assert r.rejects.get("already_proposed") == 1, r.rejects


def test_a_slug_collision_whose_candidate_id_cannot_be_read_still_holds(sim, catalog):
    _admit_first(sim, catalog, NEWTOOL, "newtool", REPO_ID)
    catalog[:] = [NEWTOOL_ELSEWHERE]                   # m/newtool: GitHub does not answer (no id)
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "newtool") == []
    assert r.rejects.get("already_proposed") == 1, r.rejects


# --- control: a different repository under a different name is admitted ---------------------------------

def test_another_repository_with_another_name_is_admitted_normally(sim, catalog):
    pr = _admit_first(sim, catalog, OLDTOOL, "oldtool", REPO_ID)
    catalog[:] = [OLDTOOL, FMTCHECK]
    sim.serve("n/fmtcheck", UNRELATED_ID)
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "oldtool") == []
    assert "data/firmware/fmtcheck/firmware.md" in r.paths, r.paths
    assert any(p.startswith("data/recipes/") and p.rstrip("/").endswith("__fmtcheck") for p in r.paths), r.paths
    assert _new_prs_holding(sim, "fmtcheck", pr["number"])
