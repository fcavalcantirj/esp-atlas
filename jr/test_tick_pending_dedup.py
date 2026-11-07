"""Sequential multi-tick regressions: what an OPEN (or vetoed) Jr tick PR holds is never staged again.

The incident (main ce0f72af): jr-review tick PRs #1500 #1501 #1503 #1506 #1508 #1511 each re-added
the SAME nightdriverstrip recipes + signals (and squachwatch-cyd's). Those firmware are already
catalogued, so their ledger record is `merged`; the open-PR hydration's `proposed` write is refused
over a merged record, and the boardmap's "already proposed" skip never fired — every hourly tick
re-derived the firmware into another review PR. The source of truth for "pending" is now the PR's
own changed-file list (jr/pending_prs.py), not a ledger status.

A small simulated GitHub keeps origin/main's files (data + ledger) and the PRs (state, labels, the
files each changed and their content) across ticks. Each tick runs the REAL jr/tick.py with the real
jr/stage_admit.py and jr/stage_boardmap.py from a fresh "worktree" written from main. Fake gh/git
only; every file under tmp_path.

Run: cd jr && python3 -m pytest test_tick_pending_dedup.py -v
"""
from __future__ import annotations

import base64
import json
import shutil
from datetime import datetime, timedelta, timezone

import pytest

import pending_prs
import review_routing
import stage_admit
import stage_boardmap
import tools
from test_stage_boardmap import FW as MARAUDER_FW, fake_api, fake_raw
from test_tick import REAL_REPO, Proc, gh_ok, run, wt_dir  # noqa: F401 — wt_dir is a fixture

pytestmark = pytest.mark.usefixtures("esp_sketch_raw")   # the device-build gate passes (conftest)

T0 = datetime(2026, 11, 7, 3, 0, tzinfo=timezone.utc)
NEW, NEW_REPO = "newtool", "n/newtool"              # admitted by tick N; lives only in the PR branch
CAT = "marauder"                                    # catalogued on main; tick N widens it with recipes
LAUNCHER = [{"name": "My Cardputer Tool", "description": "A Cardputer tool", "category": "cardputer",
             "github": f"https://github.com/{NEW_REPO}", "download": 100}]
NEW_META = {"full_name": NEW_REPO, "description": "A Cardputer tool", "license": {"spdx_id": "MIT"},
            "topics": [], "homepage": None, "default_branch": "main", "stargazers_count": 30,
            "archived": False, "forks_count": 2, "id": 4242, "fork": False, "source": None,
            "parent": None, "pushed_at": "2026-09-01T00:00:00Z", "language": "C"}
NEW_TREE = {"tree": [{"path": "newtool.ino", "type": "blob"}, {"path": "sketch.yaml", "type": "blob"}]}


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


def _ours(path, fid):
    return path.startswith(f"data/firmware/{fid}/") or (path.startswith("data/recipes/") and f"__{fid}/" in path)


