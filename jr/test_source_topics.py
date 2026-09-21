"""EspAtlas Jr — pytest for the GitHub-topics firmware SOURCE (jr/source_topics.py).

Covers: mapping a fake `search/repositories` response into candidate dicts shaped like a
launcher-catalog entry (name/github/source), per-topic tagging, dedup of a repo that surfaces
under more than one topic, and tolerance of malformed search items. No network call: `search` is
always a fake.

Run: cd jr && python3 -m pytest test_source_topics.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import source_topics  # noqa: E402


def _fake_search(mapping):
    def search(topic, per_page):
        return mapping.get(topic, [])
    return search


# ─────────────────────────── fetch_topic_repos: mapping/shape ───────────────────────────

def test_maps_search_items_into_candidate_shape():
    search = _fake_search({
        "cardputer": [{"full_name": "geo-tp/cardputer-tool", "stargazers_count": 42}],
    })

    candidates = source_topics.fetch_topic_repos(["cardputer"], search=search)

    assert candidates == [{
        "name": "cardputer-tool",
        "github": "https://github.com/geo-tp/cardputer-tool",
        "source": "topic:cardputer",
        "description": None,
    }]


def test_multiple_topics_each_tag_their_own_new_candidates():
    search = _fake_search({
        "cardputer": [{"full_name": "a/one"}],
        "bruce": [{"full_name": "b/two"}],
    })

    candidates = source_topics.fetch_topic_repos(["cardputer", "bruce"], search=search)

    sources = {c["github"]: c["source"] for c in candidates}
    assert sources["https://github.com/a/one"] == "topic:cardputer"
    assert sources["https://github.com/b/two"] == "topic:bruce"


# ─────────────────────────── dedup across topics ───────────────────────────

def test_dedups_a_repo_seen_under_multiple_topics():
    search = _fake_search({
        "cardputer": [{"full_name": "pr3y/bruce", "stargazers_count": 900}],
        "bruce": [{"full_name": "pr3y/bruce", "stargazers_count": 900}],
    })

    candidates = source_topics.fetch_topic_repos(["cardputer", "bruce"], search=search)

    assert len(candidates) == 1
    assert candidates[0]["github"] == "https://github.com/pr3y/bruce"
    assert candidates[0]["source"] == "topic:cardputer"   # first-seen topic wins the tag


def test_dedup_is_case_insensitive_on_full_name():
    search = _fake_search({
        "cardputer": [{"full_name": "Pr3y/Bruce"}],
        "bruce": [{"full_name": "pr3y/bruce"}],
    })

    candidates = source_topics.fetch_topic_repos(["cardputer", "bruce"], search=search)

    assert len(candidates) == 1


# ─────────────────────────── malformed input tolerance ───────────────────────────

def test_skips_malformed_items_without_raising():
    search = _fake_search({
        "cardputer": [
            {"stargazers_count": 5},     # no full_name
            {"full_name": ""},           # empty full_name
            {"full_name": "onlyowner"},  # no owner/repo split
            {"full_name": "ok/repo"},
        ],
    })

    candidates = source_topics.fetch_topic_repos(["cardputer"], search=search)

    assert candidates == [{
        "name": "repo",
        "github": "https://github.com/ok/repo",
        "source": "topic:cardputer",
        "description": None,
    }]


def test_search_returning_none_is_tolerated():
    candidates = source_topics.fetch_topic_repos(["cardputer"], search=lambda topic, per_page: None)
    assert candidates == []


def test_blank_topics_are_skipped_without_calling_search():
    calls = []

    def search(topic, per_page):
        calls.append(topic)
        return []

    source_topics.fetch_topic_repos(["", "  ", "cardputer"], search=search)

    assert calls == ["cardputer"]


# ─────────────────────────── injected per_topic ───────────────────────────

def test_per_topic_is_threaded_to_the_search_callable():
    seen_args = []

    def search(topic, per_page):
        seen_args.append((topic, per_page))
        return []

    source_topics.fetch_topic_repos(["cardputer"], search=search, per_topic=50)

    assert seen_args == [("cardputer", 50)]


def test_per_topic_defaults_to_100():
    seen_args = []

    def search(topic, per_page):
        seen_args.append(per_page)
        return []

    source_topics.fetch_topic_repos(["cardputer"], search=search)

    assert seen_args == [100]


# ─────────────────────────── DEFAULT_TOPICS ───────────────────────────

def test_default_topics_seeded_as_specified():
    assert source_topics.DEFAULT_TOPICS == [
        "cardputer", "m5stack", "m5stack-cardputer", "esp32-marauder", "bruce",
    ]
