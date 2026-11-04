"""Track A admission (launcher + submissions) behind the device-build evidence gate
(jr/device_evidence.py, review finding 3). Fake network only: repo trees, releases and raw build
files are served by the fake gh / raw below."""
from __future__ import annotations

from datetime import timedelta

import pytest

import memory
import stage_admit
import tools
from test_device_evidence import IDF_CMAKE, WARBLE_TREE
from test_stage_admit import NOW, _answers, _ctx, _ctx_sub, _entry, _issue, _meta, root  # noqa: F401 — root is a fixture

TREE = "repos/{}/git/trees/main?recursive=1"
RELEASES = "repos/{}/releases?per_page=10"


def _tree(*paths):
    return {"tree": [{"path": p, "type": "blob"} for p in paths], "truncated": False}


def _raw(files: dict):
    """raw(url) over {owner/repo/path: text}; everything else 404 (None). Never the network."""
    def raw(url):
        return files.get(url.replace("https://raw.githubusercontent.com/", "").replace("/main/", "/", 1))
    return raw


def _warble_meta():
    return _meta("rebelthor/warble", stars=35, forks=4, rid=1408,
                 description="Self-hosted voice server for the M5Stack Cardputer and StackChan")


def test_warble_shaped_go_server_is_rejected_not_device_firmware(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Warble", "https://github.com/rebelthor/warble")])
    metas = {"repos/rebelthor/warble": {**_warble_meta(), "language": "Go"},
             TREE.format("rebelthor/warble"): _tree(*WARBLE_TREE),
             RELEASES.format("rebelthor/warble"): []}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3, raw=_raw({}))
    assert res.admitted == 0 and res.paths == []
    assert res.rejects == {"not_device_firmware": 1}
    assert "not_device_firmware 1" in res.summary
    assert not (root / "data" / "firmware" / "warble").exists()
    assert not list((root / "data" / "recipes").glob("*__warble"))
    rec = memory.load(root / "jr" / "proposed_ledger.json")["by_id"]["warble"]
    assert rec["status"] == "rejected" and rec["reason"].startswith("not_device_firmware:")
    assert rec["repo_id"] == 1408
    assert rec["expires"].startswith((NOW + timedelta(days=memory.NO_BUILD_SIGNAL_DAYS)).strftime("%Y-%m-%d"))


EVIDENCE_SHAPES = {
    "platformio": ({"tree": _tree("platformio.ini", "src/main.cpp")},
                   {"z/zapkit/platformio.ini": "[env:cardputer]\nplatform = espressif32\nboard = m5stack-stamps3\n"}),
    "esp_idf": ({"tree": _tree("CMakeLists.txt", "main/CMakeLists.txt", "main/app.c")},
                {"z/zapkit/CMakeLists.txt": IDF_CMAKE}),
    "arduino": ({"tree": _tree("README.md", "zapkit/zapkit.ino")}, {}),
    "release_bin": ({"tree": _tree("README.md"),
                     "releases": [{"tag_name": "v1", "draft": False,
                                   "assets": [{"name": "zapkit-cardputer.bin", "browser_download_url": "https://x/tool.bin"}]}]}, {}),
}


@pytest.mark.parametrize("shape", sorted(EVIDENCE_SHAPES))
def test_repo_with_a_device_build_signal_is_admitted(root, monkeypatch, shape):
    api_docs, files = EVIDENCE_SHAPES[shape]
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Zapkit", "https://github.com/z/zapkit")])
    metas = {"repos/z/zapkit": _meta("z/zapkit", stars=40, description="A Cardputer tool", rid=21),
             TREE.format("z/zapkit"): api_docs["tree"],
             RELEASES.format("z/zapkit"): api_docs.get("releases", [])}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3, raw=_raw(files))
    assert res.admitted == 1 and res.rejects == {}, res.summary
    assert (root / "data" / "firmware" / "zapkit" / "firmware.md").exists()


def test_unreadable_evidence_is_retried_soon_never_written(root, monkeypatch):
    """Tree and releases both 5xx: not a fact about the repo — skipped with the 7-day TTL."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Zapkit", "https://github.com/z/zapkit")])

    def boom(url):
        raise RuntimeError("HTTP 503")
    metas = {"repos/z/zapkit": _meta("z/zapkit", stars=40, description="A Cardputer tool", rid=22),
             TREE.format("z/zapkit"): {"__status__": "HTTP 502"}, RELEASES.format("z/zapkit"): {"__status__": "HTTP 502"}}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3, raw=boom)
    assert res.admitted == 0 and res.rejects == {"device_evidence_unreadable": 1}
    rec = memory.load(root / "jr" / "proposed_ledger.json")["by_id"]["zapkit"]
    assert rec["expires"].startswith((NOW + timedelta(days=memory.UNRESOLVED_REJECT_DAYS)).strftime("%Y-%m-%d"))


def test_dry_run_does_not_claim_a_warble_shaped_repo_would_admit(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Warble", "https://github.com/rebelthor/warble")])
    metas = {"repos/rebelthor/warble": _warble_meta(), TREE.format("rebelthor/warble"): _tree(*WARBLE_TREE),
             RELEASES.format("rebelthor/warble"): []}
    res = stage_admit.run(_ctx(root, metas=metas, dry_run=True), budget=3, raw=_raw({}))
    assert "would admit" not in res.summary and res.rejects == {"not_device_firmware": 1}
    assert not (root / "jr" / "proposed_ledger.json").exists()


def test_warble_shaped_submission_is_answered_not_device_firmware(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    issues = [_issue(9, "### Repository URL\n\nhttps://github.com/rebelthor/warble\n\n### Boards\n\nM5Stack Cardputer\n")]
    metas = {"repos/rebelthor/warble": _warble_meta(), TREE.format("rebelthor/warble"): _tree(*WARBLE_TREE),
             RELEASES.format("rebelthor/warble"): []}
    ctx = _ctx_sub(root, issues, metas)
    res = stage_admit.run(ctx, budget=3, raw=_raw({}))
    assert res.admitted == 0 and res.rejects == {"not_device_firmware": 1}
    assert "warble: skip not_device_firmware (submission #9)" in res.summary
    answer = _answers(ctx)[0][2]
    assert "**Not admitted** — `not_device_firmware" in answer and "platformio.ini" in answer
