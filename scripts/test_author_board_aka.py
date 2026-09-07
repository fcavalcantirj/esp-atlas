"""Tests for scripts/author_board_aka.py — the textual `aka:` + `sources[]` rewrite.

All on strings and tmp_path; the real data/ tree is never written. One test runs the real
driver in --dry-run mode over the repo to prove it stays read-only and resolves boards.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import author_board_aka as aba  # noqa: E402

RECORD = """\
---
id: m5cardputer
type: board
brand: m5stack
name: "M5Cardputer"
module: esp32-s3-wroom-1
flash_mb: 8
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/Cardputer
  verified: '2026-08-21'
- field: aka
  url: https://old.example/stale
  verified: '2026-01-01'
- field: io.gpio_pins
  url: https://docs.m5stack.com/en/core/Cardputer
  verified: '2026-08-21'
---

Body text stays exactly as it is, with "quotes" and ç.
"""

RECORD_WITH_AKA = RECORD.replace('name: "M5Cardputer"\n', 'name: "M5Cardputer"\naka:\n- "old alias"\n- "another"\n')
RAW = "https://raw.githubusercontent.com/espressif/arduino-esp32/" + "a" * 40 + "/boards.txt"


def test_rewrite_inserts_aka_after_name_and_cites_each_url_once():
    out = aba.rewrite(RECORD, ["M5Cardputer ADV", "m5stack_cardputer"], [RAW], "2026-09-07")
    fm = out.split("---")[1]
    assert 'name: "M5Cardputer"\naka:\n- "M5Cardputer ADV"\n- "m5stack_cardputer"\nmodule:' in fm
    assert fm.count("- field: aka") == 1                       # the stale aka citation is gone
    assert "https://old.example/stale" not in fm
    assert f"- field: aka\n  url: {RAW}\n  verified: '2026-09-07'" in fm
    # every other source entry and the body survive byte for byte
    assert "- field: '*'\n  url: https://docs.m5stack.com/en/core/Cardputer\n  verified: '2026-08-21'" in fm
    assert "- field: io.gpio_pins" in fm
    assert out.endswith('Body text stays exactly as it is, with "quotes" and ç.\n')


def test_rewrite_replaces_an_existing_aka_block_in_place():
    out = aba.rewrite(RECORD_WITH_AKA, ["fresh"], [RAW], "2026-09-07")
    fm = out.split("---")[1]
    assert "old alias" not in fm and "another" not in fm
    assert 'aka:\n- "fresh"\nmodule:' in fm
    assert fm.count("aka:") == 1


def test_rewrite_is_idempotent():
    once = aba.rewrite(RECORD, ["x", "y"], [RAW, "https://github.com/pioarduino/x/blob/b/boards/x.json"], "2026-09-07")
    twice = aba.rewrite(once, ["x", "y"], [RAW, "https://github.com/pioarduino/x/blob/b/boards/x.json"], "2026-09-07")
    assert once == twice
    assert once.count("- field: aka") == 2


def test_yaml_strings_keep_non_ascii_and_escape_quotes():
    out = aba.rewrite(RECORD, ['AIｽﾀｯｸﾁｬﾝ2', 'say "hi"'], [RAW], "2026-09-07")
    assert '- "AIｽﾀｯｸﾁｬﾝ2"' in out and '- "say \\"hi\\""' in out


def test_aka_for_dedupes_by_compact_form_and_drops_the_boards_own_names():
    board = {"id": "m5cardputer", "name": "M5Cardputer", "aka": [], "soc": "esp32-s3"}
    entries = {
        "arduino-esp32:m5stack_cardputer": {"id": "m5stack_cardputer", "name": "M5Cardputer", "variant": "m5stack_cardputer", "url": RAW},
        "pioarduino:m5stack-cardputer": {"id": "m5stack-cardputer", "name": "M5Stack Cardputer", "variant": "m5stack_cardputer", "url": "https://github.com/p/blob/b/boards/m5stack-cardputer.json"},
        "arduino-esp32:other": {"id": "other", "name": "Other", "variant": "o", "url": RAW},
    }
    table = {"arduino-esp32:m5stack_cardputer": {"atlas_id": "m5cardputer"}, "pioarduino:m5stack-cardputer": {"atlas_id": "m5cardputer"},
             "arduino-esp32:other": {"atlas_id": "somebody-else"}}
    entries["arduino-esp32:m5stack_cardputer"]["board_define"] = "CARDPUTER_ADV"      # unique define → alias
    entries["pioarduino:m5stack-cardputer"]["board_define"] = "ESP32S3_DEV"            # shared generic define → never
    entries["arduino-esp32:other"]["board_define"] = "ESP32S3_DEV"
    entries["arduino-esp32:m5stack_cardputer"]["variant"] = "esp32s3"                # variants are never aka
    aka, urls = aba.aka_for("m5cardputer", board, entries, table)
    assert aka == ["CARDPUTER_ADV", "m5stack_cardputer"]     # own name dropped; the pio id dedups against the arduino id
    assert urls == [RAW, "https://github.com/p/blob/b/boards/m5stack-cardputer.json"]


def test_dry_run_over_the_real_tree_writes_nothing_and_resolves_most_boards():
    import subprocess
    before = subprocess.run(["git", "status", "--porcelain", "--", "data/boards"], cwd=aba.REPO, capture_output=True, text=True).stdout
    lines = []
    res = aba.run(dry_run=True, out=lines.append)
    after = subprocess.run(["git", "status", "--porcelain", "--", "data/boards"], cwd=aba.REPO, capture_output=True, text=True).stdout
    assert before == after
    assert len(res["written"]) + len(res["unchanged"]) >= 30 and lines[0].startswith("aka:")


def test_run_reaches_a_fixed_point_on_a_tmp_copy_and_a_second_run_changes_nothing(tmp_path):
    import shutil
    src = aba.REPO / "data" / "boards"
    for b in ("adafruit/adafruit-qt-py-esp32-s3", "espressif/esp32-pico-kit", "m5stack/m5cardputer", "lilygo/lilygo-t-deck"):
        (tmp_path / b).mkdir(parents=True)
        shutil.copy(src / b / "board.md", tmp_path / b / "board.md")
    first = aba.run(boards_dir=tmp_path, out=lambda *a: None)
    assert first["passes"] >= 1 and "m5cardputer" in first["written"] or "m5cardputer" in first["unchanged"]
    second = aba.run(boards_dir=tmp_path, out=lambda *a: None)
    assert second["written"] == [] and second["passes"] == 1
    assert "lilygo-t-deck" in second["skipped"]                      # absent from both registries → untouched
    assert "aka:" not in (tmp_path / "lilygo/lilygo-t-deck/board.md").read_text()
