"""Tests for scripts/firmware_floor_audit.py — the OFFLINE firmware popularity-floor audit + CI gate.

TDD, no network: the audit reads the STORED `popularity` block from frontmatter and never fetches.
Uses a small temp fixture data dir with coding-domain ESP32 example firmware (an on-device dev
tool, a code editor), never lorem ipsum. Mirrors scripts/test_data_completion.py's tmp_path
fixture-writing convention.

Run: python3 -m pytest scripts/test_firmware_floor_audit.py -q
"""
from __future__ import annotations

import firmware_floor_audit as audit

# --- fixtures -------------------------------------------------------------

# A non-curated coding firmware STAMPED sub-floor (3 stars, 10 downloads) -> flagged.
FW_SUBFLOOR_MD = """---
id: cardputer-git
type: firmware
name: Cardputer Git Client
url: https://github.com/devuser/cardputer-git
category: multi
popularity:
  stars: 3
  downloads: 10
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

# A non-curated coding firmware STAMPED above the floor via downloads (12 stars but 6000
# downloads — the Sun-Rider case) -> NOT flagged.
FW_POPULAR_MD = """---
id: cardputer-code-editor
type: firmware
name: Cardputer Code Editor
url: https://github.com/devuser/cardputer-code-editor
category: multi
popularity:
  stars: 12
  downloads: 6000
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

# A non-curated coding firmware with NO popularity block -> unstamped (needs backfill), NOT a
# floor failure.
FW_UNSTAMPED_MD = """---
id: cardputer-repl
type: firmware
name: Cardputer REPL
url: https://github.com/devuser/cardputer-repl
category: multi
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-repl
  verified: '2026-09-01'
---

# Cardputer REPL
"""

# A curated / known-good firmware (bruce is on CURATED_EXEMPT) -> exempt even sub-floor / unstamped.
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


# --- tests ----------------------------------------------------------------

def test_flags_stored_subfloor_noncurated_and_not_the_curated_entry(tmp_path):
    """(b) A STORED sub-floor non-curated firmware is flagged; a curated/exempt one is NOT."""
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)
    _write_firmware(tmp_path, "bruce", FW_CURATED_MD)

    report = audit.audit(tmp_path)

    flagged_ids = {e["id"] for e in report["flagged"]}
    assert flagged_ids == {"cardputer-git"}
    assert "bruce" not in flagged_ids
    assert "bruce" in report["exempt"]


def test_ci_flag_exits_nonzero_on_a_stored_subfloor_entry(tmp_path):
    """(b) --ci EXITS NON-ZERO when a stored entry is below both floors."""
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)

    assert audit.main(["--data-dir", str(tmp_path), "--ci"]) == 1


def test_above_floor_via_downloads_is_not_flagged(tmp_path):
    """(c) A stored entry with 12 stars but 6000 downloads clears the floor -> not flagged, --ci ok."""
    _write_firmware(tmp_path, "cardputer-code-editor", FW_POPULAR_MD)

    report = audit.audit(tmp_path)
    assert report["flagged"] == []
    assert audit.main(["--data-dir", str(tmp_path), "--ci"]) == 0


def test_unstamped_listed_separately_and_does_not_trip_ci(tmp_path):
    """(d) An entry with NO popularity block is reported as unstamped, not flagged, and --ci stays 0."""
    _write_firmware(tmp_path, "cardputer-repl", FW_UNSTAMPED_MD)

    report = audit.audit(tmp_path)
    assert {e["id"] for e in report["unstamped"]} == {"cardputer-repl"}
    assert report["flagged"] == []
    assert audit.main(["--data-dir", str(tmp_path), "--ci"]) == 0


def test_mixed_catalog_flags_only_the_subfloor(tmp_path):
    """A realistic mix: sub-floor (flagged), above-floor, unstamped, curated — only the sub-floor
    trips --ci."""
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)
    _write_firmware(tmp_path, "cardputer-code-editor", FW_POPULAR_MD)
    _write_firmware(tmp_path, "cardputer-repl", FW_UNSTAMPED_MD)
    _write_firmware(tmp_path, "bruce", FW_CURATED_MD)

    report = audit.audit(tmp_path)

    assert {e["id"] for e in report["flagged"]} == {"cardputer-git"}
    assert {e["id"] for e in report["unstamped"]} == {"cardputer-repl"}
    assert "bruce" in report["exempt"]
    assert audit.main(["--data-dir", str(tmp_path), "--ci"]) == 1


def test_empty_data_dir_does_not_crash(tmp_path):
    report = audit.audit(tmp_path)
    assert report["entries"] == []
    assert report["flagged"] == []
    assert report["unstamped"] == []
    assert audit.main(["--data-dir", str(tmp_path), "--ci"]) == 0


def test_cli_main_runs_and_prints_worklist(tmp_path, capsys):
    _write_firmware(tmp_path, "cardputer-git", FW_SUBFLOOR_MD)
    _write_firmware(tmp_path, "cardputer-repl", FW_UNSTAMPED_MD)
    _write_firmware(tmp_path, "bruce", FW_CURATED_MD)

    exit_code = audit.main(["--data-dir", str(tmp_path)])   # no --ci -> report only, exit 0

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "POPULARITY-FLOOR AUDIT" in out
    assert "cardputer-git" in out
    assert "UNSTAMPED" in out
    assert "cardputer-repl" in out
    assert "SUMMARY" in out
