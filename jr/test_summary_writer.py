"""EspAtlas Jr — pytest for jr/summary_writer.py. Fixtures are real catalog-style firmware.md
text (matching what jr/tools.author_firmware_record actually puts on disk).

Run: cd jr && python3 -m pytest test_summary_writer.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import summary_writer as sw  # noqa: E402

TODAY = "2026-09-20"

NO_SUMMARY_MD = """---
id: draftling
type: firmware
name: draftling
url: https://github.com/clackups/draftling
category: multi
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/clackups/draftling
  verified: '2026-09-07'
maintainer: clackups
---

Admitted by jr/scorer.py rule authored.
"""

WITH_SUMMARY_MD = """---
id: draftling
type: firmware
name: draftling
url: https://github.com/clackups/draftling
category: multi
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/clackups/draftling
  verified: '2026-09-07'
- field: summary
  url: https://github.com/clackups/draftling
  verified: '2026-09-19'
maintainer: clackups
summary: Draftling is a firmware for drafting things.
readme_lang: en
readme_sha: abc123
---

Admitted by jr/scorer.py rule authored.
"""


def test_readme_sha256_is_stable_and_content_addressed():
    a = sw.readme_sha256("hello world")
    b = sw.readme_sha256("hello world")
    c = sw.readme_sha256("hello world!")
    assert a == b
    assert a != c
    assert len(a) == 64


def test_update_summary_writes_missing_fields_and_source():
    result = sw.update_summary(
        NO_SUMMARY_MD, summary="Draftling is a firmware for drafting things.",
        readme_lang="en", readme_sha="abc123",
        readme_url="https://github.com/clackups/draftling", today=TODAY,
    )

    assert result["changed"] is True
    fm, _ = sw._split(result["text"])
    assert fm["summary"] == "Draftling is a firmware for drafting things."
    assert fm["readme_lang"] == "en"
    assert fm["readme_sha"] == "abc123"
    summary_sources = [s for s in fm["sources"] if s.get("field") == "summary"]
    assert summary_sources == [{"field": "summary", "url": "https://github.com/clackups/draftling",
                                 "verified": TODAY}]


def test_update_summary_does_not_disturb_other_fields_or_the_body():
    result = sw.update_summary(
        NO_SUMMARY_MD, summary="Draftling is a firmware for drafting things.",
        readme_lang="en", readme_sha="abc123",
        readme_url="https://github.com/clackups/draftling", today=TODAY,
    )

    fm, body = sw._split(result["text"])
    old_fm, old_body = sw._split(NO_SUMMARY_MD)
    assert body == old_body
    untouched_keys = {"summary", "readme_lang", "readme_sha", "sources"}
    assert {k: v for k, v in fm.items() if k not in untouched_keys} \
        == {k: v for k, v in old_fm.items() if k not in untouched_keys}


def test_update_summary_replaces_rather_than_duplicates_the_summary_source():
    result = sw.update_summary(
        WITH_SUMMARY_MD, summary="A refreshed synopsis after the README changed.",
        readme_lang="en", readme_sha="def456",
        readme_url="https://github.com/clackups/draftling", today=TODAY,
    )

    fm, _ = sw._split(result["text"])
    summary_sources = [s for s in fm["sources"] if s.get("field") == "summary"]
    assert len(summary_sources) == 1
    assert summary_sources[0]["verified"] == TODAY


def test_update_summary_is_byte_stable_on_a_no_op():
    first = sw.update_summary(
        NO_SUMMARY_MD, summary="Draftling is a firmware for drafting things.",
        readme_lang="en", readme_sha="abc123",
        readme_url="https://github.com/clackups/draftling", today=TODAY,
    )
    assert first["changed"] is True

    second = sw.update_summary(
        first["text"], summary="Draftling is a firmware for drafting things.",
        readme_lang="en", readme_sha="abc123",
        readme_url="https://github.com/clackups/draftling", today=TODAY,
    )

    assert second == {"text": first["text"], "changed": False, "reason": "up_to_date"}


def test_update_summary_empty_summary_is_a_no_op():
    result = sw.update_summary(
        NO_SUMMARY_MD, summary="", readme_lang="en", readme_sha="abc123",
        readme_url="https://github.com/clackups/draftling", today=TODAY,
    )

    assert result == {"text": NO_SUMMARY_MD, "changed": False, "reason": "no_summary"}


def test_write_readme_en_creates_the_file_with_a_trailing_newline(tmp_path):
    firmware_dir = tmp_path / "draftling"

    path = sw.write_readme_en(firmware_dir, "# Draftling\n\nTranslated body.")

    assert path == firmware_dir / "readme.en.md"
    assert path.read_text(encoding="utf-8") == "# Draftling\n\nTranslated body.\n"


def test_write_readme_en_does_not_double_the_trailing_newline(tmp_path):
    firmware_dir = tmp_path / "draftling"

    path = sw.write_readme_en(firmware_dir, "# Draftling\n\nTranslated body.\n")

    assert path.read_text(encoding="utf-8") == "# Draftling\n\nTranslated body.\n"
