"""EspAtlas Jr — pytest for the deterministic launcher-catalog drain (jr/drain.py).

Covers: the cheap no-network pre-filter (dedup vs catalogued repos/tokens, noise tokens,
missing github), scorer.score_entry() integration via an injected fetch_meta (dedup fork
detection, clean-mappable authoring), the juicy ranking (download+stars combined, per-category
cap), and that author_selected() writes a firmware+recipe pair that validates against the real
schema (and the real guard) — then cleans up after itself. Network is NEVER hit directly here:
fetch_meta is always an injected fake; author_selected's guard checks are real (local
subprocess over the real, already-clean dataset), which is what proves "matches the schema the
guard expects" for real, not just against a copy of the schema.

Run: cd jr && python3 -m pytest test_drain.py -v
"""
from __future__ import annotations
import json
import shutil
import sys
from pathlib import Path

import jsonschema
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import drain  # noqa: E402
import ledger  # noqa: E402
import tools  # noqa: E402

REPO = tools.REPO
FIRMWARE_SCHEMA = json.loads((REPO / "schema/firmware.schema.json").read_text())
RECIPE_SCHEMA = json.loads((REPO / "schema/recipe.schema.json").read_text())

CATALOGUED_REPOS = {"pr3y/bruce", "pr3y", "justcallmekoko/esp32marauder", "justcallmekoko"}
CATALOGUED_TOKENS = {"bruce", "esp32marauder", "marauder"}


# ─────────────────────────── prefilter (cheap, no network) ───────────────────────────

def test_prefilter_drops_entries_with_no_github_link():
    entries = [{"name": "No Code Here", "github": "", "download": 999}]
    assert drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS) == []


def test_prefilter_drops_already_catalogued_repo():
    entries = [{"name": "Marauder Fork", "github": "https://github.com/justcallmekoko/ESP32Marauder",
                "download": 500}]
    assert drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS) == []


def test_prefilter_drops_same_owner_different_repo():
    """Owner-level dedup: a DIFFERENT repo by an already-catalogued owner is still a skip
    (mirrors tools._catalogued_repos_and_tokens()'s owner-only fingerprint)."""
    entries = [{"name": "Justcallmekoko Side Project", "github": "https://github.com/justcallmekoko/other-tool",
                "download": 500}]
    assert drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS) == []


def test_prefilter_drops_name_token_match():
    entries = [{"name": "Bruce Companion App", "github": "https://github.com/someone/bruce-companion",
                "download": 500}]
    assert drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS) == []


def test_prefilter_drops_noise_tokens():
    entries = [{"name": "ESP32 Doom Port", "github": "https://github.com/someone/esp32-doom",
                "download": 999999}]
    assert drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS) == []


def test_prefilter_keeps_clean_new_entry_sorted_by_download_desc():
    entries = [
        {"name": "Low Download Tool", "github": "https://github.com/a/low", "download": 10},
        {"name": "High Download Tool", "github": "https://github.com/b/high", "download": 9000},
        {"name": "Mid Download Tool", "github": "https://github.com/c/mid", "download": 500},
    ]
    kept = drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS)
    assert [e["name"] for e in kept] == ["High Download Tool", "Mid Download Tool", "Low Download Tool"]


def test_prefilter_treats_missing_download_as_zero():
    entries = [{"name": "No Download Field", "github": "https://github.com/a/nodl"}]
    kept = drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS)
    assert len(kept) == 1


# ─────────────────────────── prefilter x ledger (repo already proposed/rejected — deliverable 3) ───────────────────────────

