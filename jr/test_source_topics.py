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


# ─────────────────────────── seed list (versioned) ───────────────────────────

import math  # noqa: E402

CURATED = [
    "esp32", "esp32-s3", "esp32-c3", "esp32-c6", "esp32-c5", "esp32-h2", "esp32-p4", "esp-idf",
    "arduino-esp32", "platformio", "m5stickc", "m5stack-core2", "atoms3", "m5stack-cardputer",
    "cardputer", "lilygo", "t-deck", "t-display", "heltec", "meshtastic", "meshcore", "wled",
    "esphome", "tasmota", "esp32-marauder", "bruce", "flipper-zero", "wardriving", "xiaozhi",
]


def _catalog(tmp_path, socs=(), brands=()):
    for soc in socs:
        (tmp_path / "data" / "socs" / soc).mkdir(parents=True)
    for brand in brands:
        (tmp_path / "data" / "boards" / brand).mkdir(parents=True)
    return tmp_path


def test_curated_topics_cover_the_ecosystem():
    assert source_topics.CURATED_TOPICS == CURATED
    assert isinstance(source_topics.SEED_VERSION, int) and source_topics.SEED_VERSION >= 1


def test_catalog_topics_derive_socs_and_brands_in_github_topic_form(tmp_path):
    root = _catalog(tmp_path, socs=["esp32-c61", "ESP32_S31"], brands=["unexpected-maker", "Seeed Studio", "m5stack"])
    (tmp_path / "data" / "boards" / "README.md").write_text("not a brand dir")
    assert source_topics.catalog_topics(root) == [
        "esp32-c61", "esp32-s31", "m5stack", "seeed-studio", "unexpected-maker",
    ]


def test_catalog_topics_tolerate_a_missing_catalog(tmp_path):
    assert source_topics.catalog_topics(tmp_path) == []


def test_seed_topics_is_curated_then_catalog_with_no_duplicates(tmp_path):
    root = _catalog(tmp_path, socs=["esp32", "esp32-c61", "esp32-s2"], brands=["lilygo", "m5stack", "waveshare"])
    seed = source_topics.seed_topics(root)
    assert seed[:len(CURATED)] == CURATED
    assert seed[len(CURATED):] == ["esp32-c61", "esp32-s2", "m5stack", "waveshare"]
    assert len(seed) == len(set(seed))


def test_seed_topics_on_the_real_catalog_include_every_soc_and_brand():
    seed = source_topics.seed_topics()
    repo = Path(__file__).resolve().parent.parent
    socs = {p.name for p in (repo / "data" / "socs").iterdir() if p.is_dir()}
    brands = {p.name for p in (repo / "data" / "boards").iterdir() if p.is_dir()}
    assert set(CURATED) | socs | brands <= set(seed)
    assert len(seed) == len(set(seed))
    assert source_topics.DEFAULT_TOPICS == seed   # the one-shot drivers scan the whole seed list


def test_normalize_topic_to_github_form():
    n = source_topics.normalize_topic
    assert n("  ESP32_S3 ") == "esp32-s3"
    assert n("Seeed Studio") == "seeed-studio"
    assert n("--a..b--") == "a-b"
    assert n("x" * 80) == "x" * 50
    assert n("!!!") == ""


# ─────────────────────────── rotation across hourly ticks ───────────────────────────

def test_rotation_covers_every_topic_within_ceil_n_over_k_ticks():
    topics = [f"t{i}" for i in range(41)]
    for k in (1, 2, 3, 7):
        for start in (0, 5, 123456):
            seen = set()
            for h in range(start, start + math.ceil(len(topics) / k)):
                seen.update(source_topics.topics_for_tick(topics, h, k))
            assert seen == set(topics), (k, start)


def test_rotation_is_deterministic_for_a_given_hour_index():
    topics = [f"t{i}" for i in range(41)]
    assert source_topics.topics_for_tick(topics, 482_017, 2) == source_topics.topics_for_tick(list(topics), 482_017, 2)
    assert source_topics.topics_for_tick(topics, 0, 2) == ["t0", "t1"]
    assert source_topics.topics_for_tick(topics, 20, 2) == ["t40", "t0"]   # wraps


def test_rotation_never_returns_more_than_k_or_duplicates():
    for n in (0, 1, 2, 5):
        topics = [f"t{i}" for i in range(n)]
        for h in range(10):
            got = source_topics.topics_for_tick(topics, h, 3)
            assert len(got) <= 3 and len(got) == len(set(got)) and set(got) <= set(topics)


def test_hour_index_is_whole_hours_since_epoch():
    from datetime import datetime, timezone
    assert source_topics.hour_index(datetime(1970, 1, 1, 2, 59, tzinfo=timezone.utc)) == 2
    a = source_topics.hour_index(datetime(2026, 11, 3, 20, 0, tzinfo=timezone.utc))
    b = source_topics.hour_index(datetime(2026, 11, 3, 20, 59, tzinfo=timezone.utc))
    c = source_topics.hour_index(datetime(2026, 11, 3, 21, 0, tzinfo=timezone.utc))
    assert a == b and c == a + 1
