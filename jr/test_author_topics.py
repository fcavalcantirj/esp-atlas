"""EspAtlas Jr — pytest for the one-shot GitHub-topics authoring driver (jr/author_topics.py).

Covers: the driver wires drain.run_drain() (never a hand-rolled authoring loop) to the
GitHub-topics source with the one-shot batch sizing (max_per_category=8, batch_size=40) and the
live fork resolver by default; --limit lowers the batch passed to run_drain instead of inventing
a separate cap; and an end-to-end pass (injected fake topic search + fake fetch_meta, no
resolve_source) authors a schema-valid firmware+recipe through the REAL run_drain — the same
real, local guard test_drain.py's own full-pipeline test exercises. No network: search_topic and
fetch_meta are always fakes.

Run: cd jr && python3 -m pytest test_author_topics.py -v
"""
from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import author_topics  # noqa: E402
import drain  # noqa: E402
import source_topics  # noqa: E402
import tools  # noqa: E402

REPO = tools.REPO
FIRMWARE_SCHEMA = json.loads((REPO / "schema/firmware.schema.json").read_text())
RECIPE_SCHEMA = json.loads((REPO / "schema/recipe.schema.json").read_text())

FIXTURE_ID = "zzz-test-fixture-author-topics"


@pytest.fixture
def cleanup_fixture():
    yield
    shutil.rmtree(tools.FIRMWARE_DIR / FIXTURE_ID, ignore_errors=True)
    for rdir in (REPO / "data/recipes").glob(f"*__{FIXTURE_ID}"):
        shutil.rmtree(rdir, ignore_errors=True)


# ─────────────────────────── reuses drain.run_drain — no duplicated authoring loop ───────────────────────────

def test_author_topics_defines_no_authoring_or_scoring_logic_of_its_own():
    """The driver's only job is wiring: it must not reimplement any step of the pipeline."""
    for name in ("author_selected", "score_candidates", "score_entry", "run_guard", "prefilter"):
        assert not hasattr(author_topics, name), f"author_topics must not define its own {name}()"


def test_main_calls_drain_run_drain(monkeypatch):
    calls = []

    def spy(**kwargs):
        calls.append(kwargs)
        return {"fetched": 0, "prefiltered": 0, "scored_clean": 0, "skipped_scoring": 0,
                "skipped_popularity": [], "selected": 0, "dropped_cap": 0, "authored": [],
                "dropped_guard": [], "guard": {"ok": True, "output": ""}}
    monkeypatch.setattr(drain, "run_drain", spy)

    author_topics.main(search_topic=lambda topic, per_page: [], resolve_source=lambda owner, repo: None)

    assert len(calls) == 1


def test_main_wires_batch_sizing_and_topics_source(monkeypatch):
    calls = []

    def spy(**kwargs):
        calls.append(kwargs)
        return {"fetched": 0, "prefiltered": 0, "scored_clean": 0, "skipped_scoring": 0,
                "skipped_popularity": [], "selected": 0, "dropped_cap": 0, "authored": [],
                "dropped_guard": [], "guard": {"ok": True, "output": ""}}
    monkeypatch.setattr(drain, "run_drain", spy)

    fake_resolver = lambda owner, repo: None
    author_topics.main(search_topic=lambda topic, per_page: [], resolve_source=fake_resolver)

    kwargs = calls[0]
    assert kwargs["batch_size"] == author_topics.BATCH_SIZE == 40
    assert kwargs["max_per_category"] == author_topics.MAX_PER_CATEGORY == 8
    assert kwargs["resolve_source"] is fake_resolver


def test_main_fetch_catalog_kwarg_drives_the_injected_topic_search(monkeypatch):
    """fetch_catalog is a callable run_drain calls itself — assert it, once called, returns
    candidates shaped by the injected search fake, not a live network call."""
    calls = []
    monkeypatch.setattr(drain, "run_drain", lambda **kwargs: calls.append(kwargs) or {
        "fetched": 0, "prefiltered": 0, "scored_clean": 0, "skipped_scoring": 0,
        "skipped_popularity": [], "selected": 0, "dropped_cap": 0, "authored": [],
        "dropped_guard": [], "guard": {"ok": True, "output": ""},
    })

    def fake_search(topic, per_page):
        return [{"full_name": "someone/topic-tool"}] if topic == "cardputer" else []
    author_topics.main(search_topic=fake_search, resolve_source=lambda owner, repo: None)

    fetch_catalog = calls[0]["fetch_catalog"]
    candidates = fetch_catalog()
    assert {"name": "topic-tool", "github": "https://github.com/someone/topic-tool",
            "source": "topic:cardputer"} in candidates


