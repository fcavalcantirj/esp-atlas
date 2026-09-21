"""EspAtlas Jr — the GitHub-topics stage: admit new firmware from the topics source
(jr/stage_admit_topics.py).

A small, additive tick stage over jr/author_topics.py's one-shot driver: the SAME deterministic
pipeline the topics source already used for its first admission batch (jr/drain.py run_drain ->
jr/source_topics.py -> jr/scorer.py — no LLM, no new gate) wired to run automatically, a couple of
firmware at a time, every hour, so the catalog keeps growing from topics after the launcher pool
(jr/stage_admit.py) drained (DECISION-LOG.md). Bounded by tick.TOPICS_PER_TICK, independent of the
allocator's A/B split — appended to jr/tick.py's hourly_stages() after admit+boardmap.

run_drain() is a standalone one-shot design (`python3 author_topics.py`) with three gaps a tick
stage can't inherit unfixed, closed here without touching drain.py, tools.py or any gate:

  - run_drain (and the tools.py authoring functions under it) write against tools.REPO — the
    process's OWN checkout, never a caller-supplied root. A tick stage writes into a FRESH
    worktree (ctx.root) so the tick's own guard validates, and jr/publish.py commits, exactly
    what the tick wrote and nothing else. `_rooted_tools` below points every REPO-derived
    tools.py path constant (and board_soc's stale-bound `repo=REPO` default — captured at import
    time, so reassigning tools.REPO alone can't reach it) at ctx.root for the span of one
    run_drain() call, restoring them after — the same target jr/tick.py's guard_env() aims
    scripts/validate.py at via ESP_ATLAS_REPO_ROOT/PYTHONPATH.
  - run_drain never records an authored id as "proposed" in the ledger (its only ledger write is
    ledger.record_seen for below-floor skips) — exactly the gap jr/tick.hydrate_open_pr_ledger
    exists to close for stage_admit's launcher path. Left alone, a topics candidate sitting in an
    unmerged tick PR would be re-discovered and re-authored into a DUPLICATE PR next hour (the
    historical #158/#159 bug). So every id run_drain reports authored is recorded via
    memory.record_proposed — the same call stage_admit.py makes — right after.
  - That same run_drain ledger write — ledger.record_seen for below-floor skips — is a v1, TTL-less
    write: it drops `expires`, which scripts/ledger_guard.py rejects on any "seen" record a PR adds
    or changes. Left alone, every tick that skips a below-floor candidate ships a guard-red PR, auto-
    merge never fires, PRs pile up, and jr/tick.py's >3h-open guard then aborts every later tick (the
    hourly-tick stall this stage exists to prevent). So every skip in run_drain's report
    (`skipped_popularity`) is re-recorded via memory.record_seen — the v2 writer that applies
    SEEN_TTL_DAYS — right after the authored loop; memory._write's transition rules make the
    re-record a safe no-op if the id was already proposed/merged/permanently rejected since.

Dry-run: run_drain has no dry-run mode (it always authors+guards+writes), so dry-run here runs
the SCORING half of the same pipeline directly (drain.prefilter -> score_candidates -> rank_juicy
-> cap_categories, all already root-agnostic — no monkeypatch needed) and stops before authoring:
same contract as stage_admit.run's dry-run, writes nothing.
"""
from __future__ import annotations

import json
import os
import urllib.parse
from contextlib import contextmanager
from pathlib import Path

import drain
import ledger
import memory
import source_topics
import tools
from budget import BudgetExceeded

# Score at most `budget * SCORE_MULTIPLIER` prefiltered candidates per tick. run_drain's own
# fetch_limit (default PREFILTER_LIMIT=120) is NOT bounded by batch_size/max_per_category — those
# only cap the LATER selection step — so left at its default this stage would fetch_meta a
# hundred-odd repos every hour even though it only ever admits `budget`. Keeps the "BOUNDED,
# low-risk" contract on GitHub-call cost, not just on admitted count.
SCORE_MULTIPLIER = 5

_ROOTED_ATTRS = ("REPO", "FIRMWARE_DIR", "BOARDS_DIR", "SOCS_DIR", "MODULES_DIR", "COVERAGE_MD")


