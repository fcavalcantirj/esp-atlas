"""Sequential multi-tick regressions for the repeat jr-review bug (SPEC-jr-review-routing.md §5).

Every hourly tick re-opened a bookkeeping-only jr-review PR for gdantas04/cardputer-system-monitor
(#1478 … #1488, #1490): the needs_review decision only ever lived in the unmerged review PR's
ledger, so main never learnt it. Here a small simulated GitHub keeps PRs (number, state, labels,
body) and main's ledger across ticks; a review PR waits for the owner, an AUTO PR merges and lands
its committed ledger on main. Each tick runs the REAL jr/tick.py + jr/stage_admit.py from a fresh
"worktree" written from main — so a new GitHubSim over the same state is a restart. Fake gh/git
only; every file under tmp_path.

Run: cd jr && python3 -m pytest test_tick_review_dedup.py -v
"""
from __future__ import annotations

import copy
import json
import shutil
from datetime import datetime, timedelta, timezone

import memory
import review_routing
import stage_admit
import tools
from test_stage_admit import _entry, _meta
from test_stage_admit_device_gate import RELEASES, TREE, _raw, _tree
from test_tick import REAL_REPO, Proc, checkout, gh_ok, run, wt_dir  # noqa: F401 — checkout/wt_dir are fixtures

T0 = datetime(2026, 11, 6, 15, 0, tzinfo=timezone.utc)
FID, REPO, RID = "cardputer-system-monitor", "gdantas04/cardputer-system-monitor", 831377003
SIGNALS = "data/firmware/acid-drop/signals.json"
MAIN_EXPIRED = {"expired_at": "2026-11-05T19:01:17.341039+00:00", "expires": "2026-11-05T19:00:58.979878+00:00",
                "id": FID, "pr_ref": None, "reason": "below_floor: 24 stars / 2 forks", "repo": REPO,
                "repo_id": RID, "status": "expired", "timestamp": "2026-10-06T19:00:58.979878+00:00"}
LEGACY_BODY = ("### Needs owner review — no ESP target stated (not admitted)\n"
               f"- `{REPO}` (`{FID}`) — arduino_sketch https://github.com/{REPO}/blob/main/serial_receiver.ino: "
               "a .ino but no ESP board named\nRe-checked after the reject TTL; admit by hand if it does target an ESP.\n")


def _iso(dt):
    return dt.isoformat().replace("+00:00", "Z")


