"""Sequential multi-tick regressions for the TOPICS stage: a repository admitted through GitHub's rename
redirect keeps its stable id (PR 1512, R2d — reviewer finding #988).

The topics search can still list a repository under its stale name `n/oldtool`; GitHub answers that
name with the renamed repository, canonical `n/newtool`, stable id 4242. The stage read that id under
the INPUT url but emitted the item (and its ledger record) under the canonical name, so the PR carried
neither the identity marker nor a ledger repo_id: the next tick, listing `n/newtool`, admitted the same
repository again, and closing the first PR vetoed nothing. The fetched id now follows the redirect into
the item, the PR's identity marker and the ledger committed at its head.

R2e (reviewer finding #999): the ALIGNED case — the search lists `n/newtool`, the very name GitHub
answers (no redirect) — must reach the same place: memory.record_proposed carries id 4242 into the
ledger committed at the PR head, so the repository renamed upstream to `n/renamedtool` is held by its
id while the PR is open and vetoed after it closes unmerged; distinct id 7777 is never caught.

Runs the REAL jr/tick.py (preflight index, ledger hydration, publish) with the real stage_admit_topics
(drain, scorer, writer, memory) over test_tick_pending_identity's simulated GitHub (fake gh/git only,
every file under tmp_path).

Run: cd jr && python3 -m pytest test_tick_topics_identity.py -v
"""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

import drain
import pending_prs
import source_topics
import stage_admit_topics
import tools
from test_tick_pending_dedup import T0, _staged_for
from test_tick_pending_identity import REPO_ID, OTHER_ID, RenameSim, _new_prs_holding, _owners_of
from test_tick import run, wt_dir  # noqa: F401 — wt_dir is a fixture

pytestmark = pytest.mark.usefixtures("esp_sketch_raw")   # the device-build gate passes (conftest)


def _topic(owner_repo, name):
    return {"name": name, "description": "A Cardputer tool", "source": "topic:cardputer",
            "github": f"https://github.com/{owner_repo}"}


STALE = _topic("n/oldtool", "Old Tool")             # the stale name GitHub still redirects
CANONICAL = _topic("n/newtool", "New Tool")         # the same repository, id 4242
UNRELATED = _topic("n/fmtcheck", "Fmt Check")       # another repository, id 7777


class TopicsSim(RenameSim):
    """RenameSim whose ticks run only the topics stage; its repository reads answer through the sim's
    GitHub, so an old name is served the renamed repository (same id), as GitHub's redirect does."""

    def fetch_meta(self, github_url):
        owner_repo = "/".join(github_url.removeprefix("https://github.com/").strip("/").split("/")[:2])
        p = self.gh("api", f"repos/{owner_repo}")
        if p.returncode != 0:
            return {"error": "404 not found"}
        d = json.loads(p.stdout)
        return {"full_name": d["full_name"], "description": d["description"], "license": "MIT", "topics": [],
                "homepage": None, "default_branch": d["default_branch"], "stars": d["stargazers_count"],
                "archived": False, "forks": d["forks_count"], "id": d["id"], "fork": False,
                "source_full_name": None, "parent_full_name": None, "pushed_at": d["pushed_at"],
                "language": "C", "readme_title": None, "readme_body": "", "has_library_manifest": False}

    def tick(self, now):
        self.now, self.snapshot = now, {}
        return run(git=self.git, gh=self.gh, now=now, stages=[lambda ctx: stage_admit_topics.run(ctx, budget=1)],
                   env={"JR_REPO_SLUG": "o/r"})


@pytest.fixture
def listing(monkeypatch):
    entries: list = []
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: list(entries))
    return entries


@pytest.fixture
def sim(wt_dir, listing, monkeypatch):
    s = TopicsSim(wt_dir)
    monkeypatch.setattr(drain, "default_fetch_meta", s.fetch_meta)
    monkeypatch.setattr(tools, "run_guard", lambda: {"ok": True, "output": ""})
    return s


def _admit_through_redirect(sim, listing):
    """Tick N: the search lists the stale name; GitHub redirects it to canonical n/newtool, id 4242."""
    listing[:] = [STALE]
    sim.serve("n/newtool", REPO_ID, "n/oldtool")
    r = sim.tick(T0)
    assert not r.aborted, r.aborted
    pr = sim.prs[-1]
    assert "data/firmware/oldtool/firmware.md" in pr["files"], pr["files"]
    return pr


def test_the_redirected_admission_records_the_stable_id_in_marker_and_committed_ledger(sim, listing):
    pr = _admit_through_redirect(sim, listing)
    assert pending_prs.identities(pr["body"]) == {"oldtool": (REPO_ID, "n/newtool")}, pr["body"]
    led = json.loads(pr["tree"]["jr/proposed_ledger.json"])
    assert led["by_id"]["oldtool"].get("repo_id") == REPO_ID, led["by_id"]["oldtool"]


def test_a_redirected_repository_held_by_an_open_pr_is_not_admitted_again(sim, listing):
    pr = _admit_through_redirect(sim, listing)
    listing[:] = [CANONICAL]
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "newtool") == [], "a second record for repository 4242"
    assert not _new_prs_holding(sim, "newtool", pr["number"])


def test_a_redirected_repository_stays_held_by_its_id_when_the_ledger_hydration_is_blind(sim, listing):
    pr = _admit_through_redirect(sim, listing)
    listing[:] = [CANONICAL]
    sim.view_rc = 1                                    # `gh pr view --json files` fails: nothing hydrated
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "newtool") == [], "a second record for repository 4242"
    assert not _new_prs_holding(sim, "newtool", pr["number"])
    assert r.rejects.get("already_proposed") == 1, r.rejects
    summary = next(s for s in r.stages if s["name"] == "admit_topics")["summary"]
    assert f"#{pr['number']}" in summary and str(REPO_ID) in summary, summary


