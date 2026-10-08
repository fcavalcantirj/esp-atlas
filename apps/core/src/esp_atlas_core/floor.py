"""The firmware popularity floor — ONE definition, imported by everything that gates on it.

SPEC-firmware-floor.md: a firmware qualifies iff **stars >= STAR_FLOOR OR forks >= FORK_FLOOR
OR it has an independent editorial home OR launcher/M5Burner downloads >= DOWNLOAD_FLOOR**. A
star is a bookmark; a fork is a derivative, a stronger "someone actually built on this" signal
— so a heavily-forked but under-starred utility still clears.

THE THIRD SIGNAL (editorial home). GitHub stars are not the same as notability: real, niche
firmware with a genuine independent write-up (e.g. RogueDuck: 6 stars, under 25 forks, but a
real homepage at ethicalhackersden.org) was wrongly cut by a stars/forks-only bar. A `homepage`
counts as editorial evidence only when it is a non-empty URL whose host is neither `github.com`
nor a `*.github.io` domain — those name the repo itself or a GitHub Pages mirror of it, not an
independent home. Filler with no homepage (e.g. `server-vampeta`: 3 stars, 0 forks) is unaffected
and still cut — the third signal only ever widens what clears, never narrows it.

THE FOURTH SIGNAL (launcher downloads). A prior revision of this module declared downloads dead
("not a citable, stable metric") and gated on GitHub stars/forks/editorial-home only. That bar
rejected exactly the firmware real users install most: M5Launcher (120k launcher downloads, 1
GitHub star), Evil-Cardputer (92k downloads, 1 star), Doom-for-Cardputer (37k downloads, 1 star)
— each sitting under a repo nobody stars because installing it never requires visiting GitHub.
A launcher/M5Burner download count this high is not noise; it is the single strongest "real
people are actually running this" signal the catalog has, stronger than a star a repo's own
author can rack up in an afternoon. `DOWNLOAD_FLOOR = 2000` sits far enough above a trivially
gamed number (a handful of friends clicking install) that clearing it is proof of real,
widespread use — not a rescue for every low-star repo, just the ones genuinely in people's
hands. Downloads are never fetched live (the launcher catalog, not GitHub, is the only source
for them), so every caller that re-verifies this signal — offline guards and live PR checks
alike — must read it from the record's PERSISTED `popularity.downloads` snapshot, never refetch
it.

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
DOWNLOAD_FLOOR = 2000


def is_editorial_home(homepage: str | None) -> bool:
    """True iff `homepage` is a real, independent project home — not the repo's own github.com
    page and not a `*.github.io` GitHub Pages mirror of it. A maintainer-run blog/site is
    evidence a firmware is genuinely in use that a star count can miss (the RogueDuck class).

    Public (not `_`-prefixed): callers that persist the editorial-home signal so it can be
    re-verified OFFLINE (jr/tools.py, jr/stage_admit.py, scripts/firmware_floor_audit.py) need
    to decide what counts as "editorial" using the exact same rule `clears_popularity_floor`
    uses below — never a second, hand-typed copy of this check."""
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


def clears_popularity_floor(stars: int | None, forks: int | None, homepage: str | None = None,
                            downloads: int | None = None) -> bool:
    """True iff `stars` or `forks` clears its floor, OR `homepage` names an independent editorial
    home (see `is_editorial_home`), OR `downloads` (a launcher/M5Burner install count) clears
    `DOWNLOAD_FLOOR` — a high download count is a FOURTH signal a stars/forks-only bar misses
    (the M5Launcher/Evil-Cardputer/Doom-for-Cardputer class: tens of thousands of installs, 1
    GitHub star). None counts as zero — an unstamped record has not been shown to clear
    anything, and the floor is a claim about evidence, not a guess."""
    return ((stars or 0) >= STAR_FLOOR or (forks or 0) >= FORK_FLOOR or is_editorial_home(homepage)
            or (downloads or 0) >= DOWNLOAD_FLOOR)
