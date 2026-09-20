"""EspAtlas Jr — pytest for jr/backfill_popularity.py (pure rewrite; `main()` never runs here —
see its own guard). Fixtures are real catalog-style firmware.md text (matching what
jr/writers.render_firmware and jr/tools.author_firmware_record actually put on disk), never
lorem/animal placeholders. `api` is always a hand-built fake — no network call ever happens in
this file.

Run: cd jr && python3 -m pytest test_backfill_popularity.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backfill_popularity as bp  # noqa: E402

TODAY = "2026-09-20"

# draftling: the bug's actual fingerprint — a `field: popularity` source citation already sits
# there from admission time, but the popularity block itself never got written (forks was None).
NO_POP_MD = """---
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
- field: popularity
  url: https://github.com/clackups/draftling
  verified: '2026-09-07'
maintainer: clackups
---

Admitted by jr/scorer.py rule authored.
"""

# advanceos-for-cardputer: stars only, stale as_of — the other half of the fingerprint.
STARS_ONLY_MD = """---
id: advanceos-for-cardputer
type: firmware
name: AdvanceOS For Cardputer ADV
url: https://github.com/bomberman30/AdvanceOS-for-cardputer
category: multi
maintainer: bomberman30
capabilities:
- ir
- wifi
socs:
- esp32-s3
popularity:
  stars: 89
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/bomberman30/AdvanceOS-for-cardputer
  verified: '2026-08-27'
- field: popularity
  url: https://github.com/bomberman30/AdvanceOS-for-cardputer
  verified: '2026-09-01'
---

AdvanceOS is software for cardputerADV.
"""

# area512: already fully backfilled — the idempotent no-op case.
BOTH_CURRENT_MD = """---
id: area512
type: firmware
name: Area512 for Cardputer ADV
url: https://github.com/engneer-hamachan/area512
category: multi
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/engneer-hamachan/area512
  verified: '2026-09-19'
- field: popularity
  url: https://github.com/engneer-hamachan/area512
  verified: '2026-09-19'
maintainer: engneer-hamachan
popularity:
  stars: 59
  forks: 6
  as_of: '2026-09-19'
---

