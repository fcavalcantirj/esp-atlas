"""Tests for scripts/popularity_backfill.py — the one-off popularity backfill.

TDD, no network: `fetch_stars` and `fetch_catalog` are always injected fakes. Uses a small temp
fixture data dir with coding-domain ESP32 example firmware (an on-device git client, a code
editor), never lorem ipsum. Mirrors scripts/test_firmware_floor_audit.py's tmp_path convention.

Run: python3 -m pytest scripts/test_popularity_backfill.py -q
"""
from __future__ import annotations

import yaml

import popularity_backfill as backfill

# --- fixtures -------------------------------------------------------------

# An unstamped coding firmware (an on-device git client) -> should get a popularity block.
FW_UNSTAMPED_MD = """---
id: cardputer-git
type: firmware
name: Cardputer Git Client
url: https://github.com/devuser/cardputer-git
category: multi
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-git
  verified: '2026-09-01'
---

# Cardputer Git Client
"""

# An already-stamped coding firmware (a code editor) -> must be skipped, never overwritten.
FW_STAMPED_MD = """---
id: cardputer-code-editor
type: firmware
name: Cardputer Code Editor
url: https://github.com/devuser/cardputer-code-editor
category: multi
popularity:
  stars: 99
  downloads: 8000
  as_of: '2026-08-01'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-code-editor
  verified: '2026-08-01'
- field: popularity
  url: https://github.com/devuser/cardputer-code-editor
  verified: '2026-08-01'
---

# Cardputer Code Editor
"""


def _write_firmware(data_root, fw_id, text):
    p = data_root / "firmware" / fw_id / "firmware.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _fm(path):
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


# A no-network fetch_stars fake: owner/repo -> stargazers_count.
def _stars(mapping, default=0):
    return lambda owner_repo: mapping.get(owner_repo, default)


# A no-network launcher catalog fake.
_CATALOG = [
    {"name": "Cardputer Git Client", "github": "https://github.com/devuser/cardputer-git",
     "download": 640},
]


# --- tests ----------------------------------------------------------------

def test_stamps_an_unstamped_fixture(tmp_path):
    """(e) An unstamped firmware gets popularity{stars,downloads,as_of} + a popularity citation."""
    path = _write_firmware(tmp_path, "cardputer-git", FW_UNSTAMPED_MD)

    result = backfill.backfill(
        tmp_path,
        fetch_stars=_stars({"devuser/cardputer-git": 30}),
        fetch_catalog=lambda: _CATALOG,
        today="2026-09-01",
    )

    assert result["stamped"] == ["cardputer-git"]
    assert result["skipped"] == []
    fm = _fm(path)
    assert fm["popularity"] == {"stars": 30, "downloads": 640, "as_of": "2026-09-01"}
    assert any(s["field"] == "popularity" and s["verified"] == "2026-09-01"
               for s in fm["sources"])


def test_skips_an_already_stamped_fixture(tmp_path):
    """(e) An already-stamped firmware is skipped and its existing block is never overwritten."""
    path = _write_firmware(tmp_path, "cardputer-code-editor", FW_STAMPED_MD)

    result = backfill.backfill(
        tmp_path,
        fetch_stars=lambda r: 1,           # would-be different values, must NOT be applied
        fetch_catalog=lambda: [],
        today="2026-09-01",
    )

    assert result["stamped"] == []
    assert result["skipped"] == ["cardputer-code-editor"]
    fm = _fm(path)
    assert fm["popularity"] == {"stars": 99, "downloads": 8000, "as_of": "2026-08-01"}


def test_unmatched_catalog_gives_zero_downloads(tmp_path):
    """A firmware not present in the launcher catalog is stamped with downloads=0 (never invented)."""
    path = _write_firmware(tmp_path, "cardputer-git", FW_UNSTAMPED_MD)

    result = backfill.backfill(
        tmp_path,
        fetch_stars=_stars({"devuser/cardputer-git": 30}),
        fetch_catalog=lambda: [],          # empty catalog -> no match
        today="2026-09-01",
    )

    assert result["stamped"] == ["cardputer-git"]
    assert _fm(path)["popularity"]["downloads"] == 0


def test_missing_stars_treated_as_zero(tmp_path):
    """fetch_stars returning None (unresolvable repo) is stamped as 0 stars, not omitted."""
    path = _write_firmware(tmp_path, "cardputer-git", FW_UNSTAMPED_MD)

    result = backfill.backfill(
        tmp_path,
        fetch_stars=lambda r: None,
        fetch_catalog=lambda: _CATALOG,
        today="2026-09-01",
    )

    assert result["stamped"] == ["cardputer-git"]
    assert _fm(path)["popularity"] == {"stars": 0, "downloads": 640, "as_of": "2026-09-01"}


def test_stamped_firmware_still_parses_and_keeps_other_fields(tmp_path):
    """After stamping, the record is still well-formed and every original field survives."""
    path = _write_firmware(tmp_path, "cardputer-git", FW_UNSTAMPED_MD)

    backfill.backfill(tmp_path, fetch_stars=lambda r: 30,
                      fetch_catalog=lambda: _CATALOG, today="2026-09-01")

    fm = _fm(path)
    assert fm["id"] == "cardputer-git"
    assert fm["name"] == "Cardputer Git Client"
    assert fm["socs"] == ["esp32-s3"]
    assert "# Cardputer Git Client" in path.read_text(encoding="utf-8")


def test_matches_catalog_by_name_when_repo_differs(tmp_path):
    """Repo match is preferred, but a name match still recovers downloads when the github url in
    the catalog differs (e.g. a moved/renamed repo)."""
    path = _write_firmware(tmp_path, "cardputer-git", FW_UNSTAMPED_MD)
    catalog = [{"name": "Cardputer Git Client",
                "github": "https://github.com/someoneelse/moved-repo", "download": 512}]

    backfill.backfill(tmp_path, fetch_stars=lambda r: 3,
                      fetch_catalog=lambda: catalog, today="2026-09-01")

    assert _fm(path)["popularity"]["downloads"] == 512