def test_main_defaults_resolve_source_to_drains_live_resolver(monkeypatch):
    calls = []
    monkeypatch.setattr(drain, "run_drain", lambda **kwargs: calls.append(kwargs) or {
        "fetched": 0, "prefiltered": 0, "scored_clean": 0, "skipped_scoring": 0,
        "skipped_popularity": [], "selected": 0, "dropped_cap": 0, "authored": [],
        "dropped_guard": [], "guard": {"ok": True, "output": ""},
    })

    author_topics.main(search_topic=lambda topic, per_page: [])

    assert calls[0]["resolve_source"] is drain._live_resolve_canonical


def test_limit_lowers_batch_size_passed_to_run_drain(monkeypatch):
    calls = []
    monkeypatch.setattr(drain, "run_drain", lambda **kwargs: calls.append(kwargs) or {
        "fetched": 0, "prefiltered": 0, "scored_clean": 0, "skipped_scoring": 0,
        "skipped_popularity": [], "selected": 0, "dropped_cap": 0, "authored": [],
        "dropped_guard": [], "guard": {"ok": True, "output": ""},
    })

    author_topics.main(limit=5, search_topic=lambda topic, per_page: [], resolve_source=lambda owner, repo: None)

    assert calls[0]["batch_size"] == 5


def test_no_limit_means_the_full_one_shot_batch_size(monkeypatch):
    calls = []
    monkeypatch.setattr(drain, "run_drain", lambda **kwargs: calls.append(kwargs) or {
        "fetched": 0, "prefiltered": 0, "scored_clean": 0, "skipped_scoring": 0,
        "skipped_popularity": [], "selected": 0, "dropped_cap": 0, "authored": [],
        "dropped_guard": [], "guard": {"ok": True, "output": ""},
    })

    author_topics.main(search_topic=lambda topic, per_page: [], resolve_source=lambda owner, repo: None)

    assert calls[0]["batch_size"] == author_topics.BATCH_SIZE


# ─────────────────────────── end-to-end: real run_drain, fake I/O, real guard ───────────────────────────

def test_main_full_pipeline_authors_a_clean_topic_candidate(cleanup_fixture, capsys):
    def fake_search(topic, per_page):
        if topic != "cardputer":
            return []
        return [{"full_name": f"octocat/{FIXTURE_ID}", "stargazers_count": 55}]

    meta = {"full_name": f"octocat/{FIXTURE_ID}", "fork": False, "source_full_name": None, "stars": 55,
            "description": "WiFi deauth tool for the Cardputer.", "license": None, "readme_title": None}

    report = author_topics.main(search_topic=fake_search, fetch_meta=lambda url: meta,
                                resolve_source=lambda owner, repo: None)

    assert report["authored"] == [FIXTURE_ID]
    assert report["dropped_guard"] == []
    assert report["guard"]["ok"] is True

    fm = tools._frontmatter(tools.FIRMWARE_DIR / FIXTURE_ID / "firmware.md")
    jsonschema.validate(fm, FIRMWARE_SCHEMA)
    assert fm["category"] == "pentest"
    rc_dirs = list((REPO / "data/recipes").glob(f"*__{FIXTURE_ID}"))
    assert len(rc_dirs) == 1
    jsonschema.validate(tools._frontmatter(rc_dirs[0] / "recipe.md"), RECIPE_SCHEMA)

    out = capsys.readouterr().out
    assert f"authored (1): ['{FIXTURE_ID}']" in out
    assert "guard ok=True" in out


def test_main_reports_skips_and_authors_nothing_when_topics_are_all_noise():
    def fake_search(topic, per_page):
        return [{"full_name": "someone/esp32-doom"}] if topic == "cardputer" else []

    report = author_topics.main(search_topic=fake_search,
                                fetch_meta=lambda url: pytest.fail("no network"),
                                resolve_source=lambda owner, repo: None)

    assert report["authored"] == []
    assert report["guard"]["ok"] is True


def test_main_returns_run_drains_report_unchanged(monkeypatch):
    sentinel = {"fetched": 3, "prefiltered": 2, "scored_clean": 1, "skipped_scoring": 1,
               "skipped_popularity": [], "selected": 1, "dropped_cap": 0, "authored": ["some-id"],
               "dropped_guard": [], "guard": {"ok": True, "output": ""}}
    monkeypatch.setattr(drain, "run_drain", lambda **kwargs: sentinel)

    report = author_topics.main(search_topic=lambda topic, per_page: [], resolve_source=lambda owner, repo: None)

    assert report is sentinel
