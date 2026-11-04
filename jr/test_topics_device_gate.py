"""The topics / launcher-drain path (jr/drain.score_candidates -> jr/stage_admit_topics) behind the
device-build evidence gate (jr/device_evidence.py, review finding 3). Fake network only."""
from __future__ import annotations

import json
from datetime import timedelta
from types import SimpleNamespace

import pytest

import device_evidence as dev
import drain
import memory
import source_topics
import stage_admit_topics
from test_device_evidence import IDF_CMAKE, WARBLE_TREE, fake_repo
from test_stage_admit_topics import NOW, _ctx, _fake_fetch_meta, _meta, _topic_entry, root  # noqa: F401 — root is a fixture
import tools

WARBLE = _topic_entry("Warble", "https://github.com/rebelthor/warble",
                      "Self-hosted voice server for the M5Stack Cardputer and StackChan")


def _warble_meta():
    return {**_meta("rebelthor/warble", stars=35, forks=4, rid=1408, description=WARBLE["description"]),
            "language": "Go"}


def _evidence(**shape):
    """An evidence(owner_repo, ref) callable running the REAL check over one fake repo shape."""
    api, raw, _ = fake_repo(owner_repo=shape.pop("owner_repo"), ref="main", **shape)
    return lambda owner_repo, ref: dev.check(owner_repo, api=api, raw=raw, ref=ref)


def test_score_candidates_rejects_a_warble_shaped_repo_not_device_firmware():
    seen = []
    ev = _evidence(owner_repo="rebelthor/warble", tree=WARBLE_TREE, releases=[])
    scored, skipped = drain.score_candidates([WARBLE], set(), set(), fetch_meta=lambda url: _warble_meta(),
                                             evidence=lambda o, r: seen.append((o, r)) or ev(o, r))
    assert scored == []
    assert seen == [("rebelthor/warble", "main")]
    [s] = skipped
    assert s["reason"].startswith("not_device_firmware:")
    assert s["firmware_id"] == "warble" and s["repo"] == "rebelthor/warble"


SHAPES = {
    "platformio": {"tree": ["platformio.ini"], "files": {"platformio.ini": "[env:c]\nplatform = espressif32\nboard = m5stack-stamps3\n"}},
    "esp_idf": {"tree": ["CMakeLists.txt", "main/app.c"], "files": {"CMakeLists.txt": IDF_CMAKE}},
    "arduino": {"tree": ["zap/zap.ino"]},
    "release_bin": {"tree": ["README.md"], "releases": [{"draft": False, "assets": [{"name": "zap.bin", "browser_download_url": "u"}]}]},
}


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_score_candidates_passes_a_repo_with_a_device_build_signal(shape):
    entry = _topic_entry("Zap Cardputer", "https://github.com/z/zap", "A Cardputer tool")
    meta = _meta("z/zap", stars=40, description="A Cardputer tool", rid=5)
    scored, skipped = drain.score_candidates([entry], set(), set(), fetch_meta=lambda url: meta,
                                             evidence=_evidence(owner_repo="z/zap", **SHAPES[shape]))
    assert skipped == [] and [s["record"]["id"] for s in scored] == ["zap"]


def test_the_gate_is_on_by_default(monkeypatch):
    """No evidence callable passed: the module default (live in production) still gates."""
    monkeypatch.setattr(drain, "default_device_evidence", lambda o, r: {"ok": False, "notes": []})
    scored, skipped = drain.score_candidates([WARBLE], set(), set(), fetch_meta=lambda url: _warble_meta())
    assert scored == [] and skipped[0]["reason"].startswith("not_device_firmware:")


def test_below_floor_is_decided_before_spending_evidence_calls():
    calls = []
    meta = {**_warble_meta(), "stars": 3, "forks": 0}
    _, skipped = drain.score_candidates([WARBLE], set(), set(), fetch_meta=lambda url: meta,
                                        evidence=lambda o, r: calls.append(o))
    assert calls == [] and skipped[0]["reason"] == "below-popularity-floor"


# --- the hourly topics stage ---------------------------------------------------------------------

def _gh(api_docs):
    """ctx.gh over {path: doc}; a missing path is a 404, like `gh api`."""
    calls = []

    def gh(*a):
        calls.append(a)
        doc = api_docs.get(a[1]) if len(a) > 1 else None
        if doc is None:
            return SimpleNamespace(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)")
        return SimpleNamespace(returncode=0, stdout=json.dumps(doc), stderr="")
    gh.calls = calls
    return gh


@pytest.fixture
def _no_real_guard(monkeypatch):
    monkeypatch.setattr(tools, "run_guard", lambda: {"ok": True, "output": ""})


def _warble_stage(monkeypatch):
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: [WARBLE])
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta({"rebelthor/warble": _warble_meta()}))
    return _gh({"repos/rebelthor/warble/git/trees/main?recursive=1":
                {"tree": [{"path": p, "type": "blob"} for p in WARBLE_TREE]},
                "repos/rebelthor/warble/releases?per_page=10": []})


def test_topics_stage_rejects_warble_and_remembers_it_with_the_no_build_signal_ttl(root, monkeypatch, _no_real_guard):
    gh = _warble_stage(monkeypatch)
    ctx = _ctx(root, gh=gh)
    res = stage_admit_topics.run(ctx, budget=2, raw=lambda url: None)
    assert res.admitted == 0 and res.paths == []
    assert res.rejects == {"not_device_firmware": 1}
    assert not (root / "data" / "firmware" / "warble").exists()
    rec = memory.load(root / "jr" / "proposed_ledger.json")["by_id"]["warble"]
    assert rec["status"] == "rejected" and rec["reason"].startswith("not_device_firmware:")
    assert rec["expires"].startswith((NOW + timedelta(days=memory.NO_BUILD_SIGNAL_DAYS)).strftime("%Y-%m-%d"))
    # the evidence reads went through the tick's counted gh
    assert ("api", "repos/rebelthor/warble/git/trees/main?recursive=1") in gh.calls
    assert ctx.budget.calls >= 2


def test_topics_stage_dry_run_never_claims_warble_would_admit(root, monkeypatch, _no_real_guard):
    gh = _warble_stage(monkeypatch)
    res = stage_admit_topics.run(_ctx(root, gh=gh, dry_run=True), budget=2, raw=lambda url: None)
    assert "would admit" not in res.summary and res.rejects.get("not_device_firmware") == 1
    assert not (root / "jr" / "proposed_ledger.json").exists()
