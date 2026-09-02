"""Tests for scripts/validate.py's mechanical popularity-floor gate (SPEC-firmware-floor.md).

TDD, no network: check_popularity_floor() reuses firmware_floor_audit.audit() (STORED,
offline) against a temp fixture data dir. Real catalog-style hardware/firmware examples (a
Cardputer git client), never lorem ipsum.

Run: python3 -m pytest scripts/test_validate.py -q
"""
from __future__ import annotations

import validate

# --- fixtures -------------------------------------------------------------

# A non-curated firmware STAMPED sub-floor (3 stars, 1 fork) -> must fail validation.
FW_SUBFLOOR_MD = """---
id: cardputer-git
type: firmware
name: Cardputer Git Client
url: https://github.com/devuser/cardputer-git
category: multi
popularity:
  stars: 3
  forks: 1
  as_of: '2026-09-01'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-git
  verified: '2026-09-01'
- field: popularity
  url: https://github.com/devuser/cardputer-git
  verified: '2026-09-01'
---

# Cardputer Git Client
"""

# A non-curated firmware STAMPED above the floor via stars -> must NOT fail validation.
FW_ABOVE_FLOOR_MD = """---
id: cardputer-code-editor
type: firmware
name: Cardputer Code Editor
url: https://github.com/devuser/cardputer-code-editor
category: multi
popularity:
  stars: 40
  forks: 2
  as_of: '2026-09-01'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-code-editor
  verified: '2026-09-01'
- field: popularity
  url: https://github.com/devuser/cardputer-code-editor
  verified: '2026-09-01'
---

# Cardputer Code Editor
"""


def _write_firmware(data_root, fw_id, text):
    p = data_root / "firmware" / fw_id / "firmware.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# --- tests ----------------------------------------------------------------

def test_below_floor_fixture_fails_validation(tmp_path):
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)

    errors = validate.check_popularity_floor(tmp_path)

    assert len(errors) == 1
    assert "cardputer-git" in errors[0]
    assert "below popularity floor" in errors[0]


def test_above_floor_fixture_passes_validation(tmp_path):
    _write_firmware(tmp_path, "cardputer-code-editor", FW_ABOVE_FLOOR_MD)

    assert validate.check_popularity_floor(tmp_path) == []


def test_mixed_catalog_flags_only_the_subfloor_entry(tmp_path):
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)
    _write_firmware(tmp_path, "cardputer-code-editor", FW_ABOVE_FLOOR_MD)

    errors = validate.check_popularity_floor(tmp_path)

    assert len(errors) == 1
    assert "cardputer-git" in errors[0]


def test_empty_data_dir_has_no_floor_errors(tmp_path):
    assert validate.check_popularity_floor(tmp_path) == []


def test_error_message_never_mentions_downloads(tmp_path):
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)

    errors = validate.check_popularity_floor(tmp_path)

    assert not any("download" in e.lower() for e in errors)


def test_real_catalog_clears_the_floor():
    """The real, already-purged data/ catalog must clear the floor gate with zero errors —
    this is the mechanical enforcement `python3 scripts/validate.py` relies on."""
    assert validate.check_popularity_floor() == []
