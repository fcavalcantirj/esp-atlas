"""Tests for scripts/firmware_floor_audit.py — the firmware popularity-floor audit.

TDD, no network: `fetch_stars` is always an injected fake. Uses a small temp fixture data dir
with coding-domain ESP32 example firmware (an on-device dev tool, a code editor), never lorem
ipsum. Mirrors scripts/test_data_completion.py's tmp_path fixture-writing convention.

Run: python3 -m pytest scripts/test_firmware_floor_audit.py -q
"""
from __future__ import annotations

import firmware_floor_audit as audit

# --- fixtures -------------------------------------------------------------

# A non-curated, low-popularity coding firmware (an on-device git client) -> sub-floor, flagged.
FW_SUBFLOOR_MD = """---
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

# A non-curated, genuinely popular coding firmware (a code editor) -> clears the star floor.
FW_POPULAR_MD = """---
id: cardputer-code-editor
type: firmware
name: Cardputer Code Editor
url: https://github.com/devuser/cardputer-code-editor
category: multi
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-code-editor
  verified: '2026-09-01'
---

# Cardputer Code Editor
"""

# A curated / known-good firmware (bruce is on the CURATED_EXEMPT allowlist) -> exempt even at
# low stars.
FW_CURATED_MD = """---
id: bruce
type: firmware
name: Bruce
url: https://github.com/pr3y/Bruce
category: pentest
socs:
- esp32
sources:
- field: '*'
  url: https://github.com/pr3y/Bruce
  verified: '2026-09-01'
---

# Bruce
"""


def _write_firmware(data_root, fw_id, text):
    p = data_root / "firmware" / fw_id / "firmware.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def _stars(mapping, default=0):
    """A no-network fetch_stars fake: owner/repo -> stargazers_count."""
    return lambda owner_repo: mapping.get(owner_repo, default)


# --- tests ----------------------------------------------------------------

def test_flags_subfloor_noncurated_and_not_the_curated_entry(tmp_path):
    """The core case: a sub-floor non-curated firmware is flagged; a curated/exempt one is NOT,
    even at the same low star count."""
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)
    _write_firmware(tmp_path, "bruce", FW_CURATED_MD)
    fetch = _stars({"devuser/cardputer-git": 3, "pr3y/bruce": 3})

    report = audit.audit(tmp_path, fetch_stars=fetch)

    flagged_ids = {e["id"] for e in report["flagged"]}
    assert flagged_ids == {"cardputer-git"}
    assert "bruce" not in flagged_ids
    assert "bruce" in report["exempt"]


def test_popular_noncurated_is_not_flagged(tmp_path):
    """stars >= STAR_FLOOR clears the floor -> not flagged."""
    _write_firmware(tmp_path, "cardputer-code-editor", FW_POPULAR_MD)
    fetch = _stars({"devuser/cardputer-code-editor": 40})

    report = audit.audit(tmp_path, fetch_stars=fetch)

    assert report["flagged"] == []


def test_downloads_clear_the_floor(tmp_path):
    """A frontmatter-stored download count >= DOWNLOAD_FLOOR clears the floor even at low stars."""
    md = FW_SUBFLOOR_MD.replace("category: multi", "category: multi\ndownload: 800")
    _write_firmware(tmp_path, "cardputer-git", md)
    fetch = _stars({"devuser/cardputer-git": 3})

    report = audit.audit(tmp_path, fetch_stars=fetch)

    assert report["flagged"] == []


def test_unknown_stars_treated_as_zero_and_flagged(tmp_path):
    """A repo whose stars can't be resolved (fetch returns None) is treated as 0 -> below floor."""
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)
    fetch = lambda owner_repo: None

    report = audit.audit(tmp_path, fetch_stars=fetch)

    assert {e["id"] for e in report["flagged"]} == {"cardputer-git"}


def test_empty_data_dir_does_not_crash(tmp_path):
    report = audit.audit(tmp_path, fetch_stars=lambda r: 0)
    assert report["entries"] == []
    assert report["flagged"] == []


def test_cli_main_runs_and_prints_worklist(tmp_path, capsys, monkeypatch):
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)
    _write_firmware(tmp_path, "bruce", FW_CURATED_MD)
    monkeypatch.setattr(audit, "default_fetch_stars", lambda owner_repo: 3)

    exit_code = audit.main(["--data-dir", str(tmp_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "POPULARITY-FLOOR AUDIT" in out
    assert "cardputer-git" in out
    assert "SUMMARY" in out
