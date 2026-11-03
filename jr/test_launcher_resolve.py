"""Tests for jr/launcher_resolve.py — the deterministic repo resolver for launcher entries whose
`github` is None or owner-only (G1b, 2026-11-03). Pure functions plus one injected `gh`; no network.
Fixtures are shaped exactly like api.launcherhub.net/giveMeTheList rows."""
from __future__ import annotations

import json
import urllib.parse
from types import SimpleNamespace

import pytest

import launcher_resolve as lr
from budget import BudgetExceeded

IBUTTON = {"fid": "ec0b5f11b7a6a85445a1d4dc5ad65508", "name": "IButton M5Stick C Plus2",
           "author": "geo_tp", "github": "https://github.com/geo-tp", "category": "stickc",
           "download": 214, "description": None}
NONE_ENTRY = {"fid": "aa11bb22cc33dd44ee55ff6677889900", "name": "Pocket Synth",
              "author": "Muart", "github": None, "category": "cardputer", "download": 90}


def _item(full_name):
    return {"full_name": full_name, "name": full_name.split("/")[1], "stargazers_count": 3}


def _gh(doc, calls, returncode=0):
    def gh(*a):
        calls.append(a)
        return SimpleNamespace(returncode=returncode, stdout=json.dumps(doc), stderr="422 bad user")
    return gh


def _q(call):
    """The decoded `q=` of a recorded `gh api search/repositories?...` call."""
    return urllib.parse.parse_qs(urllib.parse.urlsplit(call[1]).query)["q"][0]


# --- which entries need resolving -------------------------------------------------------------

@pytest.mark.parametrize("github, expected", [
    (None, True), ("", True), ("   ", True),
    ("https://github.com/geo-tp", True), ("https://github.com/irisihrz/", True),
    ("https://github.com/geo-tp/M5Stick-IButton", False),
    ("http://maker.peien.xyz/", False),            # a non-GitHub homepage: not this resolver's job
    ("Volos-TV-Remote", False),                    # junk text: stays on the existing unresolved path
])
def test_needs_resolution_is_none_empty_or_owner_only(github, expected):
    assert lr.needs_resolution({"github": github}) is expected


def test_owner_comes_from_the_owner_only_url_first():
    assert lr.owner_hint(dict(IBUTTON, author="someone_else")) == "geo-tp"


@pytest.mark.parametrize("author, owner", [
    ("geo_tp", "geo-tp"), ("Muart", "muart"), ("_0m3gx", "0m3gx"), ("Some Body", "some-body"),
    ("___", None), ("", None), (None, None),
])
def test_owner_falls_back_to_the_author_normalized_to_a_github_login(author, owner):
    assert lr.owner_hint({"github": None, "author": author}) == owner


def test_significant_tokens_drop_device_family_and_filler_words():
    assert lr.significant_tokens("IButton M5Stick C Plus2") == ["ibutton"]
    assert lr.significant_tokens("Marauder 0.13.6 For M5stickcplus2") == ["marauder"]
    assert lr.significant_tokens("2048") == ["2048"]
    assert lr.significant_tokens("") == []


def test_query_is_name_tokens_plus_user_owner():
    assert lr.build_query(IBUTTON) == "ibutton user:geo-tp"
    assert lr.build_query(NONE_ENTRY) == "pocket synth user:muart"
    assert lr.build_query({"name": "Cardputer M5Stick", "github": None, "author": "x"}) is None


def test_no_known_owner_means_no_query_never_a_global_search():
    """Without user:<owner> a lone token-matching hit would be a stranger's repo admitted under the
    launcher entry's name — inconclusive instead (14 live entries have an author with no login form)."""
    assert lr.build_query({"name": "Rare Radio Toy", "github": None, "author": "___"}) is None
    assert lr.build_query({"name": "Rare Radio Toy", "github": None, "author": None}) is None


def test_ledger_key_is_the_launcher_fid_and_never_empty():
    assert lr.ledger_key(IBUTTON) == ("launcher-ec0b5f11b7a6a85445a1d4dc5ad65508",
                                      "launcher:ec0b5f11b7a6a85445a1d4dc5ad65508")
    assert lr.ledger_key({"fid": "", "github": None}) is None
    assert lr.ledger_key({"github": None}) is None
    assert lr.ledger_key({"fid": 1234, "github": None}) == ("launcher-1234", "launcher:1234")


# --- resolving --------------------------------------------------------------------------------

def test_owner_only_entry_resolves_to_the_one_repo_whose_name_shares_a_token():
    calls = []
    doc = {"total_count": 2, "incomplete_results": False,
           "items": [_item("geo-tp/M5Stick-IButton"), _item("geo-tp/ESP32-Bus-Pirate")]}
    res = lr.resolve(IBUTTON, _gh(doc, calls))
    assert res["repo"] == "geo-tp/M5Stick-IButton"
    assert len(calls) == 1 and calls[0][0] == "api" and calls[0][1].startswith("search/repositories?")
    assert _q(calls[0]) == "ibutton user:geo-tp"


def test_two_matching_hits_are_ambiguous_and_resolve_to_nothing():
    calls = []
    doc = {"total_count": 2, "items": [_item("muart/pocket-synth"), _item("muart/synth-pocket-v2")]}
    res = lr.resolve(NONE_ENTRY, _gh(doc, calls))
    assert res["repo"] is None and res["matches"] == ["muart/pocket-synth", "muart/synth-pocket-v2"]


def test_zero_hits_resolve_to_nothing():
    res = lr.resolve(NONE_ENTRY, _gh({"total_count": 0, "items": []}, []))
    assert res["repo"] is None and res["matches"] == []


def test_a_hit_whose_name_shares_no_token_is_not_a_match():
    doc = {"total_count": 1, "items": [_item("muart/dotfiles")]}
    assert lr.resolve(NONE_ENTRY, _gh(doc, []))["repo"] is None


def test_a_truncated_result_page_cannot_prove_uniqueness():
    doc = {"total_count": 40, "items": [_item("muart/pocket-synth")]}
    assert lr.resolve(NONE_ENTRY, _gh(doc, []))["repo"] is None


def test_a_failed_search_resolves_to_nothing_with_the_error():
    res = lr.resolve(NONE_ENTRY, _gh({}, [], returncode=1))
    assert res["repo"] is None and "422" in res["error"]


def test_no_searchable_tokens_makes_no_call():
    calls = []
    res = lr.resolve({"fid": "f", "name": "Cardputer", "github": None, "author": "a"}, _gh({}, calls))
    assert res["repo"] is None and calls == []


def test_budget_exceeded_propagates():
    def gh(*a):
        raise BudgetExceeded("call budget exhausted")
    with pytest.raises(BudgetExceeded):
        lr.resolve(NONE_ENTRY, gh)


def test_the_per_tick_cap_fits_inside_the_tick_budget():
    from budget import DEFAULT_MAX_CALLS
    assert 0 < lr.RESOLVER_CALLS_PER_TICK < DEFAULT_MAX_CALLS // 4