class AtlasSim:
    """origin/main's files + the PRs, shared across ticks. `gh` / `git` are the tick's fakes."""

    def __init__(self, wt):
        self.wt, self.prs, self.n, self.now = wt, [], 1499, T0
        self.main = {f"data/firmware/{CAT}/firmware.md": MARAUDER_FW,
                     "jr/proposed_ledger.json": json.dumps({"by_id": {}, "by_repo": {}}) + "\n"}
        self.base, self.calls, self.staged, self.snapshot = gh_ok(), [], [], {}
        self.view_rc = 0                       # `gh pr view --json files` (the ledger hydration's read)

    # -- GitHub -----------------------------------------------------------------------------------
    def _listed(self, pr):
        return {k: pr[k] for k in ("number", "state", "headRefName", "createdAt", "closedAt", "mergedAt",
                                   "mergeable", "labels", "body")} | {"files": [{"path": p} for p in pr["files"]]}

    def gh(self, *a):
        self.calls.append(a)
        if a[:2] == ("api", "rate_limit"):
            return Proc(stdout="4999\n")
        if a[:4] == ("pr", "list", "--state", "open"):
            return Proc(stdout=json.dumps([self._listed(p) for p in self.prs if p["state"] == "OPEN"]))
        if a[:4] == ("pr", "list", "--state", "closed"):     # the sim ignores --search: the code must filter too
            return Proc(stdout=json.dumps([self._listed(p) for p in self.prs if p["state"] != "OPEN"]))
        if a[:4] == ("pr", "list", "--state", "all") and "--label" in a:
            return Proc(stdout=json.dumps([self._listed(p) for p in self.prs if review_routing.has_review_label(p)]))
        if a[:2] == ("pr", "view") and a[3:] == ("--json", "files"):
            pr = self._pr(a[2])
            return Proc(returncode=self.view_rc, stdout=json.dumps({"files": [{"path": p} for p in pr["files"]]}))
        if a[:2] == ("pr", "view") and a[3:] == ("--json", "state,mergedAt"):
            pr = self._pr(a[2])
            return Proc(stdout=json.dumps({"state": pr["state"], "mergedAt": pr["mergedAt"]}))
        if a[:1] == ("api",) and a[1].startswith("repos/o/r/contents/"):
            path, ref = a[1].removeprefix("repos/o/r/contents/").split("?ref=")
            pr = next(p for p in self.prs if p["headRefName"] == ref)
            text = pr["tree"].get(path)
            return Proc(returncode=0 if text else 1, stdout=base64.b64encode(text.encode()).decode() if text else "")
        if a[:2] == ("api", f"repos/{NEW_REPO}"):
            return Proc(stdout=json.dumps(NEW_META))
        if a[:2] == ("api", f"repos/{NEW_REPO}/git/trees/main?recursive=1"):
            return Proc(stdout=json.dumps(NEW_TREE))
        if a[:1] == ("api",) and a[1].startswith("repos/") and not a[1].startswith("repos/o/r"):
            return Proc(returncode=1, stderr="404 not found")
        if a[:2] == ("pr", "create"):
            self.n += 1
            self.prs.append({"number": self.n, "state": "OPEN", "createdAt": _iso(self.now), "closedAt": None,
                             "mergedAt": None, "headRefName": a[a.index("--head") + 1], "mergeable": "MERGEABLE",
                             "labels": [], "body": a[a.index("--body") + 1], "files": sorted(self.snapshot),
                             "tree": dict(self.snapshot)})
            return Proc(stdout=f"https://github.com/o/r/pull/{self.n}\n")
        if a[:2] == ("pr", "edit") and "--add-label" in a:
            self._pr(a[2])["labels"].append({"name": a[a.index("--add-label") + 1]})
            return Proc()
        if a[:2] == ("pr", "merge"):
            self.owner_merges(self._pr(a[2])["number"])
            return Proc()
        return self.base(*a)

    def _pr(self, ref):
        return next(p for p in self.prs if p["number"] == int(str(ref).rstrip("/").split("/")[-1].lstrip("#")))

    # -- git: a fresh worktree from main, the staged diff, the commit ------------------------------
    def _changed(self):
        return {p: (self.wt / p).read_text() for p in self.staged
                if (self.wt / p).is_file() and self.main.get(p) != (self.wt / p).read_text()}

    def git(self, *a):
        norm = a[2:] if a[:1] == ("-C",) else a
        if norm[:2] == ("worktree", "add"):
            shutil.rmtree(self.wt, ignore_errors=True)
            for sub in ("boards", "modules"):                              # read-only copies the stages resolve against
                shutil.copytree(REAL_REPO / "data" / sub, self.wt / "data" / sub)
            (self.wt / "data" / "recipes").mkdir(parents=True)
            for path, text in self.main.items():
                (self.wt / path).parent.mkdir(parents=True, exist_ok=True)
                (self.wt / path).write_text(text)
            return Proc()
        if norm[:3] == ("remote", "get-url", "origin"):
            return Proc(stdout="https://github.com/o/r.git\n")
        if norm[:1] == ("rev-parse",):
            return Proc(stdout="6190d21abc\n")
        if norm[:2] == ("add", "--"):
            self.staged = []
            for spec in norm[2:]:
                full = self.wt / spec
                files = sorted(f for f in full.rglob("*") if f.is_file()) if full.is_dir() else [full]
                self.staged += [str(f.relative_to(self.wt)) for f in files]
            return Proc()
        if norm[:3] == ("diff", "--cached", "--quiet"):
            return Proc(returncode=1 if self._changed() else 0)
        if norm[:3] == ("diff", "--cached", "--name-status"):
            return Proc(stdout="".join(f"{'M' if p in self.main else 'A'}\0{p}\0" for p in self._changed()))
        if norm[:1] == ("commit",):
            self.snapshot = self._changed()
        return Proc()

    # -- one tick + the owner ---------------------------------------------------------------------
    def tick(self, now):
        self.now, self.snapshot = now, {}
        stages = [lambda ctx: stage_admit.run(ctx, budget=1),
                  lambda ctx: stage_boardmap.run(ctx, budget=2, api=fake_api, raw=fake_raw)]
        return run(git=self.git, gh=self.gh, now=now, stages=stages, env={"JR_REPO_SLUG": "o/r"})

    def owner_closes(self, number, when):
        self._pr(number).update(state="CLOSED", closedAt=_iso(when))

    def owner_merges(self, number):
        pr = self._pr(number)
        pr.update(state="MERGED", mergedAt=_iso(self.now), closedAt=_iso(self.now))
        self.main.update(pr["tree"])

    def owner_keeps_only(self, number, keep):
        """The owner trims the PR (drops files) — what stays is what the PR now proposes."""
        pr = self._pr(number)
        pr["files"] = [p for p in pr["files"] if keep(p)]
        pr["tree"] = {p: t for p, t in pr["tree"].items() if keep(p)}

    def ledger(self):
        return json.loads(self.main["jr/proposed_ledger.json"])["by_id"]


def _staged_for(r, fid):
    """The data paths a tick staged for firmware `fid` (recipes are written as directories)."""
    return [p for p in r.paths if _ours(p.rstrip("/") + "/", fid) or _ours(p, fid)]


@pytest.fixture
def sim(wt_dir, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: list(LAUNCHER))
    return AtlasSim(wt_dir)


