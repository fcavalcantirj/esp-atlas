"""The firmware popularity floor — ONE definition, imported by everything that gates on it.

SPEC-firmware-floor.md: a firmware qualifies iff **stars >= STAR_FLOOR OR forks >= FORK_FLOOR**.
Downloads are not a metric anywhere. A star is a bookmark; a fork is a derivative, a stronger
"someone actually built on this" signal — so a heavily-forked but under-starred utility still
clears.

WHY THIS MODULE EXISTS. Three different floors coexisted in this repo at once:

    SPEC-firmware-floor.md    stars OR launcher downloads
    jr/scorer.py              stars OR downloads OR forks
    scripts/firmware_floor_audit.py   the same three, re-typed by hand

The audit carried a comment saying it "mirrors jr/scorer.py ... kept in sync by hand", because
jr/ is a standalone package with its own venv and was not importable from the repo-root scripts
runtime. Hand-sync is not sync: the CI gate and the drain could disagree about what qualifies,
which is exactly how sub-floor entries reached a catalog whose whole premise is that you can
trust what it says.

esp_atlas_core is the one package both runtimes already depend on — scripts/ imports it, and
jr/ reaches it through normalize.py — so it is the honest home for a constant they must agree
on. Change the bar HERE and every consumer moves together, or none does.
"""
from __future__ import annotations

STAR_FLOOR = 25
FORK_FLOOR = 25


def clears_popularity_floor(stars: int | None, forks: int | None) -> bool:
    """True iff `stars` or `forks` clears its floor. None counts as zero — an unstamped record
    has not been shown to clear anything, and the floor is a claim about evidence, not a guess."""
    return (stars or 0) >= STAR_FLOOR or (forks or 0) >= FORK_FLOOR
