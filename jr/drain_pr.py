"""EspAtlas Jr — catalog-drain PR orchestrator (jr/drain_pr.py).

Thin wrapper around drain.run_drain() (JR.md Law 3: bot proposes, humans dispose — Jr writes
PRs only, never `main`). If the drain authored anything, packages the new data/firmware +
data/recipes entries into a single PR on a fresh jr-drain-<UTC timestamp> branch. If it authored
nothing, prints one terse line and never touches git or gh — no branch, no commit, no PR.

Every git/gh call is created via a new branch FIRST (git checkout -B <drain-branch>) before any
staging or committing happens, and no git call ever references `main` — the only "main" in the
whole flow is the `gh pr create --base main` call, which cannot write to main.

Run (cron, via scripts/jr-drain.sh): python3 jr/drain_pr.py
"""
from __future__ import annotations
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

_JR_DIR = Path(__file__).resolve().parent
if str(_JR_DIR) not in sys.path:
    sys.path.insert(0, str(_JR_DIR))
import ledger  # noqa: E402
import pr_summary  # noqa: E402
import tools  # noqa: E402
from drain import run_drain as _run_drain  # noqa: E402

REPO = tools.REPO


def _facts(authored: list[str]) -> list[dict]:
    """The deterministic facts for each authored id — {id, name, category, url, capabilities,
    board} — read straight off the freshly-authored firmware.md frontmatter (and its recipe's
    board), never invented. Feeds the best-effort smart summary only; never written back."""
    facts = []
    for fid in authored:
        fw = tools._frontmatter(tools.FIRMWARE_DIR / fid / "firmware.md")
        board = ""
        for rdir in sorted((REPO / "data/recipes").glob(f"*__{fid}")):
            board = tools._frontmatter(rdir / "recipe.md").get("board", "") or ""
            if board:
                break
        facts.append({
            "id": fid,
            "name": fw.get("name", fid),
            "category": fw.get("category", ""),
            "url": fw.get("url", ""),
            "capabilities": fw.get("capabilities") or [],
            "board": board,
        })
    return facts


def _smart_summary(authored: list[str]) -> str | None:
    """Best-effort LLM smart summary for the PR description. ANY failure — no key, no client,
    error, timeout — yields None so the PR still opens with the terse cited template. Never
    raises: a summary problem must never stop the drain PR."""
    try:
        return pr_summary.summarize(_facts(authored))
    except Exception:
        return None


def default_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)


def default_gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=REPO, capture_output=True, text=True)


def branch_name(now: datetime | None = None) -> str:
    """jr-drain-YYYYMMDD-HHMM in UTC — one branch per drain run."""
    now = now or datetime.now(timezone.utc)
    return f"jr-drain-{now.strftime('%Y%m%d-%H%M')}"


def _new_paths(authored: list[str]) -> list[str]:
    """The new-file paths a drain run may have written for `authored` ids — ONLY under
    data/firmware/<id> and data/recipes/<board>__<id> — never anything else in the tree."""
    paths = []
    for fid in authored:
        fw_dir = REPO / "data/firmware" / fid
        if fw_dir.exists():
            paths.append(str(fw_dir.relative_to(REPO)))
        for rdir in (REPO / "data/recipes").glob(f"*__{fid}"):
            paths.append(str(rdir.relative_to(REPO)))
    return paths


def _pr_body(authored: list[str], summary: str | None = None) -> str:
    """Every authored firmware id with its source URL, plus a guard-green statement — read
    straight off the freshly-authored firmware.md frontmatter, never invented. If a best-effort
    smart `summary` was produced it is prepended ABOVE the terse cited list (prose only — the
    cited list below is unchanged and remains the ground truth)."""
    lines = []
    if summary:
        lines += [summary, "", "---", ""]
    lines += ["Jr's catalog drain — new entries this run:", ""]
    for fid in authored:
        fw = tools._frontmatter(tools.FIRMWARE_DIR / fid / "firmware.md")
        lines.append(f"- `{fid}` — {fw.get('url', '')}")
    lines += [
        "",
        "Deterministic guard: green.",
        "",
        "**Bot proposes, humans dispose** — skim, then merge (or drop any you don't want).",
        "",
        "— 🤖 EspAtlas Jr · catalog drain",
    ]
    return "\n".join(lines)


