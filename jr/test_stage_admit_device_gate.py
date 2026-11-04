"""Track A admission (launcher + submissions) behind the device-build evidence gate
(jr/device_evidence.py, review finding 3). Fake network only: repo trees, releases and raw build
files are served by the fake gh / raw below."""
from __future__ import annotations

from datetime import timedelta

import pytest

import device_evidence
import memory
import stage_admit
import tools
from test_device_evidence import ESP_SKETCH_YAML, IDF_CMAKE, WARBLE_TREE, esp_image
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
    "esp_idf": ({"tree": _tree("CMakeLists.txt", "main/CMakeLists.txt", "main/app.c", "sdkconfig.defaults")},
                {"z/zapkit/CMakeLists.txt": IDF_CMAKE, "z/zapkit/sdkconfig.defaults": "CONFIG_IDF_TARGET=\"esp32s3\"\n"}),
    "arduino": ({"tree": _tree("README.md", "zapkit/zapkit.ino", "zapkit/sketch.yaml")}, {"z/zapkit/zapkit/sketch.yaml": ESP_SKETCH_YAML}),
    "release_bin": ({"tree": _tree("README.md"),
                     "releases": [{"tag_name": "v1", "draft": False,
                                   "assets": [{"name": "zapkit-cardputer.bin", "browser_download_url": "https://x/tool.bin"}]}]}, {}),
}


@pytest.mark.parametrize("shape", sorted(EVIDENCE_SHAPES))
def test_repo_with_a_device_build_signal_is_admitted(root, monkeypatch, shape):
    api_docs, files = EVIDENCE_SHAPES[shape]
    monkeypatch.setattr(device_evidence, "default_head", lambda url, n: esp_image(9)[:n] if url == "https://x/tool.bin" else None)
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


def test_unreadable_submission_is_deferred_open_never_answered_or_remembered(root, monkeypatch):
    """Submissions are read from OPEN issues only: closing one on an outage would lose it."""
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    issues = [_issue(11, "### Repository URL\n\nhttps://github.com/z/zapkit\n\n### Boards\n\nM5Stack Cardputer\n")]
    metas = {"repos/z/zapkit": _meta("z/zapkit", stars=40, description="A Cardputer tool", rid=23),
             TREE.format("z/zapkit"): {"__status__": "HTTP 502"}, RELEASES.format("z/zapkit"): {"__status__": "HTTP 502"}}

    def boom(url):
        raise RuntimeError("HTTP 503")
    ctx = _ctx_sub(root, issues, metas)
    res = stage_admit.run(ctx, budget=3, raw=boom)
    assert res.admitted == 0 and "submission #11: deferred, build evidence unreadable" in res.summary
    assert _answers(ctx) == []
    assert not (root / "jr" / "proposed_ledger.json").exists() or \
        "zapkit" not in memory.load(root / "jr" / "proposed_ledger.json")["by_id"]


# --- needs_review: an ambiguous repo is never admitted and never guessed --------------------------

def _bare_sketch_metas():
    return {"repos/z/zapkit": _meta("z/zapkit", stars=40, description="A Cardputer tool", rid=24),
            TREE.format("z/zapkit"): _tree("README.md", "zapkit/zapkit.ino"), RELEASES.format("z/zapkit"): []}


BARE_SKETCH_REVIEW = {"id": "zapkit", "repo": "z/zapkit", "kind": "arduino_sketch",
                      "url": "https://github.com/z/zapkit/blob/main/zapkit/zapkit.ino"}


def test_bare_sketch_is_not_admitted_and_is_listed_for_the_owner(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Zapkit", "https://github.com/z/zapkit")])
    res = stage_admit.run(_ctx(root, metas=_bare_sketch_metas()), budget=3, raw=_raw({}))
    assert res.admitted == 0 and res.paths == [] and res.rejects == {"needs_review_target": 1}
    assert not (root / "data" / "firmware" / "zapkit").exists()
    [item] = res.review
    assert {k: item[k] for k in BARE_SKETCH_REVIEW} == BARE_SKETCH_REVIEW and "no ESP board named" in item["why"]
    assert "needs owner review: z/zapkit (arduino_sketch)" in res.summary
    rec = memory.load(root / "jr" / "proposed_ledger.json")["by_id"]["zapkit"]
    assert rec["status"] == "rejected" and rec["reason"].startswith("needs_review_target:")
    assert rec["expires"].startswith((NOW + timedelta(days=memory.NO_BUILD_SIGNAL_DAYS)).strftime("%Y-%m-%d"))


def test_dry_run_lists_a_needs_review_repo_and_remembers_nothing(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Zapkit", "https://github.com/z/zapkit")])
    res = stage_admit.run(_ctx(root, metas=_bare_sketch_metas(), dry_run=True), budget=3, raw=_raw({}))
    assert "would admit" not in res.summary and res.rejects == {"needs_review_target": 1}
    assert [r["repo"] for r in res.review] == ["z/zapkit"]
    assert not (root / "jr" / "proposed_ledger.json").exists()


def test_needs_review_submission_is_answered_with_how_to_state_the_target(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [])
    issues = [_issue(14, "### Repository URL\n\nhttps://github.com/z/zapkit\n\n### Boards\n\nM5Stack Cardputer\n")]
    ctx = _ctx_sub(root, issues, _bare_sketch_metas())
    res = stage_admit.run(ctx, budget=3, raw=_raw({}))
    assert res.admitted == 0 and res.rejects == {"needs_review_target": 1}
    assert "zapkit: skip needs_review_target (submission #14)" in res.summary
    assert [r["repo"] for r in res.review] == ["z/zapkit"]
    answer = _answers(ctx)[0][2]
    assert "**Not admitted** — `needs_review_target" in answer
    assert "owner reviews it" in answer and "sketch.yaml" in answer and "CONFIG_IDF_TARGET" in answer


def test_the_ranged_get_of_a_release_bin_is_charged_to_the_tick_budget(root, monkeypatch):
    heads = []
    monkeypatch.setattr(device_evidence, "default_head", lambda url, n: heads.append((url, n)) or esp_image(9)[:n])
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [_entry("Zapkit", "https://github.com/z/zapkit")])
    api_docs, files = EVIDENCE_SHAPES["release_bin"]
    metas = {"repos/z/zapkit": _meta("z/zapkit", stars=40, description="A Cardputer tool", rid=25),
             TREE.format("z/zapkit"): api_docs["tree"], RELEASES.format("z/zapkit"): api_docs["releases"]}
    ctx = _ctx(root, metas=metas)
    charged = []
    real_charge = ctx.budget.charge
    monkeypatch.setattr(ctx.budget, "charge", lambda n=1, what="gh": charged.append(what) or real_charge(n, what))
    res = stage_admit.run(ctx, budget=3, raw=_raw(files))
    assert res.admitted == 1 and heads == [("https://x/tool.bin", 16)]
    assert charged.count("raw") == 1          # the tree has no build files: the one raw charge is the ranged GET