def _ledger_with(repo: str, status: str) -> dict:
    """A ledger_state dict with one record for `repo`, at `status` — built through the real
    ledger.py helpers (a tmp path, never the real jr/proposed_ledger.json) so this exercises the
    actual on-disk shape drain.py will see, not a hand-rolled stand-in."""
    import tempfile
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    try:
        firmware_id = repo.split("/")[-1]
        ledger.record_proposed(firmware_id, repo, path=tmp)
        if status != "proposed":
            ledger.update_status(firmware_id, status, path=tmp)
        return ledger.load_ledger(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def test_prefilter_drops_candidate_already_in_ledger_as_proposed():
    """(a) a candidate already in the ledger as proposed is skipped by the drain."""
    entries = [{"name": "Ghost ESP", "github": "https://github.com/jorgen/ghostesp", "download": 500}]
    ledger_state = _ledger_with("jorgen/ghostesp", "proposed")
    kept = drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS, ledger_state=ledger_state)
    assert kept == []


def test_prefilter_drops_candidate_already_in_ledger_as_rejected():
    """(b) a candidate in the ledger as rejected is skipped by the drain."""
    entries = [{"name": "Ghost ESP", "github": "https://github.com/jorgen/ghostesp", "download": 500}]
    ledger_state = _ledger_with("jorgen/ghostesp", "rejected")
    kept = drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS, ledger_state=ledger_state)
    assert kept == []


def test_prefilter_keeps_candidate_not_in_ledger():
    """(c) a brand-new candidate not in the ledger passes prefilter."""
    entries = [{"name": "Ghost ESP", "github": "https://github.com/jorgen/ghostesp", "download": 500}]
    ledger_state = _ledger_with("someoneelse/unrelated-repo", "proposed")
    kept = drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS, ledger_state=ledger_state)
    assert len(kept) == 1


def test_prefilter_keeps_candidate_merged_in_ledger():
    """merged is not a blocking status via the ledger — catalogued-in-main dedup already covers
    a genuinely merged repo (it would be in CATALOGUED_REPOS by then)."""
    entries = [{"name": "Ghost ESP", "github": "https://github.com/jorgen/ghostesp", "download": 500}]
    ledger_state = _ledger_with("jorgen/ghostesp", "merged")
    kept = drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS, ledger_state=ledger_state)
    assert len(kept) == 1


def test_prefilter_with_no_ledger_state_behaves_as_before():
    """Backward compatible: omitting ledger_state (None default) does not filter anything extra."""
    entries = [{"name": "Ghost ESP", "github": "https://github.com/jorgen/ghostesp", "download": 500}]
    kept = drain.prefilter(entries, CATALOGUED_REPOS, CATALOGUED_TOKENS)
    assert len(kept) == 1


# ─────────────────────────── score_candidates (scorer integration, fetch_meta injected) ───────────────────────────

def _fake_meta(**overrides):
    base = {"full_name": None, "fork": False, "source_full_name": None, "stars": 0,
            "description": None, "license": None, "readme_title": None}
    base.update(overrides)
    return base


def test_score_candidates_authors_clean_mappable_entry():
    entry = {"name": "Cardputer Ghost ESP", "description": "WiFi tools for the Cardputer",
              "category": "cardputer", "github": "https://github.com/jorgen/ghostesp", "download": 500}
    meta = _fake_meta(full_name="jorgen/ghostesp", stars=42, description="WiFi tools for the Cardputer")

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: meta)

    assert skipped == []
    assert len(scored) == 1
    rec = scored[0]["record"]
    assert rec["board"] == "m5cardputer"
    assert rec["chip"] == "esp32-s3"
    assert rec["category"] == "pentest"          # "wifi" capability signal
    assert scored[0]["download"] == 500
    assert scored[0]["stars"] == 42
    assert scored[0]["description"] == "WiFi tools for the Cardputer"


def test_score_candidates_skips_fork_of_catalogued_via_scorer():
    entry = {"name": "Marauder for Cardputer", "description": None, "category": "cardputer",
              "github": "https://github.com/someoneelse/ESP32Marauder", "download": 3000}
    meta = _fake_meta(full_name="someoneelse/ESP32Marauder", fork=True,
                      source_full_name="justcallmekoko/ESP32Marauder", stars=5)

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: meta)

    assert scored == []
    assert len(skipped) == 1
    assert "fork_of_catalogued" in skipped[0]["reason"]