def _owner_repo_from_url(url: str) -> str:
    fn = (url or "").strip().rstrip("/").replace("https://github.com/", "").lower()
    return "/".join(fn.split("/")[:2])


def _record_proposed(authored: list[str], pr_ref: str | None, ledger_path, now: datetime) -> None:
    """Record every `authored` id into the proposed-ledger (jr/ledger.py) as status=proposed with
    `pr_ref`, at the moment this PR is opened (deliverable 2) — the SAME `now` used for the
    branch name, and reading each id's repo straight off the firmware.md just authored, never
    invented."""
    for fid in authored:
        fw = tools._frontmatter(tools.FIRMWARE_DIR / fid / "firmware.md")
        repo = _owner_repo_from_url(fw.get("url", ""))
        if not repo:
            continue
        ledger.record_proposed(fid, repo, pr_ref=pr_ref, path=ledger_path, now=now.isoformat())


def open_drain_pr(authored: list[str], git=default_git, gh=default_gh,
                  now: datetime | None = None, ledger_path: Path | None = None) -> dict:
    """Create the drain branch, stage+commit+push ONLY the new firmware/recipe paths, and open
    the PR against main. Always creates and switches to the drain branch FIRST — no add/commit
    happens against whatever branch was checked out before this call. Records every authored id
    into the proposed-ledger (`ledger_path`, injectable for tests; resolved to the real
    ledger.DEFAULT_LEDGER_PATH lazily — NOT as a bound default — so a test fixture can monkeypatch
    ledger.DEFAULT_LEDGER_PATH and every caller that omits ledger_path picks it up) as proposed
    with the PR's URL the moment the PR is opened (deliverable 2) — the prerequisite for
    deliverable 3's drain dedup to ever see it on the next run. The summary is computed ONCE here
    and reused for BOTH the PR body and the returned dict (so the cron can deliver it to Telegram
    without rebuilding it). Returns {"branch", "pr_ok", "pr_url", "summary"}."""
    now = now or datetime.now(timezone.utc)
    ledger_path = ledger.DEFAULT_LEDGER_PATH if ledger_path is None else ledger_path
    branch = branch_name(now)
    git("checkout", "-B", branch)
    paths = _new_paths(authored)
    git("add", *paths)
    subject = f"feat(firmware): jr drain batch of {len(authored)} new entries"
    git("commit", "-m", subject)
    git("push", "-u", "origin", branch)
    summary = _smart_summary(authored)  # computed ONCE — reused for PR body AND stdout/Telegram.
    pr = gh("pr", "create", "--base", "main", "--head", branch,
           "--title", subject, "--body", _pr_body(authored, summary))
    pr_ok = pr.returncode == 0
    pr_url = pr.stdout.strip()
    if pr_ok:
        _record_proposed(authored, pr_url or None, ledger_path, now)
    return {"branch": branch, "pr_ok": pr_ok, "pr_url": pr_url, "summary": summary}


def main(run_drain=_run_drain, git=default_git, gh=default_gh, now: datetime | None = None,
        ledger_path: Path | None = None) -> dict:
    report = run_drain()
    authored = report.get("authored") or []
    if not authored:
        print("jr-drain: no new entries")
        return {"authored": [], "pr": None}
    pr = open_drain_pr(authored, git=git, gh=gh, now=now, ledger_path=ledger_path)
    # Telegram-friendly nudge: the summary text (verbatim, deterministic body + optional headline),
    # then a final line linking the PR and naming the branch — so the maintainer can read the batch
    # straight from the cron message without opening the PR.
    summary = pr.get("summary")
    if summary:
        print(summary)
        print("")
    link = pr.get("pr_url") or "(PR creation failed)"
    print(f"jr-drain: {len(authored)} new entries — PR {link} · branch {pr['branch']}")
    return {"authored": authored, "pr": pr}


if __name__ == "__main__":
    main()
