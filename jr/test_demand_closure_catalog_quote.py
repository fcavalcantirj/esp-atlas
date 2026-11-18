"""Autonomous RECONCILE closure of `catalog_quote` work (hygiene): after the fix PR merges, the record AS
MERGED is re-checked with scripts/check_quotes.py through the injected page getter; PASS closes, FAIL and
INCONCLUSIVE stay pending. No git, no network: `git show` and the pages are fakes."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import demand_closure
import research_work as rw

DAY = "2026-11-18"
NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
MERGE = "978cf97f" + "0" * 32
URL = "https://docs.m5stack.com/en/core/M5Dial"
QUOTE = {"record": "data/boards/m5stack/m5dial/board.md", "id": "m5dial", "report_date": "2026-11-17",
         "quotes": ["PORT.A | G13 | G15"], "urls": [URL]}
RECORD = '''---
id: m5dial
type: board
brand: m5stack
name: Dial
soc: esp32-s3
notes:
- 'The docs table reads "PORT.A GND 5V G13 G15" for the Grove port'
sources:
- field: '*'
  url: https://docs.m5stack.com/en/core/M5Dial
  verified: '2026-11-18'
---

Body.
'''
PAGE = b"<html><body><table><tr><td>PORT.A</td><td>GND</td><td>5V</td><td>G13</td><td>G15</td></tr></table></body></html>"


def candidate():
    return {"term": rw.quote_term(QUOTE), "source": rw.SOURCE_QUOTE, "status": rw.STATUS_LINKED, "first_seen": "2026-11-17",
            "history": [], "linked_work": ["https://github.com/o/r/pull/9"], "quote": dict(QUOTE),
            "validation": {"verified_on": DAY, "forbidden_ids": [], "verification_kind": rw.KIND_CATALOG_QUOTE,
                           "validated_by": "executor", "primary_sources": [URL], "expected_ids": ["m5dial"],
                           "identity_verified": True, "term_key": rw.term_key(rw.quote_term(QUOTE))}}


def pr():
    return {"url": "https://github.com/o/r/pull/9", "state": "MERGED", "merged": True, "merge_sha": MERGE, "merged_at": f"{DAY}T10:00:00Z"}


def git_show(text=RECORD, rc=0):
    def git(*args):
        assert args[:1] == ("show",) and args[1] == f"{MERGE}:{QUOTE['record']}"
        return SimpleNamespace(returncode=rc, stdout=text, stderr="")
    return git


def fetch(pages):
    def get(url):
        return pages.get(url, (404, b""))
    return get


def test_a_pass_at_the_merge_builds_a_closing_receipt():
    rec, why = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, git=git_show(), now=NOW,
                                      fetch=fetch({URL: (200, PAGE)}))
    assert why == "" and rec["kind"] == rw.KIND_CATALOG_QUOTE and rec["verdict"] == "PASS"
    assert rec["record"] == QUOTE["record"] and rec["id"] == "m5dial" and rec["merge_sha"] == MERGE
    problem, _fields = rw._KIND_CHECKS[rw.KIND_CATALOG_QUOTE]
    assert problem(rec, ["m5dial"], []) is None


def test_a_quote_the_page_still_lacks_stays_pending():
    bad = RECORD.replace("PORT.A GND 5V G13 G15", "PORT.A | G13 | G15 | G99")
    rec, why = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, git=git_show(bad), now=NOW,
                                      fetch=fetch({URL: (200, PAGE)}))
    assert rec["verdict"] == "FAIL" and rw._KIND_CHECKS[rw.KIND_CATALOG_QUOTE][0](rec, ["m5dial"], []) is not None


def test_a_page_that_does_not_answer_is_inconclusive_not_a_verdict():
    rec, _ = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, git=git_show(), now=NOW,
                                    fetch=fetch({URL: (503, b"")}))
    assert rec["verdict"] == "INCONCLUSIVE"


def test_a_record_the_merge_does_not_hold_or_no_getter_builds_no_receipt():
    rec, why = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, git=git_show(rc=1, text=""), now=NOW,
                                      fetch=fetch({URL: (200, PAGE)}))
    assert rec is None and "not readable at" in why
    rec, why = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, git=git_show(), now=NOW, fetch=None)
    assert rec is None and "none is invented" in why


def test_a_record_without_quoted_text_after_the_fix_passes():
    """The executor may remove the quote marks (cite-or-omit): nothing left to check is a PASS."""
    plain = RECORD.replace('- \'The docs table reads "PORT.A GND 5V G13 G15" for the Grove port\'', "- The Grove port carries G13 and G15")
    rec, _ = demand_closure.observe(candidate(), pr(), {}, mined_revision=None, git=git_show(plain), now=NOW,
                                    fetch=fetch({URL: (200, PAGE)}))
    assert rec["verdict"] == "PASS" and rec["quotes"] == []
