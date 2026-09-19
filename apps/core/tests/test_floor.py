"""Tests for esp_atlas_core.floor — the ONE popularity-floor definition (SPEC-firmware-floor.md).

Oracle-loop replay set for the THIRD, editorial-home signal (deterministic, zero LLM). Real
firmware, never lorem ipsum: RogueDuck (a Cardputer pentest tool with a real independent
write-up at ethicalhackersden.org, 6 stars/3 forks) is the class a stars/forks-only bar wrongly
cuts; server-vampeta-class filler (3 stars, 0 forks, no homepage) is the class the floor must
keep cutting.
"""
from __future__ import annotations

from esp_atlas_core.floor import FORK_FLOOR, STAR_FLOOR, clears_popularity_floor


# --- pre-existing two-signal behaviour (regression) --------------------------------------------

def test_clears_via_stars_alone():
    assert clears_popularity_floor(30, 0) is True


def test_clears_via_forks_alone():
    assert clears_popularity_floor(2, 40) is True


def test_below_both_with_no_homepage_is_cut():
    assert clears_popularity_floor(3, 4) is False


def test_boundary_is_inclusive():
    assert clears_popularity_floor(STAR_FLOOR, 0) is True
    assert clears_popularity_floor(0, FORK_FLOOR) is True
    assert clears_popularity_floor(STAR_FLOOR - 1, FORK_FLOOR - 1) is False


def test_missing_star_fork_values_count_as_zero():
    assert clears_popularity_floor(None, None) is False
    assert clears_popularity_floor(None, FORK_FLOOR) is True


# --- editorial-home signal (RogueDuck class) ----------------------------------------------------

def test_rogueduck_class_clears_via_independent_editorial_home():
    """6 stars, 3 forks, under BOTH floors — but a real independent blog write-up clears it."""
    assert clears_popularity_floor(6, 3, "https://ethicalhackersden.org") is True


def test_editorial_home_alone_is_enough_even_at_zero_stars_and_forks():
    assert clears_popularity_floor(0, 0, "https://ethicalhackersden.org") is True


def test_filler_with_no_homepage_is_still_cut():
    """server-vampeta class: 3 stars, 0 forks, no homepage -> never clears."""
    assert clears_popularity_floor(3, 0, None) is False


def test_filler_with_empty_string_homepage_is_still_cut():
    assert clears_popularity_floor(3, 0, "") is False


def test_github_homepage_is_not_editorial():
    """A homepage pointing back at github.com is the repo itself, not an independent home."""
    assert clears_popularity_floor(3, 0, "https://github.com/foo/bar") is False


def test_github_io_homepage_is_not_editorial():
    """A *.github.io page is a GitHub Pages mirror of the repo, not an independent home."""
    assert clears_popularity_floor(3, 0, "https://foo.github.io") is False


def test_github_io_project_page_with_path_is_not_editorial():
    assert clears_popularity_floor(3, 0, "https://foo.github.io/bar/") is False


def test_non_http_scheme_homepage_is_not_editorial():
    assert clears_popularity_floor(3, 0, "ftp://example.com") is False


def test_malformed_homepage_is_not_editorial():
    assert clears_popularity_floor(3, 0, "not a url") is False


def test_homepage_with_no_host_is_not_editorial():
    assert clears_popularity_floor(3, 0, "https:///no-host") is False
