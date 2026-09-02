"""EspAtlas Jr — pytest for jr/normalize.py, the conservative title-banner sanitizer.

Covers the recently-seen bug: a scraped firmware `name` field carrying a GitHub repo-status
banner instead of (or alongside) the real app name, e.g. a firmware.md authored with
name: "【Maintenance completed】AIｽﾀｯｸﾁｬﾝ2" (the actual bad record: data/firmware/
ai-stackchan2-readme/firmware.md, repo robo8080/AI_StackChan2_README). Fixtures below are real
catalog-style firmware names from the esp-atlas domain (Cardputer/M5Stack/ESP32 tools), never
placeholder text.

Run: cd jr && python3 -m pytest test_normalize.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import normalize  # noqa: E402
from normalize import sanitize_firmware_name, sweep_firmware_names  # noqa: E402


# ─────────────────────────── sanitize_firmware_name ───────────────────────────

def test_real_bug_case_collapses_to_app_name():
    """The actual bad record that motivated this module: a leading 【Maintenance completed】
    repo-status banner, fullwidth-bracketed, in front of the real (katakana) app name."""
    assert sanitize_firmware_name(
        "【Maintenance completed】AIｽﾀｯｸﾁｬﾝ2"
    ) == "AIｽﾀｯｸﾁｬﾝ2"


def test_wip_deprecated_prefix_is_stripped():
    """A single bracket carrying two banner tokens, ASCII square brackets, leading position."""
    assert sanitize_firmware_name("[WIP DEPRECATED] Cardputer Marauder") == "Cardputer Marauder"


def test_stacked_double_banner_fully_stripped():
    """Two separate leading banner brackets stack; both must be removed, one pass each,
    with the separator left behind trimmed too."""
    assert sanitize_firmware_name("[Archived] (Deprecated) Bruce Firmware") == "Bruce Firmware"


def test_real_bracket_content_is_preserved():
    """A bracket whose inner text is a REAL, non-banner part of the name (a chip variant here)
    must never be stripped — conservative by default."""
    assert sanitize_firmware_name("Cardputer Marauder (ESP32-S3)") == "Cardputer Marauder (ESP32-S3)"


def test_already_clean_name_passes_through_unchanged():
    assert sanitize_firmware_name("Bruce") == "Bruce"


def test_trailing_banner_bracket_is_stripped():
    assert sanitize_firmware_name("M5Cardputer ADV Launcher [BETA]") == "M5Cardputer ADV Launcher"


def test_fullwidth_bracket_variant_is_stripped():
    assert sanitize_firmware_name("［WIP］ M5Stick Shark") == "M5Stick Shark"


def test_fullwidth_paren_variant_is_stripped():
    assert sanitize_firmware_name("（notice） CardNet") == "CardNet"


def test_japanese_kanji_banner_word_is_stripped():
    assert sanitize_firmware_name("【完了】AirMouseS3") == "AirMouseS3"  # 完了


def test_japanese_katakana_maintenance_word_is_stripped():
    assert sanitize_firmware_name("【メンテナンス】Bitmap16dx") == "Bitmap16dx"  # メンテナンス


def test_multiword_phrase_work_in_progress_is_stripped():
    assert sanitize_firmware_name("(work in progress) AnarchCardputer") == "AnarchCardputer"


def test_multiword_phrase_end_of_life_is_stripped():
    assert sanitize_firmware_name("BadCard [end of life]") == "BadCard"


def test_empty_and_none_are_returned_unchanged():
    assert sanitize_firmware_name("") == ""


def test_idempotent_on_already_sanitized_name():
    once = sanitize_firmware_name("【Maintenance completed】AdvanceOS")
    twice = sanitize_firmware_name(once)
    assert once == twice == "AdvanceOS"


def test_case_insensitive_vocabulary_match():
    assert sanitize_firmware_name("[Wip] CardputerLoraChat") == "CardputerLoraChat"
    assert sanitize_firmware_name("[wip] CardputerLoraChat") == "CardputerLoraChat"


def test_non_banner_middle_bracket_is_not_touched():
    """A bracket in the MIDDLE of the name (neither leading nor trailing) is never a
    candidate for stripping, even if the whole name superficially resembles a banner."""
    assert sanitize_firmware_name("Cardputer [Marauder] Edition") == "Cardputer [Marauder] Edition"


def test_empty_bracket_is_not_treated_as_banner():
    assert sanitize_firmware_name("[] Bruce") == "[] Bruce"


def test_concatenated_japanese_banner_words_no_space_are_stripped():
    """メンテナンス完了 ('maintenance completed') has no ASCII space between the two CJK
    banner words — the whitespace tokenizer alone wouldn't catch it."""
    assert sanitize_firmware_name("【メンテナンス完了】Bitmap16dx") == "Bitmap16dx"


