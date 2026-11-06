"""PAM refresh/persistence for an existing locked daily worktree.

No scheduler, PR publication, catalog authoring or autonomous research is hidden
here. The caller must include changed_paths in its existing publication even on
an empty/unchanged search snapshot, and keep processing GA/GSC when PAM defers.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import datetime as dt
import json
from pathlib import Path

import yaml

import pam_leads
import research_queue


STATE_PATH = "docs/demand/pam-leads.json"
MAX_STATE_BYTES = 2 * pam_leads.MAX_BYTES


@dataclass
class RefreshResult:
    status: str
    changed_paths: tuple[str, ...] = ()
    leads: int = 0
    potential_gaps: int = 0
    receipt: dict = field(default_factory=dict)
    error: str = ""
    state: dict | None = field(default=None, repr=False)

    def report(self) -> dict:
        """Bounded job-log receipt, not a copy of the full lead state."""
        return {"status": self.status, "changed_paths": list(self.changed_paths),
                "leads": self.leads, "potential_identity_gaps": self.potential_gaps,
                "receipt": self.receipt, "error": self.error}


def _comparable(state: dict | None):
    if state is None:
        return None
    return {"version": state["version"], "source": state["source"], "leads": state["leads"],
            "feeds": {name: {k: v for k, v in meta.items() if k != "fetched_at"}
                      for name, meta in state["feeds"].items()}}


def _previous(path: Path) -> dict | None:
    if not path.exists():
        return None
    with path.open("rb") as stream:
        raw = stream.read(MAX_STATE_BYTES + 1)
    if len(raw) > MAX_STATE_BYTES:
        raise pam_leads.FeedError("cached state exceeds size bound")
    state = json.loads(raw)
    if not isinstance(state, dict):
        raise pam_leads.FeedError("cached state is not an object")
    return state


def _board_identities(root: Path) -> list[dict]:
    if not (root / "data/boards").is_dir():
        raise pam_leads.FeedError("missing worktree board catalog")
    boards = [r for r in research_queue.load_catalog(root) if r["kind"] == "board"]
    if not boards or any(not r["id"] or not r["title"] for r in boards):
        raise pam_leads.FeedError("empty or unreadable worktree board identities")
    return [{"id": r["id"], "name": r["title"], "aliases": r["aliases"]} for r in boards]


def refresh_worktree(worktree: Path, *, now: dt.datetime | None = None,
                     fetch=pam_leads.fetch_feed, writer=research_queue.write_queue) -> RefreshResult:
    """Refresh fixed docs/demand state; errors preserve last-good bytes and return deferred.

    Call under the existing worker lock, in a fresh worktree. Source errors do
    not raise into the independent GA/GSC lane. Receipt timestamps still move
    on unchanged runs, but timestamp-only changes do not publish metadata PRs.
    """
    receipt = {"feed_statuses": {}}
    try:
        root = Path(worktree).resolve()
        path = root / STATE_PATH
        target = path.resolve()
        if not target.is_relative_to(root) or target.is_relative_to((root / "data").resolve()):
            raise pam_leads.FeedError("state path escapes docs worktree boundary")
        previous = _previous(path)
        catalog = _board_identities(root)

        def tracked_fetch(name, etag=None):
            response = fetch(name, etag)
            receipt["feed_statuses"].setdefault(name, []).append(response.status)
            return response

        current = pam_leads.refresh(previous, catalog, now=now or dt.datetime.now(dt.timezone.utc),
                                    fetch=tracked_fetch)
        receipt.update(checked_at=current["checked_at"],
                       feed_sha256={name: meta["sha256"] for name, meta in current["feeds"].items()})
        changed = _comparable(current) != _comparable(previous)
        if changed:
            writer(current, path)
        return RefreshResult("updated" if changed else "unchanged",
                             changed_paths=(STATE_PATH,) if changed else (),
                             leads=len(current["leads"]),
                             potential_gaps=sum(r["status"] == "potential_identity_gap" for r in current["leads"]),
                             receipt=receipt, state=current)
    except (OSError, ValueError, RuntimeError, yaml.YAMLError) as exc:
        # Generic filesystem failures may contain maintainer paths. Keep job
        # receipts bounded and free of those paths; the typed failure is enough
        # to defer this source while other demand sources continue.
        detail = str(exc)[:180] if isinstance(exc, pam_leads.FeedError) else type(exc).__name__
        return RefreshResult("deferred", receipt=receipt, error=detail)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Refresh PAM leads in an existing locked daily worktree")
    parser.add_argument("--worktree", required=True, type=Path)
    parser.add_argument("--json", action="store_true", help="print the bounded execution receipt")
    args = parser.parse_args(argv)
    result = refresh_worktree(args.worktree)
    if args.json:
        print(json.dumps(result.report(), sort_keys=True))
    else:
        print(f"PAM {result.status}: {result.leads} leads / {result.potential_gaps} potential gaps"
              + (f"; {result.error}" if result.error else ""))
    return 1 if result.status == "deferred" else 0


if __name__ == "__main__":
    raise SystemExit(main())