def test_score_candidates_skips_no_board_evidence():
    entry = {"name": "Mystery Widget", "description": "Does mysterious things", "category": None,
              "github": "https://github.com/someone/mystery-widget", "download": 50}
    meta = _fake_meta(full_name="someone/mystery-widget", description="Does mysterious things")

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: meta)

    assert scored == []
    assert "no_board_evidence" in skipped[0]["reason"]


def test_score_candidates_skips_when_repo_unresolved():
    entry = {"name": "Dead Repo Tool", "github": "https://github.com/ghost/dead-repo", "download": 10}

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: {"error": "404"})

    assert scored == []
    assert "repo_unresolved" in skipped[0]["reason"]


# ─────────────────────────── score_candidates x ledger (id-level dedup — deliverable 3) ───────────────────────────

def test_score_candidates_skips_entry_whose_scored_id_is_already_proposed():
    entry = {"name": "Cardputer Ghost ESP", "description": "WiFi tools for the Cardputer",
              "category": "cardputer", "github": "https://github.com/jorgen/ghostesp", "download": 500}
    meta = _fake_meta(full_name="jorgen/ghostesp", stars=42, description="WiFi tools for the Cardputer")
    ledger_state = _ledger_with("jorgen/ghostesp", "proposed")

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: meta, ledger_state=ledger_state)

    assert scored == []
    assert "already_proposed" in skipped[0]["reason"]


def test_score_candidates_skips_entry_whose_scored_id_is_already_rejected():
    entry = {"name": "Cardputer Ghost ESP", "description": "WiFi tools for the Cardputer",
              "category": "cardputer", "github": "https://github.com/jorgen/ghostesp", "download": 500}
    meta = _fake_meta(full_name="jorgen/ghostesp", stars=42, description="WiFi tools for the Cardputer")
    ledger_state = _ledger_with("jorgen/ghostesp", "rejected")

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: meta, ledger_state=ledger_state)

    assert scored == []
    assert "already_rejected" in skipped[0]["reason"]


def test_score_candidates_authors_entry_not_in_ledger():
    entry = {"name": "Cardputer Ghost ESP", "description": "WiFi tools for the Cardputer",
              "category": "cardputer", "github": "https://github.com/jorgen/ghostesp", "download": 500}
    meta = _fake_meta(full_name="jorgen/ghostesp", stars=42, description="WiFi tools for the Cardputer")
    ledger_state = _ledger_with("someoneelse/unrelated-repo", "proposed")

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: meta, ledger_state=ledger_state)

    assert skipped == []
    assert len(scored) == 1
    assert scored[0]["record"]["id"] == "ghostesp"


# ─────────────────────────── popularity floor (SPEC-firmware-floor.md) ───────────────────────────

def _coding_entry(**overrides):
    """A clean, scorer-mappable coding-domain candidate: a Cardputer on-device dev tool. Board
    evidence comes from category='cardputer' (device_from_category -> m5cardputer)."""
    entry = {"name": "Cardputer Git Client", "description": "An on-device git client for the Cardputer",
             "category": "cardputer", "github": "https://github.com/devuser/cardputer-git",
             "download": 0}
    entry.update(overrides)
    return entry


def test_score_candidates_skips_candidate_below_all_floors():
    """stars=3 AND forks=1 → below both floors → skipped, not authored (downloads are never
    consulted — a high launcher download count no longer rescues a candidate)."""
    entry = _coding_entry(download=999999)
    meta = _fake_meta(full_name="devuser/cardputer-git", stars=3, forks=1,
                      description="An on-device git client for the Cardputer")

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: meta)

    assert scored == []
    assert len(skipped) == 1
    assert skipped[0]["reason"] == "below-popularity-floor"
    assert skipped[0]["firmware_id"] == "cardputer-git"
    assert skipped[0]["repo"] == "devuser/cardputer-git"
    assert "download" not in skipped[0]


