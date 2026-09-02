"""EspAtlas Jr — pytest for jr/catalog_migrate.py (pure sweep functions; `main()` never runs
here — see its own guard). Fixtures are real catalog-style firmware.md text (matching
tools.author_firmware_record's actual on-disk shape), never lorem/animal placeholders.

Run: cd jr && python3 -m pytest test_catalog_migrate.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog_migrate  # noqa: E402
from scorer import FORK_FLOOR, STAR_FLOOR  # noqa: E402

ATOM_WATCH_MD = """---
id: atom-watch
type: firmware
name: Atom S3R Smartwatch UI LVGL
url: https://github.com/fbiego/atom-watch
category: multi
maintainer: fbiego
capabilities:
- ble
popularity:
  stars: 27
  forks: 4
  as_of: '2026-09-02'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/fbiego/atom-watch
  verified: '2026-09-02'
- field: popularity
  url: https://github.com/fbiego/atom-watch
  verified: '2026-09-02'
---

Atom-Watch is a tiny smartwatch project built for the M5Stack AtomS3R (128x128 display)
"""

M5APPS_WITH_DOWNLOADS_MD = """---
id: m5apps
type: firmware
name: M5Apps
url: https://github.com/d4rkmen/M5Apps
category: multi
maintainer: d4rkmen
socs:
- esp32-s3
popularity:
  stars: 90
  downloads: 1500
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/d4rkmen/M5Apps
  verified: '2026-08-27'
---

Multi-app installer for M5 CardPuter v1.0, v1.1 and ADV with a set of built-in tools
"""

FORK_MIRROR_MD = """---
id: ghostesp-mirror
type: firmware
name: GhostESP Mirror
url: https://github.com/someoneelse/ghostesp-mirror
category: pentest
maintainer: someoneelse
capabilities:
- wifi
popularity:
  stars: 4
  forks: 1
  as_of: '2026-09-02'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/someoneelse/ghostesp-mirror
  verified: '2026-09-02'
- field: popularity
  url: https://github.com/someoneelse/ghostesp-mirror
  verified: '2026-09-02'
---

A mirror of GhostESP for the Cardputer.
"""


def _fake_api(mapping: dict) -> callable:
    def _api(owner: str, repo: str) -> dict:
        return mapping.get(f"{owner}/{repo}", {})
    return _api


# ─────────────────────────── strip_downloads ───────────────────────────

def test_strip_downloads_removes_downloads_keeps_stars_forks_as_of():
    result = catalog_migrate.strip_downloads(M5APPS_WITH_DOWNLOADS_MD)
    fm, _ = catalog_migrate._split(result)
    assert "downloads" not in fm["popularity"]
    assert fm["popularity"]["stars"] == 90
    assert fm["popularity"]["as_of"] == "2026-09-01"


def test_strip_downloads_is_idempotent():
    once = catalog_migrate.strip_downloads(M5APPS_WITH_DOWNLOADS_MD)
    twice = catalog_migrate.strip_downloads(once)
    assert once == twice


def test_strip_downloads_is_a_noop_on_clean_entry():
    """No `downloads` key at all -> byte-identical passthrough, never re-rendered."""
    assert catalog_migrate.strip_downloads(ATOM_WATCH_MD) == ATOM_WATCH_MD


# ─────────────────────────── below_floor ───────────────────────────

def test_below_floor_true_when_both_below():
    assert catalog_migrate.below_floor(24, 24) is True


def test_below_floor_false_when_stars_at_boundary():
    assert catalog_migrate.below_floor(STAR_FLOOR, 0) is False


def test_below_floor_false_when_forks_at_boundary():
    assert catalog_migrate.below_floor(0, FORK_FLOOR) is False


def test_below_floor_true_one_below_boundary():
    assert catalog_migrate.below_floor(STAR_FLOOR - 1, FORK_FLOOR - 1) is True


def test_below_floor_treats_missing_as_zero():
    assert catalog_migrate.below_floor(None, None) is True


# ─────────────────────────── resolve_entry_fork ───────────────────────────

def test_resolve_entry_fork_rewrites_fork_to_its_source_and_flags_already_present():
    api = _fake_api({
        "someoneelse/ghostesp-mirror": {
            "full_name": "someoneelse/ghostesp-mirror", "fork": True,
            "stargazers_count": 4, "forks_count": 1,
            "source": {"full_name": "jorgen/ghostesp", "stargazers_count": 48, "forks_count": 9},
        },
    })
    result = catalog_migrate.resolve_entry_fork(FORK_MIRROR_MD, api)

    assert result["changed"] is True
    assert result["already_present"] is True
    assert result["source_full_name"] == "jorgen/ghostesp"

    fm, _ = catalog_migrate._split(result["text"])
    assert fm["url"] == "https://github.com/jorgen/ghostesp"
    assert fm["maintainer"] == "jorgen"
    assert fm["popularity"]["stars"] == 48
    assert fm["popularity"]["forks"] == 9
    for src in fm["sources"]:
        assert src["url"] == "https://github.com/jorgen/ghostesp"


def test_resolve_entry_fork_leaves_non_fork_unchanged():
    api = _fake_api({
        "fbiego/atom-watch": {
            "full_name": "fbiego/atom-watch", "fork": False,
            "stargazers_count": 27, "forks_count": 4,
        },
    })
    result = catalog_migrate.resolve_entry_fork(ATOM_WATCH_MD, api)

    assert result == {"text": ATOM_WATCH_MD, "changed": False,
                      "source_full_name": "fbiego/atom-watch", "already_present": False}


def test_resolve_entry_fork_is_idempotent_after_rewrite():
    """Running it a second time on the already-rewritten text (now pointing at the source
    itself, a non-fork) is a no-op."""
    api = _fake_api({
        "someoneelse/ghostesp-mirror": {
            "full_name": "someoneelse/ghostesp-mirror", "fork": True,
            "stargazers_count": 4, "forks_count": 1,
            "source": {"full_name": "jorgen/ghostesp", "stargazers_count": 48, "forks_count": 9},
        },
        "jorgen/ghostesp": {
            "full_name": "jorgen/ghostesp", "fork": False,
            "stargazers_count": 48, "forks_count": 9,
        },
    })
    once = catalog_migrate.resolve_entry_fork(FORK_MIRROR_MD, api)
    twice = catalog_migrate.resolve_entry_fork(once["text"], api)
    assert twice["changed"] is False
    assert twice["text"] == once["text"]


def test_resolve_entry_fork_handles_non_github_url_gracefully():
    md = ATOM_WATCH_MD.replace("https://github.com/fbiego/atom-watch", "https://example.com/fbiego/atom-watch")
    result = catalog_migrate.resolve_entry_fork(md, _fake_api({}))
    assert result == {"text": md, "changed": False, "source_full_name": None, "already_present": False}
