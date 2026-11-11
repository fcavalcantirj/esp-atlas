"""Tests for Jr retracting its own wrong recipes (SPEC-firmware-board-mapping.md section 4.1). The tmp
root carries a COPY of the real boards, so nothing real is written. The last test runs the whole path
through real git, the routing classifier, publish and the G2 guard."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import memory
import publish
import review_routing as rr
import stage_boardmap as sb
from review_routing import Change

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import g2_guard  # noqa: E402

SHA = "7755e3e63bec8f1280452e7d812a5cd08aafe0c0"
FW = """---
id: demo
type: firmware
name: "Demo"
url: https://github.com/o/demo
category: tools
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/o/demo
  verified: '2026-11-01'
---

Body.
"""
PRODUCT_INI = """[env:cardputer_release]
board = m5stack-stamps3
build_flags =
  -DTARGET_CARDPUTER=1
"""


def recipe(board="m5stamp-s3", env="cardputer_release", status="unverified"):
    return f"""---
id: {board}__demo
type: recipe
board: {board}
firmware: demo
status: {status}
chip_family: esp32-s3
flash:
  env: "{env}"
sources:
- field: '*'
  url: https://github.com/o/demo
  verified: '2026-11-01'
---

# {board} x demo
"""


def api(path):
    if path == "repos/o/demo":
        return {"default_branch": "main"}
    if path.startswith("repos/o/demo/git/trees/"):
        return {"tree": [{"path": "platformio.ini", "type": "blob"}], "truncated": False}
    raise RuntimeError("404 " + path)


def raw_of(ini):
    return lambda url: ini if url.endswith("/platformio.ini") else None


def put(root, rid_board, text):
    d = root / "data" / "recipes" / f"{rid_board}__demo"
    d.mkdir(parents=True)
    (d / "recipe.md").write_text(text)


@pytest.fixture
def root(tmp_path):
    shutil.copytree(REPO / "data" / "boards", tmp_path / "data" / "boards")
    shutil.copytree(REPO / "data" / "modules", tmp_path / "data" / "modules")
    (tmp_path / "data" / "firmware" / "demo").mkdir(parents=True)
    (tmp_path / "data" / "firmware" / "demo" / "firmware.md").write_text(FW)
    (tmp_path / "data" / "recipes").mkdir()
    put(tmp_path, "m5stamp-s3", recipe())
    put(tmp_path, "m5cardputer", recipe("m5cardputer", "cardputer"))
    return tmp_path


def run(root, ini=PRODUCT_INI, **kw):
    kw.setdefault("retract_limit", 3)
    kw.setdefault("head", lambda: SHA)
    return sb.map_one("demo", root=root, api=api, raw=raw_of(ini), today="2026-11-11", **kw)


def test_a_product_build_on_the_bare_module_is_retracted_with_an_audited_override(root):
    original = (root / "data/recipes/m5stamp-s3__demo/recipe.md").read_text()
    r = run(root)
    assert not (root / "data/recipes/m5stamp-s3__demo").exists()
    assert (root / "data/recipes/m5cardputer__demo/recipe.md").exists()
    assert r["retracted"] == ["m5stamp-s3__demo"]
    assert {"data/recipes/m5stamp-s3__demo/recipe.md", "jr/overrides/demo__edges.json"} <= set(r["paths"])
    rec = json.loads((root / "jr/overrides/demo__edges.json").read_text())
    assert rec["firmware"] == "demo" and rec["action"] == "edge_correction"
    assert rec["directed_by"] == rr.SELF_CORRECTION_AUTHOR
    assert rec["classification"] == "module_board_id_under_product_build"
    assert rec["deletes"] == ["data/recipes/m5stamp-s3__demo/recipe.md"]
    assert rec["originals"] == {"data/recipes/m5stamp-s3__demo/recipe.md": original}
    assert rec["historical_parent_sha"] == SHA and rec["date"] == "2026-11-11"
    assert all(u.startswith("https://") for u in rec["sources"]) and "cardputer_release" in rec["why"]


def test_it_does_not_come_back_on_the_next_read(root):
    run(root)
    (root / "jr/overrides/demo__edges.json").unlink()
    r = run(root)
    assert r["retracted"] == [] and r["written"] == []
    assert not (root / "data/recipes/m5stamp-s3__demo").exists()


@pytest.mark.parametrize("status", ["declared", "tested", "verified"])
def test_a_recipe_anyone_confirmed_is_never_touched(root, status):
    (root / "data/recipes/m5stamp-s3__demo/recipe.md").write_text(recipe(status=status))
    assert run(root)["retracted"] == []
    assert (root / "data/recipes/m5stamp-s3__demo/recipe.md").exists()


def test_a_different_env_is_not_evidence_against_this_recipe(root):
    (root / "data/recipes/m5stamp-s3__demo/recipe.md").write_text(recipe(env="some-other-env"))
    assert run(root)["retracted"] == []


def test_a_surviving_module_signal_keeps_the_recipe(root):
    ini = PRODUCT_INI + "\n[env:m5stack-stamps3]\nboard = m5stack-stamps3\n"
    assert run(root, ini=ini)["retracted"] == []
    assert (root / "data/recipes/m5stamp-s3__demo/recipe.md").exists()


def test_missing_evidence_retracts_nothing(root):
    assert run(root, ini="[platformio]\n")["retracted"] == []
    assert (root / "data/recipes/m5stamp-s3__demo/recipe.md").exists()


def test_a_degraded_read_retracts_nothing(root, monkeypatch):
    real = sb.derive.derive
    monkeypatch.setattr(sb.derive, "derive", lambda *a, **k: {**real(*a, **k), "errors": 1})
    assert run(root)["retracted"] == []
    assert (root / "data/recipes/m5stamp-s3__demo/recipe.md").exists()


def test_a_firmware_is_never_orphaned(root):
    shutil.rmtree(root / "data/recipes/m5cardputer__demo")
    r = run(root)
    assert r["retracted"] == [] and any("orphan" in n for n in r["notes"])
    assert (root / "data/recipes/m5stamp-s3__demo/recipe.md").exists()


def test_an_earlier_override_defers_to_a_person(root):
    (root / "jr/overrides").mkdir(parents=True)
    (root / "jr/overrides/demo__edges.json").write_text("{}")
    r = run(root)
    assert r["retracted"] == [] and any("override" in n for n in r["notes"])


@pytest.mark.parametrize("kw", [{"retract_limit": 0}, {"head": lambda: None}, {"head": lambda: "not-a-sha"}])
def test_no_budget_or_no_base_commit_retracts_nothing(root, kw):
    assert run(root, **kw)["retracted"] == []
    assert (root / "data/recipes/m5stamp-s3__demo/recipe.md").exists()


def test_a_dry_run_reports_and_writes_nothing(root):
    r = run(root, dry_run=True)
    assert r["would_retract"] == ["m5stamp-s3__demo"]
    assert (root / "data/recipes/m5stamp-s3__demo/recipe.md").exists()
    assert not (root / "jr/overrides").exists()


# --- routing ---------------------------------------------------------------------------------------

P = "data/recipes/m5stamp-s3__demo/recipe.md"
O = "jr/overrides/demo__edges.json"


def override(**kw):
    rec = {"firmware": "demo", "action": "edge_correction", "directed_by": rr.SELF_CORRECTION_AUTHOR,
           "classification": "module_board_id_under_product_build", "deletes": [P], "originals": {P: "x"}}
    return json.dumps({**rec, **kw})


def test_an_exact_self_correction_is_auto():
    assert rr.classify([Change(P, "D"), Change(O, "A", None, override()), Change("jr/proposed_ledger.json", "M")]).route == rr.AUTO


@pytest.mark.parametrize("changes", [
    [Change(P, "D")],                                                                    # no override
    [Change(P, "D"), Change(O, "M", None, override())],                                  # edited, not added
    [Change(P, "D"), Change(O, "A", None, override(directed_by="owner"))],               # someone else's
    [Change(P, "D"), Change(O, "A", None, override(classification="anything"))],
    [Change(P, "D"), Change(O, "A", None, "{not json")],
    [Change(O, "A", None, override())],                                                  # lists a path not deleted
    [Change(P, "D"), Change("data/recipes/esp32-c3-devkitm-1__demo/recipe.md", "D"), Change(O, "A", None, override())],  # an extra deletion
    [Change(P, "D"), Change(O, "A", None, override()), Change("data/recipes/m5dial__demo/recipe.md", "A")],              # a new claim rides along
    [Change("data/firmware/demo/firmware.md", "D"), Change(O, "A", None, override(deletes=["data/firmware/demo/firmware.md"], originals={"data/firmware/demo/firmware.md": "x"}))],
])
def test_anything_else_stays_review(changes):
    assert rr.classify(changes).route == rr.REVIEW


def test_over_the_cap_stays_review():
    paths = [f"data/recipes/b{i}__demo/recipe.md" for i in range(rr.MAX_SELF_CORRECTIONS + 1)]
    changes = [Change(p, "D") for p in paths] + [Change(O, "A", None, override(deletes=paths, originals={p: "x" for p in paths}))]
    assert rr.classify(changes).route == rr.REVIEW


# --- the whole path, real git ----------------------------------------------------------------------

def test_the_real_path_git_routing_publish_and_g2_agree(root):
    def git(*a):
        return subprocess.run(["git", *a], capture_output=True, text=True)
    g = lambda *a: git("-C", str(root), *a)  # noqa: E731
    for bookkeeping in memory.staged_paths():      # publish always stages these
        (root / bookkeeping).parent.mkdir(parents=True, exist_ok=True)
        (root / bookkeeping).write_text("{}\n")
    assert g("init", "-q").returncode == 0
    g("config", "user.email", "t@t"), g("config", "user.name", "t")
    g("add", "-A"), g("commit", "-q", "-m", "base")
    base = g("rev-parse", "HEAD").stdout.strip()

    r = run(root, head=lambda: base)
    assert r["retracted"] == ["m5stamp-s3__demo"]
    wt = publish.Worktree(path=root, base_sha=base)
    assert g("add", "--", *r["paths"]).returncode == 0
    changes = publish._staged_changes(wt, git)
    assert rr.classify(changes).route == rr.AUTO

    deleted = {c.path for c in changes if c.status.startswith("D")}
    raw = (root / O).read_bytes()
    problems = g2_guard.edge_override_problems(
        O, raw, deleted,
        lambda p: subprocess.run(["git", "-C", str(root), "show", f"{base}:{p}"], capture_output=True).stdout,
        lambda p: (root / p).exists())
    assert problems == []

    g("reset", "-q")
    res = publish.publish(wt, r["paths"], "s", "b", git=git, gh=lambda *a: subprocess.CompletedProcess(a, 1, "", "no"))
    assert "deletion refused" not in (res.reason or "")
    assert res.commit or res.reason in ("push failed", "could not create branch")