class GitHubSim:
    """origin/main's ledger + the PRs, shared across ticks. `gh` / `git` are the tick's fakes."""

    def __init__(self, wt, main_ledger, stars=30, pushed="2026-10-01T00:00:00Z"):
        self.wt, self.main, self.prs, self.n = wt, main_ledger, [], 1480
        self.stars, self.pushed, self.list_rc = stars, pushed, 0
        self.base, self.calls, self.committed = gh_ok(), [], None

    # -- GitHub -----------------------------------------------------------------------------------
    def _metas(self):
        meta = _meta(REPO, stars=self.stars, forks=2, rid=RID, description="M5Stack Cardputer system monitor")
        meta["pushed_at"] = self.pushed
        return {f"repos/{REPO}": meta, TREE.format(REPO): _tree("README.md", "serial_receiver.ino"),
                RELEASES.format(REPO): [], "repos/t/tiny": _meta("t/tiny", stars=1, rid=77)}

    def open_prs(self):
        """As `gh pr list --json …,files,changedFiles` lists them."""
        return [{**p, "files": [{"path": f} for f in p["files"]], "changedFiles": len(p["files"])}
                for p in self.prs if p["state"] == "OPEN"]

    def review_prs(self):
        return [p for p in self.prs if review_routing.has_review_label(p)]

    def gh(self, *a):
        self.calls.append(a)
        if a[:2] == ("api", "rate_limit"):
            return Proc(stdout="4999\n")
        if a[:4] == ("pr", "list", "--state", "open"):
            return Proc(stdout=json.dumps(self.open_prs()))
        if a[:4] == ("pr", "list", "--state", "all"):
            return Proc(returncode=self.list_rc, stdout=json.dumps(self.review_prs()) if self.list_rc == 0 else "")
        if a[:2] == ("pr", "view") and a[3:] == ("--json", "files"):
            pr = next(p for p in self.prs if p["number"] == int(a[2]))
            return Proc(stdout=json.dumps({"files": [{"path": f} for f in pr["files"]]}))
        if a[:2] == ("pr", "create"):
            self.n += 1
            self.prs.append({"number": self.n, "state": "OPEN", "createdAt": _iso(self.now), "mergedAt": None,
                             "headRefName": a[a.index("--head") + 1], "mergeable": "MERGEABLE", "labels": [],
                             "body": a[a.index("--body") + 1], "files": list(self.staged), "ledger": self.committed})
            return Proc(stdout=f"https://github.com/o/r/pull/{self.n}\n")
        if a[:2] == ("pr", "edit") and "--add-label" in a:
            self._pr(a[2])["labels"].append({"name": a[a.index("--add-label") + 1]})
            return Proc()
        if a[:2] == ("pr", "merge"):
            pr = self._pr(a[2])
            pr.update(state="MERGED", mergedAt=_iso(self.now))
            self.main = json.loads(pr["ledger"])
            return Proc()
        if a[:1] == ("api",) and a[1] in self._metas():
            return Proc(stdout=json.dumps(self._metas()[a[1]]))
        if a[:1] == ("api",) and a[1].startswith("repos/") and "/o/r" not in f"/{a[1]}":
            return Proc(returncode=1, stderr="404 not found")
        return self.base(*a)

    def _pr(self, url):
        return next(p for p in self.prs if p["number"] == int(str(url).rstrip("/").split("/")[-1]))

    # -- git: a fresh worktree from main, the staged diff, the commit ------------------------------
    def git(self, *a):
        norm = a[2:] if a[:1] == ("-C",) else a
        if norm[:2] == ("worktree", "add"):
            shutil.rmtree(self.wt, ignore_errors=True)
            (self.wt / "jr").mkdir(parents=True)
            (self.wt / "data" / "firmware").mkdir(parents=True)
            for sub in ("boards", "modules"):                              # read-only copies: the scorer reads boards
                shutil.copytree(REAL_REPO / "data" / sub, self.wt / "data" / sub)
            (self.wt / "jr" / "proposed_ledger.json").write_text(json.dumps(self.main, indent=2, sort_keys=True) + "\n")
            return Proc()
        if norm[:3] == ("remote", "get-url", "origin"):
            return Proc(stdout="https://github.com/o/r.git\n")
        if norm[:1] == ("rev-parse",):                                     # incl. publish's `--verify …^{commit}`
            return Proc(stdout="6190d21abc\n")
        if norm[:3] == ("diff", "--cached", "--quiet"):
            return Proc(returncode=1)
        if norm[:3] == ("diff", "--cached", "--name-status"):
            return Proc(stdout="".join(f"M\0{p}\0" for p in self.staged))
        if norm[:1] == ("commit",):
            self.committed = (self.wt / "jr" / "proposed_ledger.json").read_text()
        return Proc()

    # -- one tick -------------------------------------------------------------------------------------
    def tick(self, now, signals=True):
        self.now = now
        self.staged = ["jr/proposed_ledger.json"] + ([SIGNALS] if signals else [])
        stages = [lambda ctx: stage_admit.run(ctx, budget=3, raw=_raw({}))]
        if signals:
            stages.append(lambda ctx: _signals_stage(ctx))
        return run(git=self.git, gh=self.gh, now=now, stages=stages)

    def owner_closes(self, number):
        next(p for p in self.prs if p["number"] == number)["state"] = "CLOSED"

    def main_rec(self, fid=FID):
        return self.main["by_id"].get(fid)

    def device_calls(self):
        return [c for c in self.calls if c[:2] == ("api", TREE.format(REPO))]


def _signals_stage(ctx):
    import tick
    return tick.StageResult("boardmap", paths=[SIGNALS], summary="acid-drop: +0 recipe(s), 3 signals")


def _launcher(monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("Cardputer System Monitor", f"https://github.com/{REPO}"),
        _entry("Tiny", "https://github.com/t/tiny")])                    # unrelated: a floor reject (bookkeeping)


def _sim(wt_dir, monkeypatch, main=None, **kw):
    _launcher(monkeypatch)
    led = main or {"by_id": {FID: copy.deepcopy(MAIN_EXPIRED)}, "by_repo": {REPO: FID}}
    return GitHubSim(wt_dir, led, **kw)


def _routes(*reports):
    return [(r.publish or {}).get("route") for r in reports]


# --- the incident: an OPEN review PR is never re-asked ---------------------------------------------

def test_an_open_review_pr_is_asked_once_and_the_decision_lands_on_main_via_bookkeeping(wt_dir, monkeypatch):
    gh = _sim(wt_dir, monkeypatch)
    r1 = gh.tick(T0)
    assert r1.publish["route"] == "review" and [p["number"] for p in gh.review_prs()] == [1481]
    assert gh.main_rec() == MAIN_EXPIRED                                   # the review PR did not merge
    r2 = gh.tick(T0 + timedelta(hours=1))
    r3 = gh.tick(T0 + timedelta(hours=2))
    assert not (r2.aborted or r3.aborted) and _routes(r2, r3) == ["auto", "auto"]
    assert [p["number"] for p in gh.review_prs()] == [1481]               # no second equivalent review PR
    assert all(p["state"] == "MERGED" for p in gh.prs if p["number"] > 1481)
    rec = gh.main_rec()
    assert rec["status"] == "rejected" and rec["repo_id"] == RID and rec["reason"].startswith("needs_review_target:")
    assert rec["review"]["outcome"] == "open" and rec["review"]["pr_ref"] == "#1481"
    assert rec["history"][0] == MAIN_EXPIRED                               # appended, never deleted
    # unrelated bookkeeping in the same ticks shipped on the AUTO path, not onto review
    assert gh.main_rec("tiny")["reason"].startswith("below_floor") and SIGNALS in gh.prs[-1]["files"]