def test_score_candidates_authors_when_forks_clear_the_floor():
    """stars=3 BUT forks=30 → forks clear FORK_FLOOR → authored (a heavily built-on but
    under-starred utility is real, not filler)."""
    entry = _coding_entry()
    meta = _fake_meta(full_name="devuser/cardputer-git", stars=3, forks=30,
                      description="An on-device git client for the Cardputer")

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: meta)

    assert skipped == []
    assert len(scored) == 1
    assert scored[0]["record"]["id"] == "cardputer-git"
    assert scored[0]["forks"] == 30


def test_score_candidates_authors_when_stars_clear_the_floor():
    """stars=40 AND forks=0 → stars clear STAR_FLOOR → authored despite zero forks."""
    entry = _coding_entry()
    meta = _fake_meta(full_name="devuser/cardputer-git", stars=40,
                      description="An on-device git client for the Cardputer")

    scored, skipped = drain.score_candidates([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS,
                                             fetch_meta=lambda url: meta)

    assert skipped == []
    assert len(scored) == 1
    assert scored[0]["record"]["id"] == "cardputer-git"


def test_prefilter_skips_a_repo_recorded_seen(tmp_path):
    """A repo recorded 'seen' (below-floor) in the ledger is skipped by prefilter before any fetch,
    so sub-floor filler isn't re-fetched every run — but stays non-blocking (merged/absent pass)."""
    ledger.record_seen("cardputer-git", "devuser/cardputer-git", path=tmp_path / "l.json")
    state = ledger.load_ledger(tmp_path / "l.json")
    entry = _coding_entry()
    assert drain.prefilter([entry], CATALOGUED_REPOS, CATALOGUED_TOKENS, ledger_state=state) == []


def test_run_drain_records_below_floor_candidate_as_seen_and_reports_it(tmp_path, monkeypatch):
    """A sub-floor candidate is reported under skipped_popularity and recorded 'seen' in the
    injected ledger so the NEXT run's prefilter skips it before any fetch (not re-fetched every
    run). Isolated from live catalogued-set drift by injecting the dedup fingerprint."""
    monkeypatch.setattr(tools, "_catalogued_repos_and_tokens", lambda: (CATALOGUED_REPOS, CATALOGUED_TOKENS))
    entry = _coding_entry()
    meta = {"full_name": "devuser/cardputer-git", "fork": False, "source_full_name": None, "stars": 3,
            "description": "An on-device git client for the Cardputer", "license": None, "readme_title": None}
    ledger_path = tmp_path / "proposed_ledger.json"

    report = drain.run_drain(fetch_catalog=lambda: [entry], fetch_meta=lambda url: meta,
                             ledger_path=ledger_path)

    assert report["authored"] == []
    assert len(report["skipped_popularity"]) == 1
    assert report["skipped_popularity"][0]["firmware_id"] == "cardputer-git"
    # recorded 'seen' (non-blocking) in the ledger
    state = ledger.load_ledger(ledger_path)
    assert state["by_id"]["cardputer-git"]["status"] == "seen"
    assert ledger.is_seen(state, repo="devuser/cardputer-git") is True


# ─────────────────────────── rank_juicy (popularity = downloads combined with stars) ───────────────────────────

def _scored(name, download, stars, category="multi"):
    return {"record": {"id": name, "name": name, "category": category, "board": "m5cardputer",
                       "url": f"https://github.com/x/{name}"},
            "download": download, "stars": stars, "description": ""}


def test_rank_juicy_rewards_combined_signal_over_a_single_extreme():
    huge_downloads_no_stars = _scored("huge-dl", download=100000, stars=0)
    huge_stars_no_downloads = _scored("huge-star", download=0, stars=5000)
    balanced_both = _scored("balanced", download=5000, stars=200)
    ranked = drain.rank_juicy([huge_downloads_no_stars, huge_stars_no_downloads, balanced_both])
    assert ranked[0]["record"]["id"] == "balanced"


def test_rank_juicy_is_stable_ordering_for_equal_signal():
    a = _scored("a", download=100, stars=10)
    b = _scored("b", download=100, stars=10)
    ranked = drain.rank_juicy([a, b])
    assert {r["record"]["id"] for r in ranked} == {"a", "b"}


# ─────────────────────────── cap_categories (diversity: max 4 per category) ───────────────────────────

def test_cap_categories_enforces_max_per_category():
    scored = [_scored(f"pentest-{i}", download=1000 - i, stars=0, category="pentest") for i in range(6)]
    selected, dropped = drain.cap_categories(scored, max_per_category=4, batch_size=20)
    assert len(selected) == 4
    assert {s["record"]["id"] for s in selected} == {"pentest-0", "pentest-1", "pentest-2", "pentest-3"}
    assert len(dropped) == 2


def test_cap_categories_keeps_diverse_categories_under_the_cap():
    scored = (
        [_scored(f"pentest-{i}", download=1000, stars=0, category="pentest") for i in range(5)]
        + [_scored(f"mesh-{i}", download=1000, stars=0, category="mesh") for i in range(2)]
    )
    selected, _ = drain.cap_categories(scored, max_per_category=4, batch_size=20)
    cats = [s["record"]["category"] for s in selected]
    assert cats.count("pentest") == 4
    assert cats.count("mesh") == 2


def test_cap_categories_respects_batch_size():
    scored = [_scored(f"multi-{i}", download=1000 - i, stars=0, category="multi") for i in range(3)] + \
             [_scored(f"home-{i}", download=1000 - i, stars=0, category="home") for i in range(3)]
    selected, _ = drain.cap_categories(scored, max_per_category=4, batch_size=4)
    assert len(selected) == 4


# ─────────────────────────── author_selected (writes real firmware+recipe, real guard) ───────────────────────────

FIXTURE_ID = "zzz-test-fixture-drain-firmware"


@pytest.fixture
def cleanup_fixture():
    yield
    shutil.rmtree(tools.FIRMWARE_DIR / FIXTURE_ID, ignore_errors=True)
    for rdir in (REPO / "data/recipes").glob(f"*__{FIXTURE_ID}"):
        shutil.rmtree(rdir, ignore_errors=True)
    tools.remove_run_case(FIXTURE_ID)


def _fixture_selected(**overrides):
    record = {
        "id": FIXTURE_ID, "name": "Zzz Test Fixture Firmware",
        "url": "https://github.com/octocat/Hello-World", "category": "multi",
        "board": "m5cardputer", "chip": "esp32-s3", "capabilities": ["wifi"],
        "maintainer": "octocat",
    }
    record.update(overrides)
    # stars=30 clears the popularity floor (SPEC-firmware-floor.md, STAR_FLOOR=25) — the guard
    # run_guard() triggers now mechanically enforces the floor via scripts/validate.py, so a
    # below-floor fixture would guard-red here for a reason unrelated to what these tests cover.
    return [{"record": record, "download": 100, "stars": 30, "forks": 4,
             "description": "A fixture firmware for drain tests."}]


def test_author_selected_writes_schema_valid_firmware_and_recipe(cleanup_fixture):
    authored, dropped = drain.author_selected(_fixture_selected(), existing_ids=set())

    assert dropped == []
    assert authored == [FIXTURE_ID]
    fm = tools._frontmatter(tools.FIRMWARE_DIR / FIXTURE_ID / "firmware.md")
    jsonschema.validate(fm, FIRMWARE_SCHEMA)
    assert fm["category"] == "multi"
    assert fm["socs"] == ["esp32-s3"]
    rc = tools._frontmatter(REPO / "data/recipes" / f"m5cardputer__{FIXTURE_ID}" / "recipe.md")
    jsonschema.validate(rc, RECIPE_SCHEMA)
    assert rc["firmware"] == FIXTURE_ID
    assert rc["board"] == "m5cardputer"


def test_author_selected_stamps_popularity_block_with_citation(cleanup_fixture):
    """(a) Authoring persists a dated popularity{stars,forks,as_of} snapshot from the candidate's
    repo stars/forks (never downloads — downloads are not a stored metric), plus a `popularity`
    source citation; `today` (the run date) is injected for determinism."""
    authored, dropped = drain.author_selected(_fixture_selected(), existing_ids=set(),
                                              today="2026-09-01")

    assert dropped == []
    assert authored == [FIXTURE_ID]
    fm = tools._frontmatter(tools.FIRMWARE_DIR / FIXTURE_ID / "firmware.md")
    jsonschema.validate(fm, FIRMWARE_SCHEMA)
    # _fixture_selected(): stars=30, forks=4
    assert fm["popularity"] == {"stars": 30, "forks": 4, "as_of": "2026-09-01"}
    assert "downloads" not in fm["popularity"]
    assert any(s["field"] == "popularity" and s["verified"] == "2026-09-01"
               for s in fm["sources"])


def test_author_selected_dedups_against_existing_ids(cleanup_fixture):
    authored, dropped = drain.author_selected(_fixture_selected(), existing_ids={FIXTURE_ID})

    assert authored == []
    assert dropped[0]["id"] == FIXTURE_ID
    assert "id_already_catalogued" in dropped[0]["reason"]
    assert not (tools.FIRMWARE_DIR / FIXTURE_ID).exists()


def test_author_selected_drops_and_cleans_up_on_guard_red(cleanup_fixture):
    selected = _fixture_selected(category="not-a-real-category")

    authored, dropped = drain.author_selected(selected, existing_ids=set())

    assert authored == []
    assert dropped[0]["id"] == FIXTURE_ID
    assert "guard_red" in dropped[0]["reason"]
    assert not (tools.FIRMWARE_DIR / FIXTURE_ID).exists()
    assert not list((REPO / "data/recipes").glob(f"*__{FIXTURE_ID}"))


def test_author_selected_second_candidate_still_authored_after_first_is_dropped(cleanup_fixture):
    """A guard-red candidate must not poison the rest of the batch."""
    bad = _fixture_selected(category="not-a-real-category")[0]
    good = _fixture_selected()[0]
    good["record"] = dict(good["record"])

    authored, dropped = drain.author_selected([bad, good], existing_ids=set())

    assert authored == [FIXTURE_ID]
    assert len(dropped) == 1
    assert dropped[0]["reason"].startswith("guard_red")


def test_author_selected_reports_author_error_without_touching_guard(monkeypatch, cleanup_fixture):
    """author_firmware_and_recipes() itself can refuse (e.g. no catalogued board with a known
    soc) — that must be reported as author_error and never even reach run_guard()."""
    monkeypatch.setattr(tools, "author_firmware_and_recipes",
                        lambda **kw: {"error": "no catalogued board with a known soc"})
    monkeypatch.setattr(tools, "run_guard",
                        lambda: pytest.fail("run_guard() must not be called after an author error"))

    authored, dropped = drain.author_selected(_fixture_selected(), existing_ids=set())

    assert authored == []
    assert dropped == [{"id": FIXTURE_ID, "reason": "author_error: no catalogued board with a known soc"}]


# ─────────────────────────── _readme_title / default_fetch_meta ───────────────────────────

def test_readme_title_extracts_first_heading():
    assert drain._readme_title("some preamble\n# My Firmware Title\nbody text") == "My Firmware Title"


def test_readme_title_strips_leading_hashes_and_whitespace():
    assert drain._readme_title("### Deeply Nested Heading  \nmore") == "Deeply Nested Heading"


def test_readme_title_none_when_no_heading():
    assert drain._readme_title("just plain text, no markdown heading") is None


def test_readme_title_none_for_empty_or_none_input():
    assert drain._readme_title(None) is None
    assert drain._readme_title("") is None


def test_default_fetch_meta_combines_repo_and_readme(monkeypatch):
    monkeypatch.setattr(tools, "fetch_github_repo",
                        lambda url: {"full_name": "someone/tool", "fork": False, "stars": 12,
                                    "description": "A tool.", "license": "MIT"})
    monkeypatch.setattr(tools, "fetch_github_readme", lambda url: "# The Tool README\nmore text")

    meta = drain.default_fetch_meta("https://github.com/someone/tool")

    assert meta["full_name"] == "someone/tool"
    assert meta["stars"] == 12
    assert meta["readme_title"] == "The Tool README"


def test_default_fetch_meta_short_circuits_on_repo_error(monkeypatch):
    monkeypatch.setattr(tools, "fetch_github_repo", lambda url: {"error": "404"})
    monkeypatch.setattr(tools, "fetch_github_readme",
                        lambda url: pytest.fail("fetch_github_readme must not be called after a repo error"))

    meta = drain.default_fetch_meta("https://github.com/ghost/dead")

    assert meta == {"error": "404"}


# ─────────────────────────── run_drain (full pipeline, mocked I/O) ───────────────────────────

def test_run_drain_full_pipeline_authors_a_clean_candidate(cleanup_fixture):
    entry = {
        "name": "Zzzuniq Sentinelprobe Gadget", "description": "WiFi deauther and packet sniffer gadget.",
        "category": "cardputer", "github": f"https://github.com/octocat/{FIXTURE_ID}", "download": 777,
    }
    meta = {"full_name": f"octocat/{FIXTURE_ID}", "fork": False, "source_full_name": None, "stars": 55,
            "description": "WiFi deauth tool for the Cardputer.", "license": None, "readme_title": None}

    report = drain.run_drain(fetch_catalog=lambda: [entry], fetch_meta=lambda url: meta)

    assert report["fetched"] == 1
    assert report["prefiltered"] == 1
    assert report["scored_clean"] == 1
    assert report["skipped_scoring"] == 0
    assert report["selected"] == 1
    assert report["authored"] == [FIXTURE_ID]
    assert report["dropped_guard"] == []
    assert report["guard"]["ok"] is True

    fm = tools._frontmatter(tools.FIRMWARE_DIR / FIXTURE_ID / "firmware.md")
    jsonschema.validate(fm, FIRMWARE_SCHEMA)
    assert fm["category"] == "pentest"


def test_run_drain_reports_skips_and_authors_nothing_when_catalog_is_all_noise():
    entry = {"name": "ESP32 Doom Port", "github": "https://github.com/someone/esp32-doom", "download": 999999}

    report = drain.run_drain(fetch_catalog=lambda: [entry], fetch_meta=lambda url: pytest.fail("no network"))

    assert report["fetched"] == 1
    assert report["prefiltered"] == 0
    assert report["scored_clean"] == 0
    assert report["authored"] == []
    assert report["guard"]["ok"] is True


def test_run_drain_skips_a_candidate_already_proposed_in_an_injected_ledger(tmp_path, cleanup_fixture):
    """A second run within the same review window (same ledger, unmerged) must NOT re-author an
    id it already proposed — the end-to-end proof of deliverable 3."""
    entry = {
        "name": "Zzzuniq Sentinelprobe Gadget", "description": "WiFi deauther and packet sniffer gadget.",
        "category": "cardputer", "github": f"https://github.com/octocat/{FIXTURE_ID}", "download": 777,
    }
    meta = {"full_name": f"octocat/{FIXTURE_ID}", "fork": False, "source_full_name": None, "stars": 55,
            "description": "WiFi deauth tool for the Cardputer.", "license": None, "readme_title": None}
    ledger_path = tmp_path / "proposed_ledger.json"
    ledger.record_proposed(FIXTURE_ID, f"octocat/{FIXTURE_ID}", pr_ref="https://github.com/x/y/pull/1",
                           path=ledger_path)

    report = drain.run_drain(fetch_catalog=lambda: [entry], fetch_meta=lambda url: meta, ledger_path=ledger_path)

    assert report["prefiltered"] == 0        # blocked at prefilter, before any (fake) network fetch
    assert report["authored"] == []
    assert not (tools.FIRMWARE_DIR / FIXTURE_ID).exists()
