"""Tests for scripts/firmware_floor_audit.py — the OFFLINE firmware popularity-floor audit + CI gate.

TDD, no network: the audit reads the STORED `popularity` block from frontmatter and never fetches.
The floor is GitHub stars OR forks OR an independent editorial home OR a PERSISTED launcher
download count >= DOWNLOAD_FLOOR (SPEC-firmware-floor.md — the fourth signal, restored so the
M5Launcher/Evil-Cardputer/Doom-for-Cardputer class of 1-star-but-tens-of-thousands-of-installs
firmware isn't wrongly floored). Uses a small temp fixture data dir with coding-domain ESP32
example firmware (an on-device dev tool, a code editor), never lorem ipsum. Mirrors
scripts/test_data_completion.py's tmp_path fixture-writing convention.

Run: python3 -m pytest scripts/test_firmware_floor_audit.py -q
"""
from __future__ import annotations

import firmware_floor_audit as audit

# --- fixtures -------------------------------------------------------------

# A non-curated coding firmware STAMPED sub-floor (3 stars, 1 fork) -> flagged.
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

# A non-curated coding firmware STAMPED above the floor via forks (12 stars but 30 forks — a
# heavily built-on but under-starred utility) -> NOT flagged.
FW_POPULAR_MD = """---
id: cardputer-code-editor
type: firmware
name: Cardputer Code Editor
url: https://github.com/devuser/cardputer-code-editor
category: multi
popularity:
  stars: 12
  forks: 30
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

# A non-curated coding firmware STAMPED below both GitHub floors (1 star, 0 forks) but with a
# PERSISTED launcher download count clearing DOWNLOAD_FLOOR (the M5Launcher class) -> NOT flagged.
FW_HIGH_DOWNLOAD_MD = """---
id: cardputer-launcher-clone
type: firmware
name: Cardputer Launcher Clone
url: https://github.com/devuser/cardputer-launcher-clone
category: multi
popularity:
  stars: 1
  forks: 0
  downloads: 2000
  as_of: '2026-09-01'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-launcher-clone
  verified: '2026-09-01'
- field: popularity
  url: https://github.com/devuser/cardputer-launcher-clone
  verified: '2026-09-01'
---

# Cardputer Launcher Clone
"""

# Same shape, but the persisted download count sits ONE below DOWNLOAD_FLOOR with zero stars and
# zero forks -> still flagged (the threshold resists trivial gaming).
FW_LOW_DOWNLOAD_MD = """---
id: cardputer-filler-clone
type: firmware
name: Cardputer Filler Clone
url: https://github.com/devuser/cardputer-filler-clone
category: multi
popularity:
  stars: 0
  forks: 0
  downloads: 1999
  as_of: '2026-09-01'
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/devuser/cardputer-filler-clone
  verified: '2026-09-01'
- field: popularity
  url: https://github.com/devuser/cardputer-filler-clone
  verified: '2026-09-01'
---

# Cardputer Filler Clone
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


def test_above_floor_via_forks_is_not_flagged(tmp_path):
    """(c) A stored entry with 12 stars but 30 forks clears the floor -> not flagged, --ci ok."""
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


# --- CURATED_EXEMPT integrity (Phase 0 PR 0.4) ----------------------------

def test_curated_exempt_ids_exist():
    """Every id in CURATED_EXEMPT must resolve to a real record in the REAL data dir.

    This is the inverse of the rogueduck incident. On 2026-09-02 a floor purge deleted
    data/firmware/rogueduck/ even though "rogueduck" is named here as curated-exempt, and main
    stayed red for six runs. The audit itself could not notice: it iterates over records that
    exist, so an exempt id naming a record that has been deleted is invisible to it.

    A failure here means one of two things, and both want a human:
      - a curated record was deleted and should be restored, or
      - the record was retired on purpose and its id should leave CURATED_EXEMPT.
    """
    from pathlib import Path

    data_dir = Path(__file__).resolve().parent.parent / "data" / "firmware"
    missing = sorted(fid for fid in audit.CURATED_EXEMPT if not (data_dir / fid / "firmware.md").exists())
    assert not missing, (
        f"CURATED_EXEMPT names {len(missing)} firmware with no record: {missing}. "
        "Either restore the record or drop the id from the exempt list."
    )

def test_stored_download_count_clears_the_floor_even_at_one_star(tmp_path):
    """M5Launcher class: 1 star, 0 forks — below both GitHub floors — but a PERSISTED launcher
    download count >= DOWNLOAD_FLOOR (the fourth signal) clears it, offline, from stored data
    alone. The audited entry's dict carries the persisted count."""
    _write_firmware(tmp_path, "cardputer-launcher-clone", FW_HIGH_DOWNLOAD_MD)

    report = audit.audit(tmp_path)
    entry = next(e for e in report["entries"] if e["id"] == "cardputer-launcher-clone")
    assert entry["downloads"] == 2000
    assert entry["below_floor"] is False
    assert report["flagged"] == []


def test_stored_download_count_one_under_the_floor_with_zero_stars_still_flags(tmp_path):
    """The threshold resists trivial gaming: 1999 downloads and zero stars/forks stays filler."""
    _write_firmware(tmp_path, "cardputer-filler-clone", FW_LOW_DOWNLOAD_MD)

    report = audit.audit(tmp_path)
    flagged_ids = {e["id"] for e in report["flagged"]}
    assert flagged_ids == {"cardputer-filler-clone"}
    assert audit.main(["--data-dir", str(tmp_path), "--ci"]) == 1


# --- one floor, one definition (Phase 1 PR 1.3) ---------------------------

def test_audit_and_scorer_share_one_floor_definition():
    """The CI gate and the drain must read the SAME constants, not two copies that agree today.

    Three floors once coexisted here: the spec said stars-or-downloads, jr/scorer.py said
    stars-or-downloads-or-forks, and this audit re-typed the scorer's values by hand under a
    comment admitting they were "kept in sync by hand". Hand-sync is not sync — it lets the
    thing that BLOCKS a merge and the thing that AUTHORS a record disagree about what qualifies.

    Identity, not equality: `==` would still pass if someone re-typed 25 in both places, which
    is precisely the failure mode being prevented.
    """
    import sys
    from pathlib import Path

    jr_dir = Path(__file__).resolve().parent.parent / "jr"
    if str(jr_dir) not in sys.path:
        sys.path.insert(0, str(jr_dir))
    import scorer
    from esp_atlas_core import floor

    assert audit.STAR_FLOOR is floor.STAR_FLOOR
    assert audit.FORK_FLOOR is floor.FORK_FLOOR
    assert audit.DOWNLOAD_FLOOR is floor.DOWNLOAD_FLOOR
    assert scorer.STAR_FLOOR is floor.STAR_FLOOR
    assert scorer.FORK_FLOOR is floor.FORK_FLOOR
    assert audit.clears_popularity_floor is floor.clears_popularity_floor
    assert scorer.clears_popularity_floor is floor.clears_popularity_floor


def test_download_floor_is_defined_once_in_esp_atlas_core():
    """DOWNLOAD_FLOOR (the restored fourth signal) lives in esp_atlas_core.floor ONLY — the same
    module whose STAR_FLOOR/FORK_FLOOR this audit and jr/scorer.py already share, so the fourth
    signal can't drift the way the first three once did."""
    from esp_atlas_core import floor

    assert floor.DOWNLOAD_FLOOR == 2000
