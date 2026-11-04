"""EspAtlas Jr — the dry-run's throwaway tree (jr/tick.py --dry-run).

A dry run must be read-only STRUCTURALLY, not by every stage remembering to check ctx.dry_run:
the tick copies the part of the checkout the stages read into a fresh temp dir OUTSIDE the repo
and runs every stage there, so any write a stage makes lands in the copy and dies with it. The
stages still honour ctx.dry_run and report "would write X"; this is the floor under them.

TREE is what the tick's stages and gauge read: the catalog (data/), the committed reports
(docs/: demand snapshots, the telemetry trend), COVERAGE.md, and Jr's committed decisions
(jr/*.json: the ledger, the board cooldown). Code is never copied — the stages import it from
the clone, read-only. Symlinks are copied as their CONTENT, so no write can follow a link back
into the checkout.
"""
from __future__ import annotations

import hashlib
import shutil
import tempfile
from pathlib import Path

TREE = ("data", "docs", "COVERAGE.md")
JR_STATE_GLOB = "*.json"     # jr/proposed_ledger.json, jr/board_cooldown.json, …
_IGNORE = shutil.ignore_patterns("__pycache__", ".DS_Store")


def copy(source: Path) -> Path:
    """A fresh temp dir holding TREE and jr/*.json from `source`; the caller removes it."""
    source = Path(source)
    scratch = Path(tempfile.mkdtemp(prefix="jr-dry-run-"))
    try:
        for rel in TREE:
            src = source / rel
            if src.is_dir():
                shutil.copytree(src, scratch / rel, ignore=_IGNORE)
            elif src.is_file():
                shutil.copy2(src, scratch / rel)
        (scratch / "jr").mkdir()
        for src in sorted((source / "jr").glob(JR_STATE_GLOB)):
            if src.is_file():
                shutil.copy2(src, scratch / "jr" / src.name)
    except BaseException:
        remove(scratch)
        raise
    return scratch


def remove(scratch: Path) -> None:
    shutil.rmtree(scratch, ignore_errors=True)


def fingerprint(root: Path) -> dict[str, str]:
    """relpath -> sha256 of every file under `root`."""
    root = Path(root)
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


def changed(before: dict[str, str], scratch: Path) -> list[str]:
    """The relpaths created or modified in `scratch` since `before` (its fingerprint at copy time)."""
    after = fingerprint(scratch)
    return sorted(p for p, h in after.items() if before.get(p) != h)
