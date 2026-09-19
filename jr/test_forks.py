"""EspAtlas Jr — pytest for jr/forks.py (fork -> canonical-source resolution).

Fully offline: `api` is always a hand-built fake keyed on real, catalog-style fixtures (never
lorem/animal names) — no network call ever happens in this file.

Run: cd jr && python3 -m pytest test_forks.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import forks  # noqa: E402


def _fake_api(mapping: dict) -> callable:
    """mapping: {"owner/repo": <raw gh api repos/OWNER/REPO shape>}. Missing keys -> {} (mirrors
    default_api's own unresolved-repo return)."""
    def _api(owner: str, repo: str) -> dict:
        return mapping.get(f"{owner}/{repo}", {})
    return _api


def _fake_search(mapping: dict) -> callable:
    """mapping: {query_string: [<raw gh search repos --json fullName,stargazersCount,isFork
    shape, already normalized to full_name/stars/fork>]}. Missing keys -> [] (mirrors
    default_search's own no-results return)."""
    def _search(name_token: str) -> list:
        return mapping.get(name_token, [])
    return _search


def test_resolve_source_returns_itself_for_a_non_fork():
    api = _fake_api({
        "justcallmekoko/ESP32Marauder": {
            "full_name": "justcallmekoko/ESP32Marauder", "fork": False,
            "stargazers_count": 4200, "forks_count": 650,
        },
    })
    result = forks.resolve_source("justcallmekoko", "ESP32Marauder", api)
    assert result == {"full_name": "justcallmekoko/ESP32Marauder", "stars": 4200, "forks": 650}


def test_resolve_source_resolves_a_fork_via_source_field():
    api = _fake_api({
        "someoneelse/ESP32Marauder": {
            "full_name": "someoneelse/ESP32Marauder", "fork": True,
            "stargazers_count": 3, "forks_count": 0,
            "source": {"full_name": "justcallmekoko/ESP32Marauder",
                       "stargazers_count": 4200, "forks_count": 650},
        },
    })
    result = forks.resolve_source("someoneelse", "ESP32Marauder", api)
    assert result == {"full_name": "justcallmekoko/ESP32Marauder", "stars": 4200, "forks": 650}


def test_resolve_source_walks_multi_level_fork_chain_to_the_root():
    """A fork of a fork: someone/atom-watch-mod -> parent bob/atom-watch-mirror (itself a fork,
    no `.source` field either) -> parent fbiego/atom-watch (the real, non-fork root). Neither
    intermediate hop carries a `.source` pointer, so resolution MUST walk `.parent` twice to
    reach the root, not stop at the first hop."""
    api = _fake_api({
        "someone/atom-watch-mod": {
            "full_name": "someone/atom-watch-mod", "fork": True,
            "stargazers_count": 1, "forks_count": 0,
            "parent": {"full_name": "bob/atom-watch-mirror"},
        },
        "bob/atom-watch-mirror": {
            "full_name": "bob/atom-watch-mirror", "fork": True,
            "stargazers_count": 2, "forks_count": 0,
            "parent": {"full_name": "fbiego/atom-watch"},
        },
        "fbiego/atom-watch": {
            "full_name": "fbiego/atom-watch", "fork": False,
            "stargazers_count": 48, "forks_count": 6,
        },
    })
    result = forks.resolve_source("someone", "atom-watch-mod", api)
    assert result == {"full_name": "fbiego/atom-watch", "stars": 48, "forks": 6}


def test_resolve_source_stops_at_an_unresolvable_parent_mid_chain():
    """A multi-hop walk where the NEXT parent hop can't be fetched (rate-limited/deleted) —
    resolution stops there, reporting that unresolved parent at zero stars/forks rather than
    silently falling back further or raising."""
    api = _fake_api({
        "someone/atom-watch-mod": {
            "full_name": "someone/atom-watch-mod", "fork": True,
            "stargazers_count": 1, "forks_count": 0,
            "parent": {"full_name": "ghost/vanished-parent"},
        },
    })
    result = forks.resolve_source("someone", "atom-watch-mod", api)
    assert result == {"full_name": "ghost/vanished-parent", "stars": 0, "forks": 0}


def test_resolve_source_falls_back_to_own_repo_when_unresolvable():
    """api returns {} (repo not found / rate-limited) — resolve_source degrades to the
    owner/repo it was asked about, at zero stars/forks, rather than raising."""
    api = _fake_api({})
    result = forks.resolve_source("ghost", "vanished-repo", api)
    assert result == {"full_name": "ghost/vanished-repo", "stars": 0, "forks": 0}


def test_default_api_shape_is_injectable_not_called_by_resolve_source_directly():
    """resolve_source never imports/calls forks.default_api itself — the caller always injects
    `api` explicitly (this is what keeps every test above network-free)."""
    calls = []

    def _spy_api(owner, repo):
        calls.append((owner, repo))
        return {"full_name": f"{owner}/{repo}", "fork": False, "stargazers_count": 9, "forks_count": 1}

    result = forks.resolve_source("acme", "widget", _spy_api)
    assert calls == [("acme", "widget")]
    assert result["full_name"] == "acme/widget"


# ─────────────────────── resolve_canonical (conceptual-port lineage, jr/forks.py) ───────────────────────
# The RogueDuck-audit gap: resolve_source only catches a real git button-fork (repo_meta.fork ==
# True). A repo with fork=False that CONCEPTUALLY reimplements a more-canonical, not-yet-
# catalogued upstream sharing the same core name-token was waved through as an original.
# resolve_canonical() closes that gap with an injected `search` (gh search repositories) — kept
# deliberately conservative (exact core-token share, >=5x stars, above STAR_FLOOR) so it never
# resolves away a genuine, unrelated original.


def test_resolve_canonical_rogueduck_false_positive_guard_stays_canonical():
    """RogueDuck (fork=false, 6 stars): search on its own core tokens turns up nothing but
    itself -- must NOT be resolved away. This is the exact false-positive class the RogueDuck
    audit flagged: a real, independent project must stay canonical."""
    meta = {"full_name": "M5RogueOps/M5StickS3-RogueDuck", "fork": False,
            "stargazers_count": 6, "forks_count": 3}
    search = _fake_search({
        "m5sticks3 rogueduck": [
            {"full_name": "M5RogueOps/M5StickS3-RogueDuck", "stars": 6, "fork": False},
        ],
    })
    result = forks.resolve_canonical("M5RogueOps", "M5StickS3-RogueDuck", meta, search, _fake_api({}))
    assert result == {"full_name": "M5RogueOps/M5StickS3-RogueDuck", "stars": 6, "forks": 3}


def test_resolve_canonical_resolves_a_non_fork_conceptual_port_to_its_upstream():
    """A non-fork candidate (4 stars) sharing the exact core token "meshcore" with a
    not-yet-catalogued, far-more-starred upstream (600 stars, clears both the 5x-candidate and
    the STAR_FLOOR bars) resolves to that upstream. A same-search low-star sibling (3 stars,
    below STAR_FLOOR) must NOT win even though it shares a token too."""
    meta = {"full_name": "portauthor/meshcore-cardputer-port", "fork": False,
            "stargazers_count": 4, "forks_count": 0}
    search = _fake_search({
        "cardputer meshcore port": [
            {"full_name": "sosprz/meshcore-cardputer-adv", "stars": 3, "fork": False},
            {"full_name": "channellabs/meshcore", "stars": 600, "fork": False},
        ],
    })
    result = forks.resolve_canonical("portauthor", "meshcore-cardputer-port", meta, search, _fake_api({}))
    assert result == {"full_name": "channellabs/meshcore", "stars": 600, "forks": 0}


def test_resolve_canonical_ignores_a_shared_generic_token():
    """candidate esp32-blinker (3 stars) and an unrelated, huge esp32-something (5000 stars)
    share ONLY the stoplisted "esp32" token -- GENERIC_NAME_TOKENS strips it from both sides
    before comparison, so no shared SIGNIFICANT token survives and nothing resolves away."""
    meta = {"full_name": "tinker/esp32-blinker", "fork": False,
            "stargazers_count": 3, "forks_count": 0}
    search = _fake_search({
        "blinker": [
            {"full_name": "somebody/esp32-something", "stars": 5000, "fork": False},
        ],
    })
    result = forks.resolve_canonical("tinker", "esp32-blinker", meta, search, _fake_api({}))
    assert result == {"full_name": "tinker/esp32-blinker", "stars": 3, "forks": 0}


def test_resolve_canonical_returns_self_when_no_significant_core_token_at_all():
    """A repo name made ENTIRELY of generic tokens (here, bare "esp32") has no significant
    core token to search on -- resolve to self without even calling `search`."""
    meta = {"full_name": "acme/esp32", "fork": False, "stargazers_count": 2, "forks_count": 0}

    def _refuse(_token):
        raise AssertionError("search must not be called with no significant core token")

    result = forks.resolve_canonical("acme", "esp32", meta, _refuse, _fake_api({}))
    assert result == {"full_name": "acme/esp32", "stars": 2, "forks": 0}


def test_resolve_canonical_real_git_fork_path_delegates_to_resolve_source_behavior():
    """meta.fork == True (a real git button-fork) resolves exactly as resolve_source() already
    does (same `.source` field, same api contract) -- `search` is never consulted for a real
    fork; the git-fork path is untouched by this change."""
    meta = {
        "full_name": "someoneelse/ESP32Marauder", "fork": True,
        "stargazers_count": 3, "forks_count": 0,
        "source": {"full_name": "justcallmekoko/ESP32Marauder",
                   "stargazers_count": 4200, "forks_count": 650},
    }

    def _refuse(_token):
        raise AssertionError("search must not be called for a real git fork")

    result = forks.resolve_canonical("someoneelse", "ESP32Marauder", meta, _refuse, _fake_api({}))
    assert result == {"full_name": "justcallmekoko/ESP32Marauder", "stars": 4200, "forks": 650}


def test_resolve_canonical_ignores_a_search_result_that_is_itself_a_fork():
    """A higher-starred search result sharing the exact core token is itself a fork (fork=True)
    -- not a canonical upstream, so it's skipped even though every other bar clears."""
    meta = {"full_name": "tinker/blinkwave", "fork": False,
            "stargazers_count": 2, "forks_count": 0}
    search = _fake_search({
        "blinkwave": [
            {"full_name": "somebody/blinkwave-mirror", "stars": 900, "fork": True},
        ],
    })
    result = forks.resolve_canonical("tinker", "blinkwave", meta, search, _fake_api({}))
    assert result == {"full_name": "tinker/blinkwave", "stars": 2, "forks": 0}


def test_resolve_canonical_requires_at_least_5x_the_candidates_stars():
    """A search result shares the exact core token and clears STAR_FLOOR, but is under 5x the
    candidate's own stars -- not a MEANINGFULLY higher-starred upstream, so it doesn't win."""
    meta = {"full_name": "tinker/blinkwave", "fork": False,
            "stargazers_count": 10, "forks_count": 0}
    search = _fake_search({
        "blinkwave": [
            {"full_name": "somebody/blinkwave-plus", "stars": 40, "fork": False},  # 4x, not 5x
        ],
    })
    result = forks.resolve_canonical("tinker", "blinkwave", meta, search, _fake_api({}))
    assert result == {"full_name": "tinker/blinkwave", "stars": 10, "forks": 0}


def test_default_search_shape_is_injectable_not_called_by_resolve_canonical_directly():
    """resolve_canonical never imports/calls forks.default_search itself -- the caller always
    injects `search` explicitly (this is what keeps every test above network-free)."""
    calls = []

    def _spy_search(name_token):
        calls.append(name_token)
        return []

    meta = {"full_name": "tinker/blinkwave", "fork": False, "stargazers_count": 2, "forks_count": 0}
    result = forks.resolve_canonical("tinker", "blinkwave", meta, _spy_search, _fake_api({}))
    assert calls == ["blinkwave"]
    assert result["full_name"] == "tinker/blinkwave"
