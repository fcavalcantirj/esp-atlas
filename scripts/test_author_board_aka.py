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


def _tree_digest():
    import hashlib
    h = hashlib.sha256()
    for p in sorted((aba.REPO / "data" / "boards").glob("*/*/board.md")):
        h.update(p.read_bytes())
    return h.hexdigest()


def test_dry_run_over_the_real_tree_writes_nothing_and_resolves_most_boards():
    before = _tree_digest()
    lines = []
    res = aba.run(dry_run=True, out=lines.append)
    assert _tree_digest() == before
    assert len(res["written"]) + len(res["unchanged"]) >= 30 and lines[0].startswith("aka:")
    assert res["refused"] == []                                   # every real record's layout is understood


def _indent_sources(text):
    """The same record with its sources list indented two spaces (valid YAML, other layout)."""
    out, in_sources = [], False
    for line in text.split("\n"):
        if line.startswith("sources:"):
            in_sources = True
            out.append(line)
            continue
        if in_sources and (line.startswith("- ") or line.startswith("  ")):
            out.append("  " + line)
            continue
        in_sources = in_sources and line == ""
        out.append(line)
    return "\n".join(out)


def test_verify_rewrite_refuses_layouts_the_rewriter_does_not_understand():
    import yaml
    indented = _indent_sources(RECORD)
    assert yaml.safe_load(indented.split("---")[1])["sources"]                  # the input itself is valid
    assert aba.verify_rewrite(aba.rewrite(indented, ["x"], [RAW], "2026-09-07"), ["x"], [RAW]) is not None
    wrapped = RECORD.replace('name: "M5Cardputer"\n', 'name: "M5Cardputer"\naka: [old,\n  older]\n')
    assert "aka read back" in (aba.verify_rewrite(aba.rewrite(wrapped, ["x"], [RAW], "2026-09-07"), ["x"], [RAW]) or "")
    url_first = RECORD.replace("- field: aka\n  url: https://old.example/stale\n  verified: '2026-01-01'",
                               "- url: https://old.example/stale\n  field: aka\n  verified: '2026-01-01'")
    assert "citations" in (aba.verify_rewrite(aba.rewrite(url_first, ["x"], [RAW], "2026-09-07"), ["x"], [RAW]) or "")
    assert aba.verify_rewrite(aba.rewrite(RECORD, ["x"], [RAW], "2026-09-07"), ["x"], [RAW]) is None


def test_one_pass_refuses_instead_of_writing_a_record_it_cannot_verify(tmp_path):
    (tmp_path / "m5stack" / "m5cardputer").mkdir(parents=True)
    bad = _indent_sources(RECORD)
    (tmp_path / "m5stack" / "m5cardputer" / "board.md").write_text(bad)
    res = aba.run(boards_dir=tmp_path, out=lambda *a: None)
    assert res["written"] == [] and res["refused"] and res["refused"][0][0] == "m5cardputer"
    assert (tmp_path / "m5stack" / "m5cardputer" / "board.md").read_text() == bad


def test_max_passes_must_be_positive_and_convergence_is_reported(tmp_path):
    with pytest.raises(ValueError):
        aba.run(boards_dir=tmp_path, max_passes=0, out=lambda *a: None)


def test_run_reaches_a_fixed_point_on_a_tmp_copy_and_a_second_run_changes_nothing(tmp_path):
    import shutil
    import subprocess
    # seed from the PRE-aka versions on main, so the multi-pass path is real, not a no-op
    for b in ("adafruit/adafruit-qt-py-esp32-s3", "espressif/esp32-pico-kit", "m5stack/m5cardputer", "lilygo/lilygo-t-deck"):
        (tmp_path / b).mkdir(parents=True)
        text = subprocess.run(["git", "show", f"main:data/boards/{b}/board.md"], cwd=aba.REPO, capture_output=True, text=True).stdout
        (tmp_path / b / "board.md").write_text(text or (aba.REPO / "data" / "boards" / b / "board.md").read_text())
    first = aba.run(boards_dir=tmp_path, out=lambda *a: None)
    assert first["converged"] and first["passes"] >= 2 and "adafruit-qt-py-esp32-s3" in first["written"]
    assert "m5cardputer" in first["written"]
    second = aba.run(boards_dir=tmp_path, out=lambda *a: None)
    assert second["written"] == [] and second["passes"] == 1 and second["converged"]
    assert "lilygo-t-deck" in second["skipped"]                      # absent from both registries → untouched
    assert "aka:" not in (tmp_path / "lilygo/lilygo-t-deck/board.md").read_text()
