"""EspAtlas Jr — pytest for jr/backfill_summary.py. `fetch_readme` and `client` are always
hand-built fakes — no test in this file ever reaches the network or real Groq.

Run: cd jr && python3 -m pytest test_backfill_summary.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backfill_summary as bs  # noqa: E402
import summary_writer as sw  # noqa: E402

TODAY = "2026-09-20"
DRAFTLING_URL = "https://github.com/clackups/draftling"

NO_SUMMARY_MD = f"""---
id: draftling
type: firmware
name: draftling
url: {DRAFTLING_URL}
category: multi
socs:
- esp32-s3
sources:
- field: '*'
  url: {DRAFTLING_URL}
  verified: '2026-09-07'
maintainer: clackups
---

Admitted by jr/scorer.py rule authored.
"""

ENGLISH_README = "# Draftling\n\nDraftling is a firmware for drafting things on an ESP32-S3."
JAPANESE_README = "# ドラフトリング\n\nESP32-S3用のドラフトファームウェアです。"


def _fake_fetch_readme(mapping: dict) -> callable:
    """mapping: {"owner/repo": readme text or None}. Missing keys -> None (unresolved)."""
    def _fetch(owner: str, repo: str):
        return mapping.get(f"{owner}/{repo}")
    return _fetch


def _fake_groq_client(reply: dict) -> callable:
    def _client(system_prompt: str, user_prompt: str) -> str:
        return json.dumps(reply)
    return _client


def _write_firmware(firmware_dir, fw_id, text):
    p = firmware_dir / fw_id / "firmware.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# ─────────────────────────── repo_owner_and_name ───────────────────────────

def test_repo_owner_and_name_parses_a_bare_github_url():
    assert bs.repo_owner_and_name(DRAFTLING_URL) == ("clackups", "draftling")


def test_repo_owner_and_name_none_for_anything_else():
    assert bs.repo_owner_and_name("https://gitlab.com/clackups/draftling") is None
    assert bs.repo_owner_and_name("") is None
    assert bs.repo_owner_and_name(None) is None


# ─────────────────────────── backfill(): writes ───────────────────────────

def test_backfill_writes_summary_and_no_translation_for_an_english_readme(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_SUMMARY_MD)

    result = bs.backfill(
        tmp_path,
        fetch_readme=_fake_fetch_readme({"clackups/draftling": ENGLISH_README}),
        client=_fake_groq_client({
            "summary": "Draftling is a firmware for drafting things on an ESP32-S3.",
            "source_lang": "en", "readme_en": None,
        }),
        today=TODAY,
    )

    assert result["updated"] == ["draftling"]
    fm, _ = sw._split(path.read_text(encoding="utf-8"))
    assert fm["summary"] == "Draftling is a firmware for drafting things on an ESP32-S3."
    assert fm["readme_lang"] == "en"
    assert fm["readme_sha"] == sw.readme_sha256(ENGLISH_README)
    assert not (path.parent / "readme.en.md").exists()


def test_backfill_writes_readme_en_for_a_translated_readme(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_SUMMARY_MD)
    translated = "# Draftling\n\nA drafting firmware for the ESP32-S3."

    result = bs.backfill(
        tmp_path,
        fetch_readme=_fake_fetch_readme({"clackups/draftling": JAPANESE_README}),
        client=_fake_groq_client({
            "summary": "Draftling is a drafting firmware for the ESP32-S3.",
            "source_lang": "ja", "readme_en": translated,
        }),
        today=TODAY,
    )

    assert result["updated"] == ["draftling"]
    fm, _ = sw._split(path.read_text(encoding="utf-8"))
    assert fm["readme_lang"] == "ja"
    readme_en_path = path.parent / "readme.en.md"
    assert readme_en_path.exists()
    assert readme_en_path.read_text(encoding="utf-8") == translated + "\n"


# ─────────────────────────── backfill(): dry-run ───────────────────────────

def test_backfill_dry_run_reports_without_writing(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_SUMMARY_MD)

    result = bs.backfill(
        tmp_path,
        fetch_readme=_fake_fetch_readme({"clackups/draftling": ENGLISH_README}),
        client=_fake_groq_client({
            "summary": "Draftling is a firmware for drafting things on an ESP32-S3.",
            "source_lang": "en", "readme_en": None,
        }),
        today=TODAY, dry_run=True,
    )

    assert result["updated"] == ["draftling"]
    assert path.read_text(encoding="utf-8") == NO_SUMMARY_MD


def test_backfill_dry_run_with_a_translation_does_not_write_readme_en(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_SUMMARY_MD)

    bs.backfill(
        tmp_path,
        fetch_readme=_fake_fetch_readme({"clackups/draftling": JAPANESE_README}),
        client=_fake_groq_client({
            "summary": "A drafting firmware.", "source_lang": "ja",
            "readme_en": "# Draftling\n\nTranslated.",
        }),
        today=TODAY, dry_run=True,
    )

    assert not (path.parent / "readme.en.md").exists()


# ─────────────────────────── backfill(): skips ───────────────────────────

def test_backfill_skips_a_non_github_url(tmp_path):
    non_github_md = NO_SUMMARY_MD.replace(DRAFTLING_URL, "https://gitlab.com/clackups/draftling")
    path = _write_firmware(tmp_path, "draftling", non_github_md)

    result = bs.backfill(tmp_path, fetch_readme=_fake_fetch_readme({}),
                         client=_fake_groq_client({}), today=TODAY)

    assert result["updated"] == []
    assert result["skipped"] == [("draftling", "url is not a bare github.com/owner/repo link")]
    assert path.read_text(encoding="utf-8") == non_github_md


def test_backfill_skips_an_unresolvable_readme(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_SUMMARY_MD)

    result = bs.backfill(tmp_path, fetch_readme=_fake_fetch_readme({}),
                         client=_fake_groq_client({}), today=TODAY)

    assert result["updated"] == []
    assert result["skipped"] == [("draftling", "no resolvable README")]
    assert path.read_text(encoding="utf-8") == NO_SUMMARY_MD


def test_backfill_skips_when_enrichment_returns_no_usable_summary(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_SUMMARY_MD)

    result = bs.backfill(
        tmp_path,
        fetch_readme=_fake_fetch_readme({"clackups/draftling": ENGLISH_README}),
        client=_fake_groq_client({"summary": "", "source_lang": "en", "readme_en": None}),
        today=TODAY,
    )

    assert result["updated"] == []
    assert result["skipped"] == [("draftling", "enrichment returned no usable summary")]
    assert path.read_text(encoding="utf-8") == NO_SUMMARY_MD


# ─────────────────────────── backfill(): idempotence ───────────────────────────

def test_backfill_is_idempotent_and_calls_groq_only_once_across_two_runs(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_SUMMARY_MD)
    call_count = {"n": 0}

    def _counting_client(system_prompt, user_prompt):
        call_count["n"] += 1
        return json.dumps({
            "summary": "Draftling is a firmware for drafting things on an ESP32-S3.",
            "source_lang": "en", "readme_en": None,
        })

    fetch_readme = _fake_fetch_readme({"clackups/draftling": ENGLISH_README})

    first = bs.backfill(tmp_path, fetch_readme=fetch_readme, client=_counting_client, today=TODAY)
    text_after_first = path.read_text(encoding="utf-8")
    second = bs.backfill(tmp_path, fetch_readme=fetch_readme, client=_counting_client, today=TODAY)

    assert first["updated"] == ["draftling"]
    assert second["updated"] == []
    assert second["unchanged"] == ["draftling"]
    assert path.read_text(encoding="utf-8") == text_after_first
    assert call_count["n"] == 1  # the second run's matching readme_sha short-circuits before Groq


def test_backfill_re_enriches_when_the_readme_changes(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_SUMMARY_MD)
    fetch_readme = _fake_fetch_readme({"clackups/draftling": ENGLISH_README})
    client = _fake_groq_client({
        "summary": "Draftling is a firmware for drafting things on an ESP32-S3.",
        "source_lang": "en", "readme_en": None,
    })
    bs.backfill(tmp_path, fetch_readme=fetch_readme, client=client, today=TODAY)

    changed_readme = ENGLISH_README + "\n\nNow with new features."
    result = bs.backfill(
        tmp_path,
        fetch_readme=_fake_fetch_readme({"clackups/draftling": changed_readme}),
        client=_fake_groq_client({
            "summary": "Draftling is a firmware for drafting things, now with new features.",
            "source_lang": "en", "readme_en": None,
        }),
        today="2026-09-21",
    )

    assert result["updated"] == ["draftling"]
    fm, _ = sw._split(path.read_text(encoding="utf-8"))
    assert fm["summary"] == "Draftling is a firmware for drafting things, now with new features."
    assert fm["readme_sha"] == sw.readme_sha256(changed_readme)