Admitted by jr/scorer.py rule authored.
"""


def _fake_api(mapping: dict) -> callable:
    """mapping: {"owner/repo": <raw gh api repos/OWNER/REPO shape>}. Missing keys -> {} (mirrors
    default_api's own unresolved-repo return: 404/deleted/gh failure)."""
    def _api(owner: str, repo: str) -> dict:
        return mapping.get(f"{owner}/{repo}", {})
    return _api


# ─────────────────────────── repo_owner_and_name ───────────────────────────

def test_repo_owner_and_name_parses_a_bare_github_url():
    assert bp.repo_owner_and_name("https://github.com/clackups/draftling") == ("clackups", "draftling")


def test_repo_owner_and_name_none_for_anything_else():
    assert bp.repo_owner_and_name("https://gitlab.com/clackups/draftling") is None
    assert bp.repo_owner_and_name("") is None
    assert bp.repo_owner_and_name(None) is None


# ─────────────────────────── update_popularity ───────────────────────────

def test_update_popularity_writes_missing_block_stars_and_forks_known():
    data = {"full_name": "clackups/draftling", "stargazers_count": 12, "forks_count": 3}
    result = bp.update_popularity(NO_POP_MD, data, TODAY)
    assert result["changed"] is True
    fm, _ = bp._split(result["text"])
    assert fm["popularity"] == {"stars": 12, "forks": 3, "as_of": TODAY}
    # the sources[] popularity citation already existed — not duplicated
    pop_sources = [s for s in fm["sources"] if s.get("field") == "popularity"]
    assert len(pop_sources) == 1


def test_update_popularity_adds_missing_sources_entry_when_absent():
    no_source_md = NO_POP_MD.replace(
        "- field: popularity\n  url: https://github.com/clackups/draftling\n  verified: '2026-09-07'\n", "")
    data = {"full_name": "clackups/draftling", "stargazers_count": 12, "forks_count": 3}
    result = bp.update_popularity(no_source_md, data, TODAY)
    fm, _ = bp._split(result["text"])
    pop_sources = [s for s in fm["sources"] if s.get("field") == "popularity"]
    assert pop_sources == [{"field": "popularity", "url": "https://github.com/clackups/draftling",
                            "verified": TODAY}]


def test_update_popularity_fills_the_missing_forks_without_disturbing_other_fields():
    data = {"full_name": "bomberman30/AdvanceOS-for-cardputer", "stargazers_count": 91, "forks_count": 5}
    result = bp.update_popularity(STARS_ONLY_MD, data, TODAY)
    assert result["changed"] is True
    fm, body = bp._split(result["text"])
    assert fm["popularity"] == {"stars": 91, "forks": 5, "as_of": TODAY}
    old_fm, old_body = bp._split(STARS_ONLY_MD)
    assert body == old_body
    assert {k: v for k, v in fm.items() if k != "popularity"} == {k: v for k, v in old_fm.items() if k != "popularity"}


def test_update_popularity_is_idempotent_when_already_current():
    data = {"full_name": "engneer-hamachan/area512", "stargazers_count": 59, "forks_count": 6}
    result = bp.update_popularity(BOTH_CURRENT_MD, data, "2026-09-19")
    assert result == {"text": BOTH_CURRENT_MD, "changed": False, "reason": "up_to_date"}


def test_update_popularity_refreshes_as_of_when_counts_change_even_if_stable():
    data = {"full_name": "engneer-hamachan/area512", "stargazers_count": 60, "forks_count": 6}
    result = bp.update_popularity(BOTH_CURRENT_MD, data, TODAY)
    assert result["changed"] is True
    fm, _ = bp._split(result["text"])
    assert fm["popularity"] == {"stars": 60, "forks": 6, "as_of": TODAY}


def test_update_popularity_unresolved_repo_leaves_the_file_untouched():
    result = bp.update_popularity(NO_POP_MD, {}, TODAY)
    assert result == {"text": NO_POP_MD, "changed": False, "reason": "unresolved"}


def test_update_popularity_partial_signal_still_persists_what_is_known():
    """Same fix as the writer: a repo that (for whatever reason) reports stars but no numeric
    forks must not lose the stars."""
    data = {"full_name": "clackups/draftling", "stargazers_count": 12, "forks_count": None}
    result = bp.update_popularity(NO_POP_MD, data, TODAY)
    fm, _ = bp._split(result["text"])
    assert fm["popularity"] == {"stars": 12, "as_of": TODAY}
    assert "forks" not in fm["popularity"]


# ─────────────────────────── backfill() (dry-run vs write), offline ───────────────────────────

def _write_firmware(firmware_dir, fw_id, text):
    """`firmware_dir` is a data/firmware-shaped root — the same thing `bp.backfill`'s
    `data_dir` param names (NOT the repo's data/ root; there's only one content type here)."""
    p = firmware_dir / fw_id / "firmware.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_backfill_dry_run_reports_without_writing(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_POP_MD)

    result = bp.backfill(
        tmp_path,
        api=_fake_api({"clackups/draftling": {"full_name": "clackups/draftling",
                                               "stargazers_count": 12, "forks_count": 3}}),
        today=TODAY, dry_run=True,
    )

    assert result["updated"] == ["draftling"]
    assert path.read_text(encoding="utf-8") == NO_POP_MD


def test_backfill_without_dry_run_writes_the_file(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_POP_MD)

    result = bp.backfill(
        tmp_path,
        api=_fake_api({"clackups/draftling": {"full_name": "clackups/draftling",
                                               "stargazers_count": 12, "forks_count": 3}}),
        today=TODAY,
    )

    assert result["updated"] == ["draftling"]
    fm, _ = bp._split(path.read_text(encoding="utf-8"))
    assert fm["popularity"] == {"stars": 12, "forks": 3, "as_of": TODAY}


def test_backfill_skips_a_404_repo_without_touching_the_file(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_POP_MD)

    result = bp.backfill(tmp_path, api=_fake_api({}), today=TODAY)   # every lookup -> {} (404/deleted)

    assert result["updated"] == []
    assert result["skipped"] == [("draftling", "repo unresolved (404 / deleted / gh failure)")]
    assert path.read_text(encoding="utf-8") == NO_POP_MD


def test_backfill_skips_a_renamed_repo_without_touching_the_file(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_POP_MD)

    # gh api follows GitHub's rename redirect and still answers 200 under the new full_name.
    result = bp.backfill(
        tmp_path,
        api=_fake_api({"clackups/draftling": {"full_name": "someoneelse/draftling-renamed",
                                              "stargazers_count": 12, "forks_count": 3}}),
        today=TODAY,
    )

    assert result["updated"] == []
    assert result["skipped"] == [("draftling", "repo renamed to someoneelse/draftling-renamed")]
    assert path.read_text(encoding="utf-8") == NO_POP_MD


def test_backfill_is_idempotent_across_two_runs(tmp_path):
    path = _write_firmware(tmp_path, "draftling", NO_POP_MD)
    api = _fake_api({"clackups/draftling": {"full_name": "clackups/draftling",
                                            "stargazers_count": 12, "forks_count": 3}})

    first = bp.backfill(tmp_path, api=api, today=TODAY)
    text_after_first = path.read_text(encoding="utf-8")
    second = bp.backfill(tmp_path, api=api, today=TODAY)

    assert first["updated"] == ["draftling"]
    assert second["updated"] == []
    assert second["unchanged"] == ["draftling"]
    assert path.read_text(encoding="utf-8") == text_after_first