def _topic_search(ctx):
    """search(topic, per_page) -> raw GitHub search `items`, routed through ctx.gh (counted by
    the tick's Budget) instead of source_topics.default_search_topic's own uncounted subprocess —
    otherwise the identical query/sort/endpoint."""
    def search(topic, per_page=100):
        query = urllib.parse.quote(f"topic:{topic}", safe=":")
        p = ctx.gh("api", f"search/repositories?q={query}&sort=stars&order=desc&per_page={per_page}")
        if getattr(p, "returncode", 1) != 0:
            return []
        try:
            data = json.loads(getattr(p, "stdout", "") or "{}")
        except json.JSONDecodeError:
            return []
        items = data.get("items") if isinstance(data, dict) else None
        return items if isinstance(items, list) else []
    return search


@contextmanager
def _rooted_tools(root: Path):
    """Point tools.py's REPO-derived path constants (and board_soc's stale-bound default) at
    `root` for the span of the block, restoring them after — see module docstring."""
    saved = {name: getattr(tools, name) for name in _ROOTED_ATTRS}
    saved_board_soc = tools.board_soc
    saved_env = {k: os.environ.get(k) for k in ("ESP_ATLAS_REPO_ROOT", "PYTHONPATH")}
    tools.REPO = root
    tools.FIRMWARE_DIR = root / "data" / "firmware"
    tools.BOARDS_DIR = root / "data" / "boards"
    tools.SOCS_DIR = root / "data" / "socs"
    tools.MODULES_DIR = root / "data" / "modules"
    tools.COVERAGE_MD = root / "COVERAGE.md"
    tools.board_soc = lambda board_id, repo=root, _orig=saved_board_soc: _orig(board_id, repo=root)
    os.environ["ESP_ATLAS_REPO_ROOT"] = str(root)
    src = str(root / "apps" / "core" / "src")
    os.environ["PYTHONPATH"] = src + (os.pathsep + saved_env["PYTHONPATH"] if saved_env["PYTHONPATH"] else "")
    try:
        yield
    finally:
        for name, val in saved.items():
            setattr(tools, name, val)
        tools.board_soc = saved_board_soc
        for k, v in saved_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _written_paths(root: Path, authored_ids: list[str]) -> list[str]:
    """firmware.md + every recipe.md an authored id wrote, repo-relative to `root` — run_drain's
    report carries only the id, so this mirrors drain._cleanup's own glob-by-suffix technique to
    recover what it wrote, for the tick's commit pathspec (report.TickReport.paths)."""
    paths = []
    for fid in authored_ids:
        fmd = root / "data" / "firmware" / fid / "firmware.md"
        if fmd.exists():
            paths.append(str(fmd.relative_to(root)))
        for rdir in sorted((root / "data" / "recipes").glob(f"*__{fid}")):
            rmd = rdir / "recipe.md"
            if rmd.exists():
                paths.append(str(rmd.relative_to(root)))
    return paths


def _owner_repo_from_firmware_md(path: Path) -> str | None:
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("url:") and "github.com/" in line:
            fn = line.split("github.com/", 1)[1].strip().rstrip("/").lower()
            return "/".join(fn.split("/")[:2])
    return None


