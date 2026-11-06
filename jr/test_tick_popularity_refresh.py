"""End-to-end tick routing for the real popularity stage with recorded git/GitHub effects."""
from __future__ import annotations

import json

import stage_popularity_refresh
from test_tick import NOW, Proc, checkout, gh_with_prs, git_ok, run, wt_dir  # noqa: F401
from test_tick_review import _review_pr

REL = "data/firmware/tool/firmware.md"
ORIGINAL = """---
id: tool
type: firmware
name: Tool
url: https://github.com/o/tool
category: multi
socs:
- esp32-s3
popularity:
  stars: 30
  forks: 5
  as_of: '2026-09-01'
sources:
- field: '*'
  url: https://github.com/o/tool
  verified: '2026-09-01'
- field: popularity
  url: https://github.com/o/tool
  verified: '2026-09-01'
---

Tool firmware.
"""


def _git(wt_dir, original):
    base = git_ok(wt_dir, diff=f"M\0{REL}\0")

    def git(*args):
        norm = args[2:] if args[:1] == ("-C",) else args
        if norm == ("show", f"HEAD:{REL}"):
            base.calls.append(args)
            return Proc(stdout=original)
        if norm == ("show", f":{REL}"):
            base.calls.append(args)
            return Proc(stdout=(wt_dir / REL).read_text())
        return base(*args)
    git.calls = base.calls
    return git


def _gh(prs):
    base = gh_with_prs(prs)

    def gh(*args):
        if args == ("api", "repos/o/tool"):
            base.calls.append(args)
            return Proc(stdout=json.dumps({"full_name": "o/tool", "id": 123,
                                           "stargazers_count": 31, "forks_count": 6}))
        return base(*args)
    gh.calls = base.calls
    return gh


def _prepare(wt_dir, text=ORIGINAL):
    path = wt_dir / REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_legacy_refresh_publishes_auto_once_below_cap_and_not_again_when_fresh(wt_dir):
    path = _prepare(wt_dir)
    git, gh = _git(wt_dir, ORIGINAL), _gh([])
    when = NOW.replace(hour=0)
    first = run(git=git, gh=gh, stages=[stage_popularity_refresh.run], now=when)
    assert not first.aborted and first.publish["route"] == "auto"
    assert len([c for c in gh.calls if c[:2] == ("pr", "create")]) == 1
    assert not any(c[:2] == ("pr", "edit") for c in gh.calls)
    assert "popularity.github_repo_id" in path.read_text()

    second = run(git=git, gh=gh, stages=[stage_popularity_refresh.run], now=when)
    assert not second.aborted and second.publish is None
    assert len([c for c in gh.calls if c[:2] == ("pr", "create")]) == 1


def test_review_cap_still_allows_safe_auto_refresh_without_new_review_pr(wt_dir):
    _prepare(wt_dir)
    prs = [_review_pr(910 + i, 5) for i in range(10)]
    git, gh = _git(wt_dir, ORIGINAL), _gh(prs)
    result = run(git=git, gh=gh, stages=[stage_popularity_refresh.run], now=NOW.replace(hour=0), review_cap=10)
    assert not result.aborted and result.review_capped
    assert result.publish["route"] == "auto"
    assert len([c for c in gh.calls if c[:2] == ("pr", "create")]) == 1
    assert not any(c[:2] == ("pr", "edit") for c in gh.calls)


def test_unsafe_existing_citation_is_deferred_without_a_pr(wt_dir):
    old = ORIGINAL.replace("- field: popularity\n", "- field: popularity.stars\n"
                           "  url: https://unrelated.example/count\n  verified: '2026-09-01'\n- field: popularity\n")
    _prepare(wt_dir, old)
    git, gh = _git(wt_dir, old), _gh([])
    result = run(git=git, gh=gh, stages=[stage_popularity_refresh.run], now=NOW.replace(hour=0))
    assert not result.aborted and result.publish is None
    assert "1 provenance deferred" in result.stages[0]["summary"]
    assert not any(c[:2] == ("pr", "create") for c in gh.calls)