def _first_tick(sim):
    r = sim.tick(T0)
    assert not r.aborted, r.aborted
    pr = sim.prs[-1]
    assert review_routing.has_review_label(pr) and pr["state"] == "OPEN"     # a new firmware routes REVIEW
    assert f"data/firmware/{NEW}/firmware.md" in pr["files"]
    assert any(_ours(p, NEW) and p.startswith("data/recipes/") for p in pr["files"])
    assert any(_ours(p, CAT) and p.startswith("data/recipes/") for p in pr["files"])
    assert NEW not in sim.ledger()                                           # the proposal is NOT on main
    return pr


# --- the incident: an open PR's firmware and recipes are not staged again ---------------------------

def test_tick_n_plus_1_stages_nothing_an_open_pr_already_holds(sim):
    pr = _first_tick(sim)
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, NEW) == [] and _staged_for(r, CAT) == []
    assert len([p for p in sim.prs if p["state"] == "OPEN"]) == 1, "a second PR re-proposed the same records"
    boardmap = next(s for s in r.stages if s["name"] == "boardmap")
    assert f"#{pr['number']}" in boardmap["summary"]                        # the skip names the PR that holds it


def test_the_pr_file_list_is_the_source_of_truth_even_when_the_ledger_hydration_is_blind(sim):
    _first_tick(sim)
    sim.view_rc = 1                                     # `gh pr view --json files` fails: no hydrated record
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, NEW) == [] and _staged_for(r, CAT) == []


def test_no_recipe_for_a_pending_firmware_is_stacked_on_a_new_board(sim):
    pr = _first_tick(sim)
    kept = next(p for p in pr["files"] if _ours(p, CAT) and p.startswith("data/recipes/"))
    sim.owner_keeps_only(pr["number"], lambda p: not (_ours(p, CAT) and p.startswith("data/recipes/")) or p == kept)
    r = sim.tick(T0 + timedelta(hours=1))           # the other boards are NEW relative to what the PR holds
    assert not r.aborted, r.aborted
    assert _staged_for(r, CAT) == []


def test_a_merged_pr_counts_as_catalogued(sim):
    pr = _first_tick(sim)
    sim.now = T0 + timedelta(minutes=30)
    sim.owner_merges(pr["number"])
    r = sim.tick(T0 + timedelta(hours=1))
    assert not r.aborted, r.aborted
    assert sim.ledger()[NEW]["status"] == "merged"                          # reconciled and landed on main
    assert not any(p == f"data/firmware/{NEW}/firmware.md" for p in r.paths)
    assert _staged_for(r, CAT) == []                                         # freshly mapped: not re-picked
    assert not {"already_proposed", "vetoed"} & set(r.rejects)                # nothing is HELD by the merged PR
    later = sim.tick(T0 + timedelta(days=stage_boardmap.FRESH_DAYS + 1))      # signals stale again
    boardmap = next(s for s in later.stages if s["name"] == "boardmap")
    assert f"{CAT}: +" in boardmap["summary"] and "skip" not in boardmap["summary"], boardmap["summary"]


# --- a veto (closed unmerged) holds for the veto TTL ----------------------------------------------------

def test_a_vetoed_pr_is_not_re_proposed_within_the_veto_ttl(sim):
    pr = _first_tick(sim)
    sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    for when in (T0 + timedelta(hours=3), T0 + timedelta(days=pending_prs.VETO_TTL_DAYS - 1)):
        r = sim.tick(when)
        assert not r.aborted, r.aborted
        assert _staged_for(r, NEW) == [] and _staged_for(r, CAT) == [], when
    assert not [p for p in sim.prs if p["state"] == "OPEN" and any(_ours(f, NEW) or _ours(f, CAT) for f in p["files"])]


def test_the_veto_lapses_after_its_ttl(sim):
    pr = _first_tick(sim)
    sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    r = sim.tick(T0 + timedelta(days=pending_prs.VETO_TTL_DAYS + 1))
    assert not r.aborted, r.aborted
    assert _staged_for(r, CAT)                                               # reconsidered once the TTL ran out


def test_a_tick_blind_to_closed_prs_fails_closed_and_opens_nothing(sim):
    _first_tick(sim)
    real = sim.gh

    def blind(*a):
        if a[:4] == ("pr", "list", "--state", "closed"):
            return Proc(returncode=1, stderr="HTTP 502")
        return real(*a)
    sim.gh = blind
    r = sim.tick(T0 + timedelta(hours=1))
    assert "cannot see which firmware a Jr PR holds" in r.aborted
    assert len(sim.prs) == 1 and r.paths == []


def test_a_closed_pr_list_cut_at_its_limit_warns(sim, monkeypatch):
    pr = _first_tick(sim)
    sim.owner_closes(pr["number"], T0 + timedelta(hours=2))
    monkeypatch.setattr(pending_prs, "CLOSED_PR_LIMIT", 1)
    r = sim.tick(T0 + timedelta(hours=3))
    assert not r.aborted, r.aborted
    assert any("closed Jr PRs cut at 1" in w for w in r.warnings), r.warnings
