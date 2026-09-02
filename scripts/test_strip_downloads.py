"""Tests for scripts/strip_downloads.py — the one-off DOWNLOADS-STRIP migration
(SPEC-firmware-floor.md: downloads dropped entirely, the floor is stars-or-forks only).

TDD, no network: pure frontmatter rewriting over a temp fixture data dir. Uses real
catalog-style hardware/firmware examples (a Cardputer GPS logger, a badusb tool), never lorem
ipsum. Mirrors scripts/test_popularity_backfill.py's tmp_path convention.

Run: python3 -m pytest scripts/test_strip_downloads.py -q
"""
from __future__ import annotations

import yaml

import strip_downloads as migration

# --- fixtures -------------------------------------------------------------

# A stamped Cardputer GPS logger STILL carrying a downloads: line -> must be stripped.
FW_WITH_DOWNLOADS_MD = """---
id: cardputer-gps-logger
type: firmware
name: Cardputer GPS Logger
url: https://github.com/devuser/cardputer-gps-logger
category: multi
popularity:
  stars: 30
  downloads: 4200
  forks: 6
  as_of: '2026-09-01'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-gps-logger
  verified: '2026-09-01'
- field: popularity
  url: https://github.com/devuser/cardputer-gps-logger
  verified: '2026-09-01'
---

# Cardputer GPS Logger
"""

# A badusb tool already migrated (no downloads: line) -> must be left untouched (idempotent).
FW_ALREADY_CLEAN_MD = """---
id: cardputer-badusb-tool
type: firmware
name: Cardputer BadUSB Tool
url: https://github.com/devuser/cardputer-badusb-tool
category: badusb
popularity:
  stars: 55
  forks: 12
  as_of: '2026-09-01'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-badusb-tool
  verified: '2026-09-01'
- field: popularity
  url: https://github.com/devuser/cardputer-badusb-tool
  verified: '2026-09-01'
---

# Cardputer BadUSB Tool
"""

# An unstamped entry with no popularity block at all -> must be left untouched, never crash.
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

# A legacy entry whose sources array ALSO carries a downloads-only citation -> that source entry
# must be removed too (SPEC: "if a popularity source entry referenced only downloads, remove it").
FW_WITH_DOWNLOADS_SOURCE_MD = """---
id: cardputer-mesh-relay
type: firmware
name: Cardputer Mesh Relay
url: https://github.com/devuser/cardputer-mesh-relay
category: mesh
popularity:
  stars: 8
  downloads: 900
  forks: 2
  as_of: '2026-09-01'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-mesh-relay
  verified: '2026-09-01'
- field: downloads
  url: https://github.com/devuser/cardputer-mesh-relay
  verified: '2026-09-01'
---

# Cardputer Mesh Relay
"""


def _write_firmware(data_root, fw_id, text):
    p = data_root / "firmware" / fw_id / "firmware.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _fm(path):
    return yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])


# --- tests ----------------------------------------------------------------

def test_strips_downloads_line_and_keeps_stars_forks_as_of(tmp_path):
    path = _write_firmware(tmp_path, "cardputer-gps-logger", FW_WITH_DOWNLOADS_MD)

    result = migration.strip_downloads(tmp_path)

    assert result["stripped"] == ["cardputer-gps-logger"]
    assert result["skipped"] == []
    fm = _fm(path)
    assert fm["popularity"] == {"stars": 30, "forks": 6, "as_of": "2026-09-01"}
    assert "downloads" not in fm["popularity"]


def test_already_clean_entry_is_skipped_not_rewritten(tmp_path):
    path = _write_firmware(tmp_path, "cardputer-badusb-tool", FW_ALREADY_CLEAN_MD)
    before = path.read_text(encoding="utf-8")

    result = migration.strip_downloads(tmp_path)

    assert result["stripped"] == []
    assert result["skipped"] == ["cardputer-badusb-tool"]
    assert path.read_text(encoding="utf-8") == before


def test_unstamped_entry_left_untouched_and_does_not_crash(tmp_path):
    path = _write_firmware(tmp_path, "cardputer-repl", FW_UNSTAMPED_MD)
    before = path.read_text(encoding="utf-8")

    result = migration.strip_downloads(tmp_path)

    assert result["stripped"] == []
    assert result["skipped"] == ["cardputer-repl"]
    assert path.read_text(encoding="utf-8") == before


def test_removes_a_downloads_only_source_entry(tmp_path):
    path = _write_firmware(tmp_path, "cardputer-mesh-relay", FW_WITH_DOWNLOADS_SOURCE_MD)

    migration.strip_downloads(tmp_path)

    fm = _fm(path)
    assert not any(s["field"] == "downloads" for s in fm["sources"])
    assert any(s["field"] == "*" for s in fm["sources"])


def test_migration_is_idempotent_running_twice_is_a_noop_second_time(tmp_path):
    path = _write_firmware(tmp_path, "cardputer-gps-logger", FW_WITH_DOWNLOADS_MD)

    first = migration.strip_downloads(tmp_path)
    after_first = path.read_text(encoding="utf-8")
    second = migration.strip_downloads(tmp_path)
    after_second = path.read_text(encoding="utf-8")

    assert first["stripped"] == ["cardputer-gps-logger"]
    assert second["stripped"] == []
    assert second["skipped"] == ["cardputer-gps-logger"]
    assert after_first == after_second


def test_mixed_catalog_only_touches_entries_that_still_carry_downloads(tmp_path):
    _write_firmware(tmp_path, "cardputer-gps-logger", FW_WITH_DOWNLOADS_MD)
    _write_firmware(tmp_path, "cardputer-badusb-tool", FW_ALREADY_CLEAN_MD)
    _write_firmware(tmp_path, "cardputer-repl", FW_UNSTAMPED_MD)

    result = migration.strip_downloads(tmp_path)

    assert result["stripped"] == ["cardputer-gps-logger"]
    assert set(result["skipped"]) == {"cardputer-badusb-tool", "cardputer-repl"}


def test_cli_main_runs_and_prints_summary(tmp_path, capsys):
    _write_firmware(tmp_path, "cardputer-gps-logger", FW_WITH_DOWNLOADS_MD)

    exit_code = migration.main(["--data-dir", str(tmp_path)])

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "DOWNLOADS-STRIP" in out
    assert "cardputer-gps-logger" in out