def run(ctx, budget: int):
    """The topics stage for jr/tick.py: admits AT MOST `budget` firmware from the GitHub-topics
    source (jr/source_topics.DEFAULT_TOPICS) in one tick, via jr/drain.run_drain — the same
    author+guard+ledger pipeline jr/author_topics.py's one-shot run used. Returns a
    tick.StageResult, same shape as stage_admit.run's."""
    import tick
    today = ctx.now.strftime("%Y-%m-%d")
    search = _topic_search(ctx)
    try:
        entries = source_topics.fetch_topic_repos(source_topics.DEFAULT_TOPICS, search=search)
    except BudgetExceeded as e:
        return tick.StageResult("admit_topics", paths=[], summary=f"stopped: {e}", admitted=0, rejects={})
    except Exception as e:  # noqa: BLE001 — a blind stage writes nothing, flags a human
        return tick.StageResult("admit_topics", paths=[], summary=f"topics source unreadable: {type(e).__name__}: {str(e)[:120]}",
                                admitted=0, rejects={}, needs_human=True)

    fetch_limit = budget * SCORE_MULTIPLIER

    if ctx.dry_run:
        catalogued_repos, catalogued_tokens = tools._catalogued_repos_and_tokens(ctx.root / "data" / "firmware")
        led = ledger.load_ledger(ctx.ledger_path)
        prefiltered = drain.prefilter(entries, catalogued_repos, catalogued_tokens, ledger_state=led)[:fetch_limit]
        fetch_meta = ctx.budget.wrap(drain.default_fetch_meta, "gh")
        try:
            scored, skipped = drain.score_candidates(prefiltered, catalogued_repos, catalogued_tokens,
                                                      fetch_meta=fetch_meta, ledger_state=led,
                                                      resolve_source=lambda owner, repo: {})
        except BudgetExceeded as e:
            return tick.StageResult("admit_topics", paths=[], summary=f"stopped: {e}", admitted=0, rejects={})
        selected, _dropped_cap = drain.cap_categories(drain.rank_juicy(scored), max_per_category=budget, batch_size=budget)
        lines = [f"{s['record']['id']}: would admit" for s in selected]
        summary = "; ".join(lines) if lines else "no candidates"
        rejects = {"skipped_scoring": len(skipped)} if skipped else {}
        return tick.StageResult("admit_topics", paths=[], summary=summary, admitted=0, rejects=rejects)

    fetch_meta = ctx.budget.wrap(drain.default_fetch_meta, "gh")
    try:
        with _rooted_tools(ctx.root):
            report = drain.run_drain(
                fetch_limit=fetch_limit,
                batch_size=budget,
                max_per_category=budget,
                fetch_catalog=lambda: entries,
                fetch_meta=fetch_meta,
                ledger_path=ctx.ledger_path,
                today=today,
                resolve_source=lambda owner, repo: {},
            )
    except BudgetExceeded as e:
        return tick.StageResult("admit_topics", paths=[], summary=f"stopped: {e}", admitted=0, rejects={})

    authored = report["authored"]
    paths = _written_paths(ctx.root, authored)
    items = []
    for fid in authored:
        fmd = ctx.root / "data" / "firmware" / fid / "firmware.md"
        owner_repo = _owner_repo_from_firmware_md(fmd) if fmd.exists() else None
        if owner_repo:
            memory.record_proposed(fid, owner_repo, path=ctx.ledger_path, now=ctx.now)
        items.append({"kind": "firmware", "id": fid})

    # run_drain's only ledger write for below-floor skips is ledger.record_seen (jr/ledger.py) —
    # a v1, TTL-less write that scripts/ledger_guard.py rejects (a "seen" record with no
    # `expires`). Re-record each through memory.record_seen, the v2 writer that applies
    # SEEN_TTL_DAYS, so the ledger this stage ships always carries an `expires` on every "seen"
    # entry. memory._write's transition rules make this safe: it never downgrades a
    # merged/proposed/permanent-rejection record that ledger.record_seen already wrote.
    for s in report["skipped_popularity"]:
        memory.record_seen(s["firmware_id"], s["repo"], path=ctx.ledger_path, now=ctx.now)

    rejects = {}
    if report["skipped_popularity"]:
        rejects["below_floor"] = len(report["skipped_popularity"])
    other_skipped = report["skipped_scoring"] - len(report["skipped_popularity"])
    if other_skipped > 0:
        rejects["skipped_scoring"] = other_skipped
    if report["dropped_cap"]:
        rejects["dropped_cap"] = report["dropped_cap"]
    if report["dropped_guard"]:
        rejects["guard_red"] = len(report["dropped_guard"])

    summary = (f"fetched={report['fetched']} prefiltered={report['prefiltered']} "
              f"scored_clean={report['scored_clean']} authored={len(authored)}")
    if report["dropped_guard"]:
        summary += "; " + "; ".join(f"{d['id']}: {d['reason']}" for d in report["dropped_guard"])
    if not report["guard"].get("ok"):
        summary += f"; final guard red: {(report['guard'].get('output') or '')[-160:]}"

    return tick.StageResult("admit_topics", paths=paths, summary=summary, admitted=len(authored),
                            rejects=rejects, items=items)
