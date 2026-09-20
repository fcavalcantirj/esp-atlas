"""EspAtlas Jr — pytest for the GitHub-topics dry-run yield driver (jr/ingest_topics.py).

Covers: run_ingest end-to-end producing the expected would-admit/reject-reason buckets while
writing NOTHING — no firmware dir created, no ledger file changed. Both the topic-search client
and the GitHub metadata client are fakes; no network call is made.

Run: cd jr && python3 -m pytest test_ingest_topics.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ingest_topics  # noqa: E402
import ledger  # noqa: E402
from ingest_common import _reason_bucket  # noqa: E402

_SEARCH_RESULTS = {
    "cardputer": [
        {"full_name": "known/repo"},
        {"full_name": "already/proposed"},
        {"full_name": "newco/cardputer-ghost-esp"},
        {"full_name": "newco/mystery-widget"},
        {"full_name": "dead/repo"},
        {"full_name": "newco/cardputer-tiny-tool"},
    ],
}

_META = {
    "newco/cardputer-ghost-esp": {"full_name": "newco/cardputer-ghost-esp", "fork": False,
                                  "stars": 42, "forks": 5, "description": "Ghost pentest tool for the Cardputer",
                                  "homepage": None},
    "newco/mystery-widget": {"full_name": "newco/mystery-widget", "fork": False,
                             "stars": 100, "forks": 10, "description": "Does mysterious things",
                             "homepage": None},
    "dead/repo": {"error": "404"},
    "newco/cardputer-tiny-tool": {"full_name": "newco/cardputer-tiny-tool", "fork": False,
                                  "stars": 2, "forks": 0, "description": "Tiny cardputer tool",
                                  "homepage": None},
}


def _fake_search_topic(topic, per_page):
    return _SEARCH_RESULTS.get(topic, [])


def _fake_fetch_meta(url):
    key = url.rstrip("/").replace("https://github.com/", "").lower()
    return _META.get(key, {"error": "not found"})


def _seed_catalog(tmp_path):
    firmware_dir = tmp_path / "firmware"
    fw = firmware_dir / "known-fw"
    fw.mkdir(parents=True)
    (fw / "firmware.md").write_text(
        "---\nid: known-fw\nname: Known Firmware\nurl: https://github.com/known/repo\n---\nbody\n")
    return firmware_dir


def _seed_ledger(tmp_path):
    path = tmp_path / "proposed_ledger.json"
    ledger.record_proposed("proposed-fw", "already/proposed", path=path)
    return path


# ─────────────────────────── run_ingest end to end ───────────────────────────

def test_run_ingest_produces_expected_buckets_and_writes_nothing(tmp_path):
    firmware_dir = _seed_catalog(tmp_path)
    ledger_path = _seed_ledger(tmp_path)
    ledger_bytes_before = ledger_path.read_bytes()

    report = ingest_topics.run_ingest(
        topics=["cardputer"],
        search_topic=_fake_search_topic,
        fetch_meta=_fake_fetch_meta,
        ledger_path=ledger_path,
        firmware_dir=firmware_dir,
    )

    assert report["total_candidates"] == 6
    assert report["already_known"] == 2   # known/repo (catalogued) + already/proposed (ledger)

    admitted_ids = {s["record"]["id"] for s in report["would_admit"]}
    assert admitted_ids == {"cardputer-ghost-esp"}

    reasons = {(s["github"], _reason_bucket(s["reason"])) for s in report["rejected"]}
    assert ("https://github.com/newco/mystery-widget", "no_board_evidence") in reasons
    assert ("https://github.com/dead/repo", "repo_unresolved") in reasons
    assert ("https://github.com/newco/cardputer-tiny-tool", "below-popularity-floor") in reasons
    assert len(report["rejected"]) == 3

    # writes nothing: only the pre-seeded firmware dir exists, ledger file is byte-identical
    assert [d.name for d in firmware_dir.iterdir()] == ["known-fw"]
    assert ledger_path.read_bytes() == ledger_bytes_before


def test_run_ingest_defaults_to_default_topics_when_none_given(tmp_path, monkeypatch):
    firmware_dir = _seed_catalog(tmp_path)
    ledger_path = _seed_ledger(tmp_path)

    seen_topics = []

    def search_topic(topic, per_page):
        seen_topics.append(topic)
        return _SEARCH_RESULTS.get(topic, [])

    ingest_topics.run_ingest(
        search_topic=search_topic,
        fetch_meta=_fake_fetch_meta,
        ledger_path=ledger_path,
        firmware_dir=firmware_dir,
    )

    from source_topics import DEFAULT_TOPICS
    assert seen_topics == DEFAULT_TOPICS


def test_print_report_runs_without_writing(tmp_path, capsys):
    firmware_dir = _seed_catalog(tmp_path)
    ledger_path = _seed_ledger(tmp_path)

    report = ingest_topics.run_ingest(
        topics=["cardputer"],
        search_topic=_fake_search_topic,
        fetch_meta=_fake_fetch_meta,
        ledger_path=ledger_path,
        firmware_dir=firmware_dir,
    )
    ingest_topics.print_report(report)

    out = capsys.readouterr().out
    assert "would-admit" in out
    assert "total candidates: 6" in out
    assert "already known: 2" in out
    assert "would admit: 1" in out
    assert [d.name for d in firmware_dir.iterdir()] == ["known-fw"]
