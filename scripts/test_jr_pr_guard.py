"""Tests for scripts/jr_pr_guard.py — the live re-check of added firmware records, with a fake GitHub."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import jr_pr_guard as g  # noqa: E402

OK = {"stargazers_count": 27, "forks_count": 3, "fork": False, "archived": False}
FM = {"id": "x", "url": "https://github.com/o/x", "socs": ["esp32-s3"], "popularity": {"stars": 27, "forks": 3, "as_of": "2026-09-07"}}


def test_a_real_public_repo_above_the_floor_with_a_snapshot_passes():
    assert g.check_record("data/firmware/x/firmware.md", FM, fetch=lambda r: {"status": 200, "json": OK}) == []


def test_forks_archived_missing_and_sub_floor_repos_are_refused():
    assert any("is a fork of up/x" in m for m in g.check_record("p", FM, fetch=lambda r: {"status": 200, "json": {**OK, "fork": True, "parent": {"full_name": "up/x"}}}))
    assert any("is archived" in m for m in g.check_record("p", FM, fetch=lambda r: {"status": 200, "json": {**OK, "archived": True}}))
    assert any("does not answer on GitHub (HTTP 404)" in m for m in g.check_record("p", FM, fetch=lambda r: {"status": 404, "json": {}}))
    assert any("below the floor live (3 stars / 1 forks)" in m for m in g.check_record("p", FM, fetch=lambda r: {"status": 200, "json": {**OK, "stargazers_count": 3, "forks_count": 1}}))


def test_a_record_without_a_snapshot_or_socs_or_a_github_url_is_refused():
    assert any("no dated popularity snapshot" in m for m in g.check_record("p", {**FM, "popularity": None}, fetch=lambda r: {"status": 200, "json": OK}))
    assert any("socs is empty" in m for m in g.check_record("p", {**FM, "socs": []}, fetch=lambda r: {"status": 200, "json": OK}))
    assert g.check_record("p", {**FM, "url": "https://gitlab.com/o/x"}, fetch=lambda r: {"status": 200, "json": OK}) == ["p: url is not a github.com/owner/repo ('https://gitlab.com/o/x')"]


def test_added_firmware_paths_are_taken_from_the_name_status_diff():
    diff = "A\tdata/firmware/new/firmware.md\nM\tdata/firmware/old/firmware.md\nA\tdata/recipes/b__new/recipe.md\nA\tjr/proposed_ledger.json\n"
    assert g.added_firmware(diff) == ["data/firmware/new/firmware.md"]


def test_main_against_the_real_repo_with_no_added_firmware_is_green():
    assert g.main(["--base", "HEAD"]) == 0
