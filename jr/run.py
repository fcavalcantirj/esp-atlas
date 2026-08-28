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


def _board_dirs() -> set[tuple[str, str]]:
    d = tools.BOARDS_DIR
    return {(b.parent.name, b.name) for b in d.glob("*/*") if b.is_dir()} if d.exists() else set()


def _cleanup_board(brand: str | None, board_id: str | None) -> None:
    """Remove a rejected authored board dir so main/branch stays clean (mirrors _cleanup)."""
    if brand and board_id:
        shutil.rmtree(tools.BOARDS_DIR / brand / board_id, ignore_errors=True)


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


def drain_batch(n: int = 20, label: str | None = None) -> dict:
    """Author up to n new firmware (fresh agent each, for clean context), triple-validate each,
    and bundle the valid ones into ONE reviewable daily batch PR. Rejected ones are fully cleaned
    up (record + recipes + run-case). Funded (paid Groq) — the constraint is human review, so one
    batch PR/day, not a flood."""
    import datetime as dt
    from agent import make_jr
    label = label or dt.date.today().isoformat()
    authored: list[str] = []
    urls: dict[str, str] = {}
    for i in range(n):
        if tools.month_spend() >= tools.MONTHLY_CAP_USD:   # hard $5/month cap
            break
        if not tools.uncatalogued_with_code(1):
            break
        before_fw, before_rc = tools.catalogued_firmware_ids(), _recipe_dirs()
        try:
            resp = make_jr(session_id=f"batch-{label}-{i}").run(
                "Add the top genuinely-new firmware. Read READMEs, choose category+boards only, "
                "then author_firmware_and_recipes, then triple_validate.")
            m = getattr(resp, "metrics", None)
            tools.record_spend(getattr(m, "input_tokens", 0), getattr(m, "output_tokens", 0))
        except Exception:
            continue
        new_fw = sorted(tools.catalogued_firmware_ids() - before_fw)
        new_rc = _recipe_dirs() - before_rc
        if not new_fw:
            continue
        fid = new_fw[0]
        rid = next((r for r in new_rc if fid in r), None)
        verdict = tools.triple_validate(fid, rid) if rid else {"pass": False}
        if verdict.get("pass"):
            authored.append(fid)
            urls[fid] = tools._frontmatter(tools.FIRMWARE_DIR / fid / "firmware.md").get("url", "")
        else:  # reject: remove record, recipes, and its run-case so the batch stays green
            _cleanup(fid, None)
            for r in new_rc:
                shutil.rmtree(tools.REPO / "data/recipes" / r, ignore_errors=True)
            tools.remove_run_case(fid)
    if not authored:
        notify.send_telegram("🤖 *Jr batch* — ran, nothing authorable this pass.")
        return {"action": "none"}
    pr = tools.open_batch_pr(authored, label)
    for fid in authored:                                # never re-propose these while their PR is open
        tools.mark_proposed(urls.get(fid, ""))
    notify.send_telegram(
        f"🤖 *Jr daily batch* — **{len(authored)} new firmware** for review: "
        f"[PR]({pr.get('pr_url')})\n" + ", ".join(f"`{a}`" for a in authored[:15])
        + f"\n💵 month-to-date: ${tools.month_spend():.2f} / ${tools.MONTHLY_CAP_USD:.0f}")
    return {"action": "batch", "count": len(authored), "pr_url": pr.get("pr_url"), "firmware": authored}


_BOARD_SCHEMA_SUMMARY = (
    "board record: id (== folder), brand (== folder), name; exactly one of soc (a data/socs/ "
    "id) or module (a data/modules/ id) — must match the chip family named on the source page; "
    "optional dimensions_mm/usb/power/display/extras/io/notes/aka/flash_mb/psram_mb, each cited "
    "by a sources[] entry (field+url+verified)."
)