def test_a_redirected_repository_vetoed_inside_the_ttl_is_not_admitted_again(sim, listing):
    pr = _admit_through_redirect(sim, listing)
    sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    listing[:] = [CANONICAL]
    for when in (T0 + timedelta(hours=3), T0 + timedelta(days=pending_prs.VETO_TTL_DAYS - 1)):
        r = sim.tick(when)
        assert not r.aborted, r.aborted
        assert _staged_for(r, "newtool") == [], when
        assert r.rejects.get("vetoed") == 1, (when, r.rejects)
    assert not _new_prs_holding(sim, "newtool", pr["number"])


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_an_unrelated_repository_is_neither_held_nor_vetoed(sim, listing, vetoed):
    pr = _admit_through_redirect(sim, listing)
    if vetoed:
        sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    listing[:] = [UNRELATED]
    sim.serve("n/fmtcheck", OTHER_ID)
    r = sim.tick(T0 + timedelta(hours=3))
    assert not r.aborted, r.aborted
    assert "data/firmware/fmtcheck/firmware.md" in r.paths, (r.paths, r.rejects)
    assert not {"already_proposed", "vetoed", "identity_ambiguous"} & set(r.rejects), r.rejects
    assert _new_prs_holding(sim, "fmtcheck", pr["number"])
    assert _owners_of(sim, OTHER_ID) <= {"fmtcheck"} and _owners_of(sim, REPO_ID) == {"oldtool"}


# R2e (reviewer finding #999): an ALIGNED admission — the search lists the repository under the very
# name GitHub answers (input url == canonical full_name, no redirect) — must carry its stable id into
# memory.record_proposed, the ledger committed at its PR head and the pending index just the same.

RENAMED = _topic("n/renamedtool", "Renamed Tool")   # n/newtool renamed upstream: the same id 4242


def _admit_aligned(sim, listing):
    """Tick N: the search lists n/newtool; GitHub answers that very name, id 4242 — no redirect."""
    listing[:] = [CANONICAL]
    sim.serve("n/newtool", REPO_ID)
    r = sim.tick(T0)
    assert not r.aborted, r.aborted
    pr = sim.prs[-1]
    assert "data/firmware/newtool/firmware.md" in pr["files"], pr["files"]
    return pr


def _rename_aligned_upstream(sim, listing):
    listing[:] = [RENAMED]
    sim.serve("n/renamedtool", REPO_ID, "n/newtool")


def test_an_aligned_admission_records_the_stable_id_in_the_ledger_committed_at_the_pr_head(sim, listing):
    pr = _admit_aligned(sim, listing)
    led = json.loads(pr["tree"]["jr/proposed_ledger.json"])
    assert led["by_id"]["newtool"].get("repo_id") == REPO_ID, led["by_id"]["newtool"]
    assert led["by_id"]["newtool"].get("status") == "proposed", led["by_id"]["newtool"]
    assert pending_prs.identities(pr["body"]) == {"newtool": (REPO_ID, "n/newtool")}, pr["body"]
    assert _owners_of(sim, REPO_ID) == {"newtool"}


def test_an_aligned_repository_renamed_upstream_is_held_by_its_id_while_its_pr_is_open(sim, listing):
    pr = _admit_aligned(sim, listing)
    _rename_aligned_upstream(sim, listing)
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, "renamedtool") == [], "a second record for repository 4242"
    assert not _new_prs_holding(sim, "renamedtool", pr["number"])
    assert r.rejects.get("already_proposed") == 1, r.rejects
    summary = next(s for s in r.stages if s["name"] == "admit_topics")["summary"]
    assert f"#{pr['number']}" in summary and str(REPO_ID) in summary, summary
    assert _owners_of(sim, REPO_ID) == {"newtool"}


def test_an_aligned_repository_renamed_upstream_is_vetoed_inside_the_ttl(sim, listing):
    pr = _admit_aligned(sim, listing)
    sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    _rename_aligned_upstream(sim, listing)
    for when in (T0 + timedelta(hours=3), T0 + timedelta(days=pending_prs.VETO_TTL_DAYS - 1)):
        r = sim.tick(when)
        assert not r.aborted, r.aborted
        assert _staged_for(r, "renamedtool") == [], when
        assert r.rejects.get("vetoed") == 1, (when, r.rejects)
    assert not _new_prs_holding(sim, "renamedtool", pr["number"])
    assert _owners_of(sim, REPO_ID) == {"newtool"}


@pytest.mark.parametrize("vetoed", [False, True], ids=["open", "vetoed"])
def test_a_distinct_id_is_neither_held_nor_vetoed_by_an_aligned_admission(sim, listing, vetoed):
    pr = _admit_aligned(sim, listing)
    if vetoed:
        sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    listing[:] = [UNRELATED]
    sim.serve("n/fmtcheck", OTHER_ID)
    r = sim.tick(T0 + timedelta(hours=3))
    assert not r.aborted, r.aborted
    assert "data/firmware/fmtcheck/firmware.md" in r.paths, (r.paths, r.rejects)
    assert not {"already_proposed", "vetoed", "identity_ambiguous"} & set(r.rejects), r.rejects
    assert _new_prs_holding(sim, "fmtcheck", pr["number"])
    led = json.loads(sim.prs[-1]["tree"]["jr/proposed_ledger.json"])
    assert led["by_id"]["fmtcheck"].get("repo_id") == OTHER_ID, led["by_id"]["fmtcheck"]
    assert _owners_of(sim, OTHER_ID) == {"fmtcheck"} and _owners_of(sim, REPO_ID) == {"newtool"}
