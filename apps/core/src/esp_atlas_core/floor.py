"""The firmware popularity floor — ONE definition, imported by everything that gates on it.

SPEC-firmware-floor.md: a firmware qualifies iff **stars >= STAR_FLOOR OR forks >= FORK_FLOOR
OR it has an independent editorial home** (a real project site/blog, not the repo itself).
Downloads are not a metric anywhere. A star is a bookmark; a fork is a derivative, a stronger
"someone actually built on this" signal — so a heavily-forked but under-starred utility still
clears.

THE THIRD SIGNAL (editorial home). GitHub stars are not the same as notability: real, niche
firmware with a genuine independent write-up (e.g. RogueDuck: 6 stars, under 25 forks, but a
real homepage at ethicalhackersden.org) was wrongly cut by a stars/forks-only bar. A `homepage`
counts as editorial evidence only when it is a non-empty URL whose host is neither `github.com`
nor a `*.github.io` domain — those name the repo itself or a GitHub Pages mirror of it, not an
independent home. Filler with no homepage (e.g. `server-vampeta`: 3 stars, 0 forks) is unaffected
and still cut — the third signal only ever widens what clears, never narrows it.

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

from urllib.parse import urlparse

STAR_FLOOR = 25
FORK_FLOOR = 25


def _is_editorial_home(homepage: str | None) -> bool:
    """True iff `homepage` is a real, independent project home — not the repo's own github.com
    page and not a `*.github.io` GitHub Pages mirror of it. A maintainer-run blog/site is
    evidence a firmware is genuinely in use that a star count can miss (the RogueDuck class)."""
    if not homepage:
        return False
    parsed = urlparse(homepage)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host:
        return False
    if host == "github.com" or host.endswith(".github.com"):
        return False
    if host == "github.io" or host.endswith(".github.io"):
        return False
    return True


def clears_popularity_floor(stars: int | None, forks: int | None, homepage: str | None = None) -> bool:
    """True iff `stars` or `forks` clears its floor, OR `homepage` names an independent editorial
    home (see `_is_editorial_home`) — a real write-up/blog is a THIRD signal a stars/forks-only
    bar misses. None counts as zero — an unstamped record has not been shown to clear anything,
    and the floor is a claim about evidence, not a guess."""
    return (stars or 0) >= STAR_FLOOR or (forks or 0) >= FORK_FLOOR or _is_editorial_home(homepage)
