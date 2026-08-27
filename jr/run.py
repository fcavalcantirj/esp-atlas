"""EspAtlas Jr — the daily heartbeat.

Runs Jr's jobs, opens triple-validated PRs for anything cleanly proposable, and nudges Felipe
with the outcome — including a quiet "nothing today" so he knows Jr is alive. Never writes
`main`, never auto-merges (SPEC §2.3). Cron: daily.

    python run.py daily        # the scheduled run
    python run.py drain        # just the launcher-drain job (for testing)
"""
from __future__ import annotations
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import tools
import notify
from agent import jr


def _recipe_dirs() -> set[str]:
    d = tools.REPO / "data/recipes"
    return {x.name for x in d.iterdir() if x.is_dir()} if d.exists() else set()


def _cleanup(fid: str | None, rid: str | None) -> None:
    """Remove a rejected authored record so main/branch stays clean."""
    if fid:
        shutil.rmtree(tools.FIRMWARE_DIR / fid, ignore_errors=True)
    if rid:
        shutil.rmtree(tools.REPO / "data/recipes" / rid, ignore_errors=True)


def drain_once() -> dict:
    """Author the top genuinely-new firmware + recipe, then INDEPENDENTLY triple-validate
    (never trusting the agent's self-report) and open a PR only if clean."""
    if not tools.uncatalogued_with_code(1):
        return {"action": "none", "detail": "no new candidates in the launcher backlog"}
    before_fw, before_rc = tools.catalogued_firmware_ids(), _recipe_dirs()
    jr.run("Add the single top genuinely-new firmware and its recipe. Cite-or-omit; also set "
           "maintainer/distribution/capabilities when the repo evidences them; guard; triple_validate.")
    new_fw = sorted(tools.catalogued_firmware_ids() - before_fw)
    new_rc = _recipe_dirs() - before_rc
    if not new_fw:
        return {"action": "none", "detail": "agent proposed nothing this run"}
    fid = new_fw[0]
    rid = next((r for r in new_rc if fid in r), None)
    verdict = tools.triple_validate(fid, rid) if rid else {"pass": False, "gate3_structure": ["no recipe"]}
    if not verdict["pass"]:
        _cleanup(fid, rid)
        return {"action": "rejected", "fid": fid, "verdict": verdict}
    pr = tools.open_pr(fid, f"feat(firmware): add {fid} (unverified) + recipe", recipe_id=rid)  # auto-nudges
    return {"action": "pr", "fid": fid, "rid": rid, "pr_url": pr.get("pr_url"), "ok": pr.get("ok")}


def daily() -> dict:
    """The scheduled run. One consolidated outcome nudge (open_pr already nudges on a real PR)."""
    r = drain_once()
    if r["action"] == "pr" and r.get("ok"):
        pass  # open_pr already fired the PR nudge with the link
    elif r["action"] == "rejected":
        notify.send_telegram(
            f"🤖 *Jr daily* — authored `{r.get('fid')}` but it failed triple-validate; "
            f"**no PR** (the guard did its job). I'll try a different candidate next run.")
    else:
        notify.send_telegram("🤖 *Jr daily* — ran clean, **nothing new to propose** today. "
                             "Atlas is fresh. ✅")
    return r


if __name__ == "__main__":
    job = sys.argv[1] if len(sys.argv) > 1 else "daily"
    print(job, "→", globals()[job]())
