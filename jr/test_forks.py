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