def test_a_restart_reads_the_same_decision_from_github_and_main(wt_dir, monkeypatch):
    gh = _sim(wt_dir, monkeypatch)
    gh.tick(T0)
    restarted = GitHubSim(wt_dir, gh.main)                                 # a new process: only GitHub + main survive
    restarted.prs, restarted.n = gh.prs, gh.n
    r = restarted.tick(T0 + timedelta(hours=1))
    assert r.publish["route"] == "auto" and len(restarted.review_prs()) == 1


def test_an_unchanged_decision_on_main_is_quiet_no_rewrite_no_rebuild_evidence(wt_dir, monkeypatch):
    gh = _sim(wt_dir, monkeypatch)
    gh.tick(T0)
    gh.tick(T0 + timedelta(hours=1))
    settled = copy.deepcopy(gh.main_rec())
    gh.calls.clear()
    r = gh.tick(T0 + timedelta(hours=2))
    assert r.publish["route"] == "auto" and gh.main_rec() == settled and gh.device_calls() == []


# --- closed unmerged ----------------------------------------------------------------------------

def test_a_review_pr_closed_unmerged_keeps_the_decision_and_is_not_reasked(wt_dir, monkeypatch):
    gh = _sim(wt_dir, monkeypatch)
    gh.tick(T0)
    gh.owner_closes(1481)
    r2 = gh.tick(T0 + timedelta(hours=1))
    r3 = gh.tick(T0 + timedelta(hours=2))
    assert _routes(r2, r3) == ["auto", "auto"] and len(gh.review_prs()) == 1
    assert gh.main_rec()["review"]["outcome"] == "closed" and gh.main_rec()["status"] == "rejected"


def test_the_incident_legacy_open_review_prs_without_a_marker_stop_the_repeat(wt_dir, monkeypatch):
    gh = _sim(wt_dir, monkeypatch)
    for n, h in ((1488, -1), (1490, 0)):
        gh.prs.append({"number": n, "state": "OPEN", "createdAt": _iso(T0 + timedelta(hours=h)), "mergedAt": None,
                       "headRefName": f"jr/tick-20261106-{15 + h}00", "mergeable": "MERGEABLE",
                       "labels": [{"name": "jr-review"}], "body": LEGACY_BODY, "files": [SIGNALS], "ledger": None})
    gh.n = 1490
    r = gh.tick(T0 + timedelta(hours=1))
    assert r.publish["route"] == "auto" and len(gh.review_prs()) == 2
    assert gh.main_rec()["review"]["pr_ref"] == "#1490" and gh.main_rec()["review"]["evidence_rev"]   # backfilled


# --- what IS reconsidered ---------------------------------------------------------------------------

def test_an_expired_decision_is_reconsidered_and_asked_again(wt_dir, monkeypatch):
    gh = _sim(wt_dir, monkeypatch)
    gh.tick(T0)
    gh.owner_closes(1481)
    gh.tick(T0 + timedelta(hours=1))
    later = T0 + timedelta(days=memory.NO_BUILD_SIGNAL_DAYS, hours=2)
    r = gh.tick(later)
    assert r.publish["route"] == "review" and len(gh.review_prs()) == 2
    nxt = gh.tick(later + timedelta(hours=1))                             # …and then held again
    assert nxt.publish["route"] == "auto" and len(gh.review_prs()) == 2


def test_meaningful_new_evidence_is_reconsidered_once_a_star_is_not(wt_dir, monkeypatch):
    gh = _sim(wt_dir, monkeypatch)
    gh.tick(T0)
    gh.tick(T0 + timedelta(hours=1))
    gh.stars = 31                                                          # not news
    assert gh.tick(T0 + timedelta(hours=2)).publish["route"] == "auto"
    gh.pushed = "2026-11-06T16:30:00Z"                                     # a new source revision is
    r = gh.tick(T0 + timedelta(hours=3))
    assert r.publish["route"] == "review" and len(gh.review_prs()) == 2
    assert review_routing.has_review_label(gh.prs[-1]) and "jr-review-targets" in gh.prs[-1]["body"]
    assert gh.tick(T0 + timedelta(hours=4)).publish["route"] == "auto" and len(gh.review_prs()) == 2


# --- nothing weakened -------------------------------------------------------------------------------

def test_the_first_raise_still_routes_review_and_never_admits(wt_dir, monkeypatch):
    gh = _sim(wt_dir, monkeypatch)
    r = gh.tick(T0)
    assert r.publish["route"] == "review" and not r.publish["auto_merge"] and r.admitted == 0
    assert any(REPO in x for x in r.publish["review_reasons"])
    body = gh.prs[-1]["body"]
    assert f"`{REPO}`" in body and "jr-review-targets" in body and str(RID) in body


def test_a_failed_review_lookup_warns_and_never_aborts(wt_dir, monkeypatch):
    gh = _sim(wt_dir, monkeypatch)
    gh.list_rc = 1
    r = gh.tick(T0)
    assert not r.aborted and any("jr-review decisions" in w for w in r.warnings)
