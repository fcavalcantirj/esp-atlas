"""Regression for the owner-directed removal of the falsely catalogued `warble` record.

rebelthor/warble is a host-side voice backend (whisper.cpp, Silero VAD, Ollama, Piper in Docker
images) that a stock xiaozhi-esp32 device on the M5Stack StackChan talks to; it is not ESP
firmware (upstream README: https://github.com/rebelthor/warble#readme). The fixture below is
modelled on its real shape — the paths its signals.json resolved: Dockerfiles and a
publish-images workflow, no platformio.ini / ESP-IDF project / sketch, no release .bin. Fake
network only; every stage run writes into a tmp_path root, never the repo's data dirs."""
from __future__ import annotations

import json
import shutil
from types import SimpleNamespace

import device_evidence as dev
import drain
import memory
import source_topics
import stage_admit_topics
from test_device_evidence import check
from test_stage_admit_topics import REPO, _ctx, _fake_fetch_meta, _meta, _topic_entry, root  # noqa: F401 — root is a fixture
import tools

UPSTREAM_README = "https://github.com/rebelthor/warble#readme"
HOST_BACKEND_TREE = ["README.md", "LICENSE", "docker-compose.yml", ".github/workflows/publish-images.yml",
                     "docker/whisper.Dockerfile", "server/Dockerfile", "server/go.mod", "server/main.go",
                     "vad-shim/Dockerfile", "vad-shim/app.py", "piper-shim/Dockerfile", "piper-shim/app.py"]
HOST_README = ("# warble\n\nFully local AI voice backend for the M5Stack StackChan robot (whisper.cpp + "
               "Silero VAD + Ollama + Piper). Runs on your own Linux or macOS machine; the CoreS3 keeps "
               "running stock xiaozhi-esp32 and connects to it.\n\n    docker compose up -d\n")
SOURCE_ONLY_RELEASE = [{"tag_name": "v0.1.0", "draft": False, "assets": []}]
WARBLE = _topic_entry("warble", "https://github.com/rebelthor/warble",
                      "Fully local AI voice backend for the M5Stack StackChan robot")


def _warble_meta():
    """Above the popularity floor and naming a catalogued board (the CoreS3, in the README body):
    every gate but the device-build evidence one passes, as it did for the real record."""
    return {**_meta("rebelthor/warble", stars=35, forks=5, rid=1408, description=WARBLE["description"]),
            "language": "Go", "readme_title": "warble", "readme_body": HOST_README}


def _gh(docs):
    calls = []

    def gh(*a):
        calls.append(a)
        doc = docs.get(a[1]) if len(a) > 1 else None
        if doc is None:
            return SimpleNamespace(returncode=1, stdout="", stderr="gh: Not Found (HTTP 404)")
        return SimpleNamespace(returncode=0, stdout=json.dumps(doc), stderr="")
    gh.calls = calls
    return gh


def _topics_stage(monkeypatch):
    monkeypatch.setattr(tools, "run_guard", lambda: {"ok": True, "output": ""})
    monkeypatch.setattr(source_topics, "fetch_topic_repos", lambda topics, search=None: [WARBLE])
    monkeypatch.setattr(drain, "default_fetch_meta", _fake_fetch_meta({"rebelthor/warble": _warble_meta()}))
    return _gh({"repos/rebelthor/warble/git/trees/main?recursive=1":
                {"tree": [{"path": p, "type": "blob"} for p in HOST_BACKEND_TREE]},
                "repos/rebelthor/warble/releases?per_page=10": SOURCE_ONLY_RELEASE})


def _raw(url):
    return HOST_README if url.endswith("/README.md") else None


def _assert_nothing_authored(root):
    assert not (root / "data" / "firmware" / "warble").exists()
    assert not list((root / "data" / "recipes").glob("*__warble"))


def test_the_gate_classifies_the_upstream_shaped_host_backend_as_not_device_firmware():
    res, _ = check("rebelthor/warble", tree=HOST_BACKEND_TREE, files={"README.md": HOST_README},
                   releases=SOURCE_ONLY_RELEASE)
    assert res["ok"] is False and res["verdict"] == dev.NOT_DEVICE_FIRMWARE and res["kind"] is None


def test_topics_stage_does_not_admit_the_upstream_shaped_host_backend(root, monkeypatch):
    gh = _topics_stage(monkeypatch)
    res = stage_admit_topics.run(_ctx(root, gh=gh), budget=2, raw=_raw)
    assert res.admitted == 0 and res.paths == []
    assert res.rejects == {"not_device_firmware": 1}
    _assert_nothing_authored(root)


def test_the_repo_ledger_keeps_warble_as_a_permanent_owner_rejection():
    """Append-only: the record stays, flipped from merged to a PERMANENT rejection (no expires) —
    the only change scripts/ledger_guard.py allows a merged record — with a sourced reason."""
    led = memory.load(REPO / "jr" / "proposed_ledger.json")
    rec = led["by_id"]["warble"]
    assert memory.is_permanent_rejection(rec), rec
    assert rec["repo"] == "rebelthor/warble" and led["by_repo"]["rebelthor/warble"] == "warble"
    assert UPSTREAM_README in rec["reason"] and "not ESP firmware" in rec["reason"]


def test_the_owner_rejection_blocks_readmission_before_any_evidence_read(root, monkeypatch):
    shutil.copy(REPO / "jr" / "proposed_ledger.json", root / "jr" / "proposed_ledger.json")
    before = memory.load(root / "jr" / "proposed_ledger.json")["by_id"]["warble"]
    gh = _topics_stage(monkeypatch)
    res = stage_admit_topics.run(_ctx(root, gh=gh), budget=2, raw=_raw)
    assert res.admitted == 0 and res.paths == []
    assert not any("rebelthor/warble/git/trees" in " ".join(map(str, c)) for c in gh.calls)
    assert memory.load(root / "jr" / "proposed_ledger.json")["by_id"]["warble"] == before
    _assert_nothing_authored(root)


def test_the_catalog_drops_warble_under_a_sourced_g2_override():
    assert not (REPO / "data" / "firmware" / "warble").exists()
    assert not list((REPO / "data" / "recipes").glob("*__warble"))
    override = json.loads((REPO / "jr" / "overrides" / "warble.json").read_text())
    assert override["id"] == "warble" and override["repo"] == "rebelthor/warble"
    assert override["source"] == UPSTREAM_README and "repository owner" in override["why"]