# ─────────────────────────── sweep_firmware_names ───────────────────────────

def _write_firmware(root: Path, fid: str, name: str) -> Path:
    d = root / "firmware" / fid
    d.mkdir(parents=True)
    path = d / "firmware.md"
    fm = {
        "id": fid, "type": "firmware", "name": name,
        "url": f"https://github.com/example/{fid}", "category": "multi",
        "socs": ["esp32-s3"],
        "sources": [{"field": "*", "url": f"https://github.com/example/{fid}",
                     "verified": "2026-08-27"}],
    }
    front = yaml.safe_dump(fm, sort_keys=False, default_flow_style=False, allow_unicode=True).strip()
    path.write_text(f"---\n{front}\n---\n\nBody text for {fid}.\n")
    return path


def test_sweep_rewrites_only_changed_names(tmp_path):
    _write_firmware(tmp_path, "ai-stackchan2-readme",
                     "【Maintenance completed】AIｽﾀｯｸﾁｬﾝ2")
    _write_firmware(tmp_path, "bruce", "Bruce")

    report = sweep_firmware_names(data_root=tmp_path)

    assert report["changed"] == [
        {"id": "ai-stackchan2-readme", "old": "【Maintenance completed】AIｽﾀｯｸﾁｬﾝ2",
         "new": "AIｽﾀｯｸﾁｬﾝ2"}
    ]
    assert report["unchanged"] == 1

    fm_text = (tmp_path / "firmware" / "ai-stackchan2-readme" / "firmware.md").read_text()
    assert "Maintenance completed" not in fm_text
    assert "AIｽﾀｯｸﾁｬﾝ2" in fm_text


def test_sweep_is_idempotent_second_run_is_noop(tmp_path):
    _write_firmware(tmp_path, "ai-stackchan2-readme",
                     "【Maintenance completed】AIｽﾀｯｸﾁｬﾝ2")

    first = sweep_firmware_names(data_root=tmp_path)
    second = sweep_firmware_names(data_root=tmp_path)

    assert len(first["changed"]) == 1
    assert second["changed"] == []
    assert second["unchanged"] == 1


def test_sweep_preserves_other_frontmatter_fields(tmp_path):
    path = _write_firmware(tmp_path, "cardnet", "（notice） CardNet")
    sweep_firmware_names(data_root=tmp_path)
    fm_text = path.read_text()
    assert "id: cardnet" in fm_text
    assert "category: multi" in fm_text
    assert "url: https://github.com/example/cardnet" in fm_text


def test_sweep_reports_no_firmware_dir_gracefully(tmp_path):
    report = sweep_firmware_names(data_root=tmp_path / "does-not-exist")
    assert report == {"changed": [], "unchanged": 0}


def test_main_prints_sweep_summary(tmp_path, monkeypatch, capsys):
    _write_firmware(tmp_path, "ai-stackchan2-readme",
                     "【Maintenance completed】AIｽﾀｯｸﾁｬﾝ2")
    monkeypatch.setattr(normalize, "FIRMWARE_DIR", tmp_path / "firmware")
    normalize.main()
    out = capsys.readouterr().out
    assert "ai-stackchan2-readme" in out
    assert "1 changed, 0 unchanged" in out
