"""Tests for jr/research_queue.py — the zero-result site-search research queue
(SPEC-demand-research-queue.md). Pure and offline: the catalog is a fixture list except where a
test says it reads the real (read-only) data/ tree.

Run: cd jr && python3 -m pytest test_research_queue.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import research_queue as rq  # noqa: E402

TODAY = "2026-11-04"

CATALOG = [
    {"id": "lilygo-t-beam", "kind": "board", "title": "T-Beam", "aliases": ["ttgo-t-beam"]},
    {"id": "m5stick-cplus2", "kind": "board", "title": "M5StickC Plus2", "aliases": []},
    {"id": "esp32marauder", "kind": "firmware", "title": "ESP32 Marauder", "aliases": []},
    {"id": "esp32-c6", "kind": "part", "title": "ESP32-C6", "aliases": []},
    {"id": "esp32", "kind": "part", "title": "ESP32", "aliases": []},
    {"id": "lilygo", "kind": "brand", "title": "LILYGO", "aliases": []},
]


def row(term, searches=1, zero=1):
    return {"term": term, "searches": searches, "zero_result_searches": zero}


def run(rows, queue=None, today=TODAY, **kw):
    return rq.update_queue(queue or rq.empty_queue(), rows, CATALOG, today, **kw)


# ─────────────────────────── dedupe key ───────────────────────────

@pytest.mark.parametrize("variant", ["ESP32-C6", "esp32 c6", "  esp32_c6! ", "Esp32   C6", "esp32--c6"])
def test_term_key_folds_case_whitespace_punctuation_and_hyphens(variant):
    assert rq.term_key(variant) == "esp32 c6"


# ─────────────────────────── candidacy ───────────────────────────

def test_a_single_zero_result_search_creates_exactly_one_candidate():
    queue, report = run([row("es3c28p")])
    assert list(queue["candidates"]) == ["es3c28p"]
    c = queue["candidates"]["es3c28p"]
    assert c["status"] == "new"
    assert (c["searches"], c["zero_result_searches"]) == (1, 1)
    assert (c["first_seen"], c["last_seen"]) == (TODAY, TODAY)
    assert c["linked_work"] == [] and c["outcome"] is None
    assert report["opened"] == ["es3c28p"]


def test_the_same_term_in_another_case_is_one_candidate():
    queue, _ = run([row("ES3C28P"), row("es3c28p")])
    assert list(queue["candidates"]) == ["es3c28p"]


def test_a_second_day_sighting_in_another_wording_refreshes_the_same_candidate():
    queue, _ = run([row("ES3C28P")])
    queue, report = run([row("es3c28p", searches=3, zero=2)], queue=queue, today="2026-11-05")
    c = queue["candidates"]["es3c28p"]
    assert (c["first_seen"], c["last_seen"]) == (TODAY, "2026-11-05")
    assert (c["searches"], c["zero_result_searches"]) == (3, 2)   # latest window, not a sum
    assert c["term"] == "ES3C28P"                                   # first wording kept
    assert report["opened"] == [] and report["refreshed"] == ["es3c28p"]


def test_a_term_that_returned_results_creates_nothing():
    queue, report = run([row("gps", searches=1, zero=0)])
    assert queue["candidates"] == {}
    assert report["opened"] == []


def test_a_zero_result_row_without_a_submitted_search_creates_nothing():
    queue, _ = run([row("ghost", searches=0, zero=1)])
    assert queue["candidates"] == {}


# ─────────────────────────── rate limit ───────────────────────────

SIX = [row(t) for t in ("aaaa1", "bbbb2", "cccc3", "dddd4", "eeee5", "ffff6")]


def test_the_sixth_new_candidate_on_one_day_is_deferred():
    queue, report = run(SIX)
    assert len(queue["candidates"]) == 5
    assert report["deferred"] == ["ffff6"]
    assert "ffff6" not in queue["candidates"]


def test_the_daily_cap_is_configurable():
    queue, report = run(SIX, max_new_per_day=2)
    assert len(queue["candidates"]) == 2 and len(report["deferred"]) == 4


def test_the_cap_orders_by_zero_result_searches_then_searches_then_key():
    rows = [row("zzzz", 1, 1), row("yyyy", 4, 3), row("xxxx", 5, 1)]
    _, report = run(rows, max_new_per_day=2)
    assert report["opened"] == ["yyyy", "xxxx"] and report["deferred"] == ["zzzz"]


def test_a_same_day_rerun_counts_the_candidates_already_opened_today():
    queue, _ = run(SIX[:5])
    queue, report = run(SIX, queue=queue)
    assert report["opened"] == [] and report["deferred"] == ["ffff6"]


def test_a_deferred_term_opens_on_a_later_day():
    queue, _ = run(SIX)
    queue, report = run(SIX, queue=queue, today="2026-11-05")
    assert report["opened"] == ["ffff6"]


# ─────────────────────────── closed candidates ───────────────────────────

def _closed_queue(closed_on):
    queue, _ = run([row("es3c28p")], today=closed_on)
    rq.close(queue, "es3c28p", "added the board", closed_on)
    return queue


def test_a_closed_candidate_is_not_reopened_within_30_days():
    queue = _closed_queue("2026-11-04")
    before = json.dumps(queue["candidates"]["es3c28p"], sort_keys=True)
    queue, report = run([row("es3c28p")], queue=queue, today="2026-12-03")   # day 29
    assert queue["candidates"]["es3c28p"]["status"] == "closed"
    assert json.dumps(queue["candidates"]["es3c28p"], sort_keys=True) == before
    assert report["suppressed_closed"] == ["es3c28p"] and report["opened"] == []


def test_a_closed_candidate_reopens_after_30_days_with_its_history():
    queue = _closed_queue("2026-11-04")
    queue, report = run([row("es3c28p")], queue=queue, today="2026-12-04")   # day 30
    c = queue["candidates"]["es3c28p"]
    assert c["status"] == "new" and c["outcome"] is None and c["closed_on"] is None
    assert c["history"] == [{"event": "reopened", "date": "2026-12-04", "closed_on": "2026-11-04",
                             "outcome": "added the board", "linked_work": []}]
    assert report["reopened"] == ["es3c28p"]


def test_a_reopen_counts_toward_the_daily_cap():
    queue = _closed_queue("2026-10-01")
    queue, report = run([row("es3c28p", 9, 9)] + SIX, queue=queue, today="2026-11-04")
    assert report["reopened"] == ["es3c28p"] and len(report["opened"]) == 4


def test_a_closed_candidate_without_a_close_date_falls_back_to_last_seen():
    queue = _closed_queue("2026-11-04")
    queue["candidates"]["es3c28p"]["closed_on"] = None
    queue, report = run([row("es3c28p")], queue=queue, today="2026-11-20")
    assert report["suppressed_closed"] == ["es3c28p"]


# ─────────────────────────── classification ───────────────────────────

def test_a_term_with_no_catalog_match_is_missing_content():
    cls, ev = rq.classify("es3c28p", CATALOG)
    assert cls == "missing_content"
    assert ev["ids"] == [] and ev["checked"] == len(CATALOG)


def test_a_term_one_typo_from_a_board_id_is_alias_typo_with_that_id():
    cls, ev = rq.classify("lilygo-t-bem", CATALOG)
    assert cls == "alias_typo"
    assert ev["ids"] == ["lilygo-t-beam"]
    assert ev["matches"][0]["via"] == "id" and ev["matches"][0]["distance"] == 1


def test_a_term_equal_to_an_id_with_zero_results_is_a_search_defect():
    cls, ev = rq.classify("lilygo-t-beam", CATALOG)
    assert cls == "search_defect"
    assert ev["ids"] == ["lilygo-t-beam"]


def test_a_term_equal_to_a_title_is_a_search_defect_regardless_of_spacing():
    cls, ev = rq.classify("ESP32 Marauder", CATALOG)
    assert (cls, ev["ids"]) == ("search_defect", ["esp32marauder"])


def test_a_bare_generic_id_is_still_a_search_defect():
    assert rq.classify("ESP32", CATALOG)[0] == "search_defect"


def test_an_exact_alias_is_alias_typo():
    cls, ev = rq.classify("ttgo t-beam", CATALOG)
    assert (cls, ev["ids"]) == ("alias_typo", ["lilygo-t-beam"])
    assert ev["matches"][0]["via"] == "alias"


def test_the_same_tokens_in_another_order_are_alias_typo():
    cls, ev = rq.classify("plus2 m5stickc", CATALOG)
    assert (cls, ev["ids"]) == ("alias_typo", ["m5stick-cplus2"])


def test_a_name_without_its_generic_words_is_alias_typo():
    cls, ev = rq.classify("marauder", CATALOG)
    assert (cls, ev["ids"]) == ("alias_typo", ["esp32marauder"])
    assert rq.classify("esp32 c6 board", CATALOG)[1]["ids"] == ["esp32-c6"]


def test_marauder_matches_the_real_firmware_record():
    assert "esp32marauder" in rq.classify("marauder", rq.load_catalog(REPO))[1]["ids"]


def test_a_long_term_tolerates_two_edits():
    assert rq.classify("esp32marxxxer", CATALOG)[0] != "alias_typo"       # 3 edits, 13 chars
    assert rq.classify("esp32maraudr", CATALOG)[1]["ids"] == ["esp32marauder"]   # 1 edit
    assert rq.classify("esp32marudr", CATALOG)[1]["ids"] == ["esp32marauder"]    # 2 edits, 11 chars


@pytest.mark.parametrize("term", ["ab", "a-b", "esp32 board", "the firmware"])
def test_a_term_without_identity_is_unclear(term):
    cls, ev = rq.classify(term, CATALOG)
    assert cls == "unclear" and ev["rule"]


def test_a_fuzzy_match_against_more_than_three_ids_is_unclear():
    catalog = [{"id": f"abcd{i}", "kind": "board", "title": "", "aliases": []} for i in range(5)]
    cls, ev = rq.classify("abcd", catalog)
    assert cls == "unclear" and len(ev["ids"]) == 5


def test_a_new_candidate_records_its_classification_and_evidence():
    queue, _ = run([row("lilygo-t-bem")])
    c = queue["candidates"]["lilygo t bem"]
    assert c["classification"] == "alias_typo" and c["evidence"]["ids"] == ["lilygo-t-beam"]


def test_classification_refreshes_only_while_the_candidate_is_new():
    queue, _ = run([row("es3c28p")])
    rq.validate(queue, "es3c28p")
    grown = CATALOG + [{"id": "es3c28p", "kind": "board", "title": "", "aliases": []}]
    queue, _ = rq.update_queue(queue, [row("es3c28p")], grown, "2026-11-05")
    assert queue["candidates"]["es3c28p"]["classification"] == "missing_content"
    queue2, _ = run([row("es3c28p")])
    queue2, _ = rq.update_queue(queue2, [row("es3c28p")], grown, "2026-11-05")
    assert queue2["candidates"]["es3c28p"]["classification"] == "search_defect"


# ─────────────────────────── the real catalog (read-only) ───────────────────────────

REPO = Path(__file__).resolve().parent.parent


def test_the_real_catalog_indexes_boards_firmware_parts_and_brands():
    catalog = rq.load_catalog(REPO)
    kinds = {e["kind"] for e in catalog}
    assert kinds == {"board", "firmware", "part", "brand"}
    beam = next(e for e in catalog if e["id"] == "lilygo-t-beam")
    assert beam["title"] == "T-Beam" and "ttgo-t-beam" in beam["aliases"]


def test_es3c28p_has_no_match_in_the_real_catalog():
    assert rq.classify("es3c28p", rq.load_catalog(REPO))[0] == "missing_content"


def test_a_typo_of_a_real_board_id_is_alias_typo():
    cls, ev = rq.classify("lilygo-t-bea", rq.load_catalog(REPO))
    assert cls == "alias_typo" and "lilygo-t-beam" in ev["ids"]


# ─────────────────────────── lifecycle ───────────────────────────

def test_validate_link_close_connects_a_candidate_to_work_and_records_the_outcome():
    queue, _ = run([row("es3c28p")])
    rq.validate(queue, "ES3C28P")
    rq.link(queue, "es3c28p", "https://github.com/fcavalcantirj/esp-atlas/pull/1500")
    rq.close(queue, "es3c28p", "board record added", "2026-11-10")
    c = queue["candidates"]["es3c28p"]
    assert c["status"] == "closed" and c["closed_on"] == "2026-11-10"
    assert c["linked_work"] == ["https://github.com/fcavalcantirj/esp-atlas/pull/1500"]
    assert c["outcome"] == "board record added"


def test_work_can_only_be_linked_to_a_validated_candidate():
    queue, _ = run([row("es3c28p")])
    with pytest.raises(ValueError, match="validated"):
        rq.link(queue, "es3c28p", "#1500")


def test_only_a_new_candidate_can_be_validated_and_a_closed_one_cannot_be_closed_again():
    queue, _ = run([row("es3c28p")])
    rq.validate(queue, "es3c28p")
    with pytest.raises(ValueError):
        rq.validate(queue, "es3c28p")
    rq.close(queue, "es3c28p", "dup", TODAY)
    with pytest.raises(ValueError):
        rq.close(queue, "es3c28p", "dup", TODAY)


def test_an_unknown_term_is_refused():
    with pytest.raises(KeyError):
        rq.validate(rq.empty_queue(), "nope")


def test_a_linked_candidate_keeps_refreshing_last_seen():
    queue, _ = run([row("es3c28p")])
    rq.validate(queue, "es3c28p")
    rq.link(queue, "es3c28p", "#1500")
    queue, report = run([row("es3c28p")], queue=queue, today="2026-11-09")
    c = queue["candidates"]["es3c28p"]
    assert c["status"] == "linked" and c["last_seen"] == "2026-11-09"
    assert report["refreshed"] == ["es3c28p"]


# ─────────────────────────── file I/O + digest ───────────────────────────

def test_the_queue_round_trips_and_a_missing_file_is_an_empty_queue(tmp_path):
    path = tmp_path / "research-queue.json"
    assert rq.load_queue(path) == rq.empty_queue()
    queue, _ = run([row("es3c28p")])
    rq.write_queue(queue, path)
    assert rq.load_queue(path) == queue
    assert path.read_text().endswith("\n")


def test_an_unreadable_queue_file_is_refused_not_silently_reset(tmp_path):
    path = tmp_path / "research-queue.json"
    path.write_text("{not json")
    with pytest.raises(ValueError):
        rq.load_queue(path)


def test_the_digest_line_counts_opened_deferred_and_open_classifications():
    queue, report = run(SIX + [row("lilygo-t-bem")])
    line = rq.digest_line(queue, report)
    assert "+5 new" in line and "2 deferred" in line
    assert "5 open" in line and "missing_content 5" in line


def test_the_cli_validates_links_and_closes_in_the_queue_file(tmp_path, capsys):
    path = tmp_path / "research-queue.json"
    queue, _ = run([row("es3c28p")])
    rq.write_queue(queue, path)
    assert rq.main(["--queue", str(path), "validate", "ES3C28P"]) == 0
    assert rq.main(["--queue", str(path), "link", "es3c28p", "#1500"]) == 0
    assert rq.main(["--queue", str(path), "close", "es3c28p", "added", "--date", "2026-11-10"]) == 0
    c = rq.load_queue(path)["candidates"]["es3c28p"]
    assert (c["status"], c["linked_work"], c["outcome"]) == ("closed", ["#1500"], "added")


def test_the_cli_reports_a_refused_transition_without_writing(tmp_path, capsys):
    path = tmp_path / "research-queue.json"
    queue, _ = run([row("es3c28p")])
    rq.write_queue(queue, path)
    before = path.read_text()
    assert rq.main(["--queue", str(path), "link", "es3c28p", "#1"]) == 1
    assert path.read_text() == before
    assert "validated" in capsys.readouterr().err


# ─────────────────────────── checker findings (2026-11-04) ───────────────────────────

def test_a_non_ascii_term_is_kept_and_folded_not_dropped():
    assert rq.term_key("Módulo  ESP32") == "módulo esp32"
    queue, report = run([row("开发板")])
    assert report["opened"] == ["开发板"]


def test_close_refuses_a_date_that_is_not_iso():
    queue, _ = run([row("es3c28p")])
    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        rq.close(queue, "es3c28p", "fixed", "2026/11/04")
    assert queue["candidates"]["es3c28p"]["status"] == "new"


def test_a_closed_candidate_with_no_readable_date_is_never_reopened():
    queue = _closed_queue("2026-11-04")
    queue["candidates"]["es3c28p"].update(closed_on="garbage", last_seen=None)
    queue, report = run([row("es3c28p")], queue=queue, today="2027-06-01")
    assert report["suppressed_closed"] == ["es3c28p"]


def test_the_queue_files_own_cap_and_reopen_window_are_enforced():
    queue = rq.empty_queue()
    queue.update(max_new_per_day=2, reopen_after_days=7)
    queue, report = rq.update_queue(queue, SIX, CATALOG, TODAY)
    assert len(report["opened"]) == 2
    rq.close(queue, "aaaa1", "done", TODAY)
    queue, report = rq.update_queue(queue, [row("aaaa1")], CATALOG, "2026-11-11")
    assert report["reopened"] == ["aaaa1"]
