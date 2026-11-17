"""EspAtlas Jr — the daily quote report (jr/quote_run.py), the hygiene class's source.

Mirrors jr/pam_run.py for the demand runner: once a day, in the run's fresh worktree, every catalog record's
quoted spans are checked against the pages it cites (scripts/check_quotes.report) and the FAIL rows land as
`docs/demand/quote-report.json`. The broker (jr/demand_broker.intake) turns each FAIL record into ONE
hygiene work item for the executor: re-read the page and quote it as written, or omit the claim.

Fail closed: a report that ran out of its time budget is written with `complete: false` and starts no new
work; a report whose FAIL rows did not change is `unchanged` and lands nothing; any error is `deferred`
and the previous report stays. The report never carries page text, only the record, its id, the failing
quotes and the cited urls — all of which the record itself already holds.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "apps" / "core" / "src"))

STATE_PATH = "docs/demand/quote-report.json"
BUDGET_SECONDS = 300.0


@dataclass
class RefreshResult:
    status: str                      # updated | unchanged | deferred
    changed_paths: tuple = ()
    error: str = ""
    counts: dict = field(default_factory=dict)
    complete: bool = False

    def report(self) -> dict:
        return {"status": self.status, "changed_paths": list(self.changed_paths), "error": self.error,
                "counts": dict(self.counts), "complete": self.complete}


def _comparable(doc: dict | None) -> list:
    """What makes two reports the same job list: the FAIL rows' records and quotes, in order."""
    if not isinstance(doc, dict):
        return []
    return [(r.get("record"), tuple(r.get("quotes") or [])) for r in doc.get("records") or [] if isinstance(r, dict)]


def refresh_worktree(wt_path: Path, *, now: datetime, fetch=None, budget_seconds: float = BUDGET_SECONDS,
                     paths=None) -> RefreshResult:
    """Write the day's report into the worktree (or leave it) and say what changed. `fetch(url) -> Page`
    is scripts/check_quotes.fetch_page over a live client by default; `paths` the records to judge
    (default: every data/**/*.md of the worktree)."""
    import check_quotes
    from esp_atlas_core.frontmatter import iter_data_files
    today = now.astimezone(timezone.utc).date().isoformat()
    target = Path(wt_path) / STATE_PATH
    try:
        previous = json.loads(target.read_text(encoding="utf-8")) if target.is_file() else None
    except (OSError, json.JSONDecodeError):
        previous = None
    try:
        records = list(paths) if paths is not None else [p for _k, p in iter_data_files(Path(wt_path) / "data")]
        if fetch is None:
            if check_quotes.httpx is None:
                return RefreshResult("deferred", error="httpx not installed: no page can be read")
            client = check_quotes.httpx.Client(timeout=check_quotes.TIMEOUT_SECONDS, headers={"User-Agent": check_quotes.USER_AGENT})
            fetch = lambda url: check_quotes.fetch_page(client, url)  # noqa: E731
        doc = check_quotes.report(records, fetch, today=today, budget_seconds=budget_seconds)
    except Exception as e:  # noqa: BLE001 — a failed check is a deferral, the previous report stays
        return RefreshResult("deferred", error=f"{type(e).__name__}: {e}")
    # record paths relative to the worktree, never absolute
    for row in doc["records"] + doc["inconclusive"]:
        rec = row["record"]
        root = str(Path(wt_path).resolve())
        if rec.startswith(root):
            row["record"] = rec[len(root):].lstrip("/")
    counts = dict(doc["counts"])
    if _comparable(previous) == _comparable(doc) and (previous or {}).get("complete") == doc["complete"]:
        return RefreshResult("unchanged", counts=counts, complete=doc["complete"])
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(target)
    return RefreshResult("updated", changed_paths=(STATE_PATH,), counts=counts, complete=doc["complete"])