def _oracle_check(brand: str, board_id: str) -> dict:
    """oracle_review() a freshly-authored board against its own first cited source page — an
    ADDITIONAL quality gate before board_triple_validate (SPEC: the deterministic guard stays
    the final authority; the oracle only catches things it can't, like the MagTag-class wrong-
    chip bug, before a PR is even proposed)."""
    board_md = tools.BOARDS_DIR / brand / board_id / "board.md"
    if not board_md.exists():
        return {"approve": False, "issues": ["board.md not found"], "notes": ""}
    fm = tools._frontmatter(board_md)
    sources = fm.get("sources") or []
    page_url = sources[0].get("url") if sources else None
    page_text = tools.fetch_url(page_url).get("text", "") if page_url else ""
    return tools.oracle_review(board_md.read_text(), page_text, _BOARD_SCHEMA_SUMMARY)


def boards_batch(n: int = 2, vendor: str | None = None, label: str | None = None) -> dict:
    """Author up to n new boards from the COVERAGE.md backlog (fresh agent/session each, for
    clean context), then gate each through oracle_review (a stronger model fact-checking the
    draft against its own source page) AND board_triple_validate (the deterministic, FINAL
    authority) before bundling the valid ones into ONE reviewable batch PR — mirrors
    drain_batch() for firmware. `vendor` optionally restricts to one COVERAGE.md section (e.g.
    'Espressif'). A board the oracle rejects gets ONE retry (fed the oracle's issues) before
    being cleaned up. Enforces the $/month cap (SPEC: defense-in-depth even on free models)."""
    import datetime as dt
    from agent import make_jr_board
    label = label or dt.date.today().isoformat()
    authored: list[tuple[str, str]] = []
    for i in range(n):
        if tools.month_spend() >= tools.MONTHLY_CAP_USD:   # hard $/month cap (defense-in-depth)
            break
        backlog = tools.coverage_backlog()
        if vendor:
            backlog = [b for b in backlog if b.get("vendor") == vendor]
        if not backlog:
            break
        before = _board_dirs()
        board_agent = None
        try:
            board_agent = make_jr_board(session_id=f"board-batch-{label}-{i}")
            board_agent.run(
                "Pick ONE backlog board via coverage_backlog(), fetch its official page, author "
                "ONLY citable fields (omit anything the page doesn't state), then "
                "board_triple_validate; retry <=3 on a red gate.")
        except Exception:
            continue
        new = _board_dirs() - before
        if not new:
            continue
        brand, board_id = next(iter(new))

        oracle_verdict = _oracle_check(brand, board_id)
        if not oracle_verdict.get("approve") and board_agent is not None:
            issues = "; ".join(oracle_verdict.get("issues") or []) or "unspecified"
            try:
                board_agent.run(
                    f"An independent fact-checker REJECTED this board record: {issues}. "
                    "Re-check the source page and fix it (call author_board again with the "
                    "corrected soc/module/fields), then board_triple_validate again.")
            except Exception:
                pass
            new = _board_dirs() - before
            if new:
                brand, board_id = next(iter(new))
                oracle_verdict = _oracle_check(brand, board_id)
        if not oracle_verdict.get("approve"):
            _cleanup_board(brand, board_id)
            continue

        verdict = tools.board_triple_validate(board_id)
        if verdict.get("pass"):
            authored.append((brand, board_id))
        else:
            _cleanup_board(brand, board_id)
    if not authored:
        notify.send_telegram("🤖 *Jr board batch* — ran, nothing authorable this pass.")
        return {"action": "none"}
    pr = tools.open_board_batch_pr(authored, label)
    notify.send_telegram(
        f"🤖 *Jr board batch* — **{len(authored)} new board(s)** for review: "
        f"[PR]({pr.get('pr_url')})\n" + ", ".join(f"`{b}`" for _, b in authored[:15]))
    return {"action": "batch", "count": len(authored), "pr_url": pr.get("pr_url"),
            "boards": [b for _, b in authored]}


def daily() -> dict:
    """The scheduled run — a batch of up to 20 firmware into ONE reviewable PR (paid Groq)."""
    return drain_batch(2)  # budget-safe at real per-run cost; raise once tokens are trimmed


def boards() -> dict:
    """The scheduled board-population run — a small batch (staleness-queue budget, SPEC §3)."""
    return boards_batch(2)


if __name__ == "__main__":
    job = sys.argv[1] if len(sys.argv) > 1 else "daily"
    print(job, "→", globals()[job]())
