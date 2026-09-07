"""Tests for scripts/g2_guard.py — against throwaway git repos (init, base commit, deletion
commit), never the real data/ tree."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

import g2_guard

FW = """\
---
id: {fid}
type: firmware
name: {name}
url: https://github.com/o/{fid}
category: multi
socs:
- esp32
{popularity}sources:
- field: '*'
  url: https://github.com/o/{fid}
  verified: '2026-09-01'
---

Body.
"""

POP = "popularity:\n  stars: {stars}\n  forks: {forks}\n  as_of: '2026-09-01'\n"


def _git(repo: Path, *args: str) -> None:
    p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, (args, p.stderr)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "t@t.t")
    _git(r, "config", "user.name", "t")
    (r / "data" / "firmware" / "victim").mkdir(parents=True)
    (r / "data" / "firmware" / "victim" / "firmware.md").write_text(
        FW.format(fid="victim", name="Victim", popularity=POP.format(stars=100, forks=5)))
    (r / "data" / "recipes" / "m5cardputer__victim").mkdir(parents=True)
    (r / "data" / "recipes" / "m5cardputer__victim" / "recipe.md").write_text("x\n")
    _git(r, "add", ".")
    _git(r, "commit", "-qm", "base")
    return r


def _base(repo: Path) -> str:
    p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True)
    return p.stdout.strip()


def _run(repo: Path, base: str) -> tuple[int, str]:
    import io
    from contextlib import redirect_stdout, redirect_stderr
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = g2_guard.main(["--base", base, "--repo", str(repo)])
    return rc, out.getvalue() + err.getvalue()


def test_floor_passing_deletion_fails_without_override(repo):
    base = _base(repo)
    (repo / "data" / "firmware" / "victim" / "firmware.md").unlink()
    _git(repo, "commit", "-qam", "delete victim")
    rc, out = _run(repo, base)
    assert rc == 1 and "victim" in out and "floor-passing" in out


def test_floor_passing_deletion_passes_with_override(repo):
    base = _base(repo)
    (repo / "data" / "firmware" / "victim" / "firmware.md").unlink()
    (repo / "jr" / "overrides").mkdir(parents=True)
    (repo / "jr" / "overrides" / "victim.json").write_text('{"why": "human said so"}\n')
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "delete victim with override")
    rc, out = _run(repo, base)
    assert rc == 0, out


def test_curated_exempt_deletion_fails(repo):
    base = _base(repo)
    (repo / "data" / "firmware" / "bruce").mkdir(parents=True)
    (repo / "data" / "firmware" / "bruce" / "firmware.md").write_text(
        FW.format(fid="bruce", name="Bruce", popularity=POP.format(stars=1, forks=0)))
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "seed bruce")
    base2 = _base(repo)
    (repo / "data" / "firmware" / "bruce" / "firmware.md").unlink()
    _git(repo, "commit", "-qam", "delete bruce")
    rc, out = _run(repo, base2)
    assert rc == 1 and "curated-exempt" in out


def test_below_floor_deletion_passes(repo):
    base = _base(repo)
    (repo / "data" / "firmware" / "victim" / "firmware.md").write_text(
        FW.format(fid="victim", name="Victim", popularity=POP.format(stars=3, forks=4)))
    _git(repo, "commit", "-qam", "sink victim below floor")
    base2 = _base(repo)
    (repo / "data" / "firmware" / "victim" / "firmware.md").unlink()
    (repo / "data" / "recipes" / "m5cardputer__victim" / "recipe.md").unlink()
    _git(repo, "commit", "-qam", "delete victim and its recipe")
    rc, out = _run(repo, base2)
    assert rc == 0, out   # below-floor firmware is deletable — but only with its recipe gone too


def test_recipe_deletion_with_firmware_intact_fails(repo):
    base = _base(repo)
    (repo / "data" / "recipes" / "m5cardputer__victim" / "recipe.md").unlink()
    _git(repo, "commit", "-qam", "delete only the recipe")
    rc, out = _run(repo, base)
    assert rc == 1 and "m5cardputer__victim" in out


def test_recipe_deletion_with_overridden_firmware_passes(repo):
    base = _base(repo)
    (repo / "data" / "firmware" / "victim" / "firmware.md").unlink()
    (repo / "data" / "recipes" / "m5cardputer__victim" / "recipe.md").unlink()
    (repo / "jr" / "overrides").mkdir(parents=True)
    (repo / "jr" / "overrides" / "victim.json").write_text('{"why": "human said so"}\n')
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "delete victim and recipe with override")
    rc, out = _run(repo, base)
    assert rc == 0, out


def test_path_helpers():
    assert g2_guard.firmware_id_of("data/firmware/bruce/firmware.md") == "bruce"
    assert g2_guard.firmware_id_of("data/recipes/m5cardputer__bruce/recipe.md") is None
    assert g2_guard.firmware_id_of("jr/overrides/bruce.json") is None
    assert g2_guard.recipe_firmware_id("data/recipes/m5cardputer__bruce/recipe.md") == "bruce"
    assert g2_guard.recipe_firmware_id("data/firmware/bruce/firmware.md") is None
    assert g2_guard.deleted_paths("D\tdata/firmware/x/firmware.md\nM\tother\n") == ["data/firmware/x/firmware.md"]
