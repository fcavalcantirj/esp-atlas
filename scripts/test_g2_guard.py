"""Tests for scripts/g2_guard.py — against throwaway git repos (init, base commit, deletion
commit), never the real data/ tree."""
from __future__ import annotations

import json
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
POP_DL = "popularity:\n  stars: {stars}\n  forks: {forks}\n  downloads: {downloads}\n  as_of: '2026-09-01'\n"


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


def test_high_persisted_download_count_protects_from_deletion_without_override(repo):
    """M5Launcher class: 1 star, 0 forks — below both GitHub floors — but a persisted
    popularity.downloads>=2000 (the fourth floor signal) makes the record floor-passing, so
    deletion without an override is refused."""
    base = _base(repo)
    (repo / "data" / "firmware" / "victim" / "firmware.md").write_text(
        FW.format(fid="victim", name="Victim", popularity=POP_DL.format(stars=1, forks=0, downloads=2000)))
    _git(repo, "commit", "-qam", "stamp victim with a qualifying download count")
    base2 = _base(repo)
    (repo / "data" / "firmware" / "victim" / "firmware.md").unlink()
    _git(repo, "commit", "-qam", "delete victim")
    rc, out = _run(repo, base2)
    assert rc == 1 and "floor-passing" in out


def test_persisted_download_count_just_under_the_floor_with_zero_stars_stays_deletable(repo):
    base = _base(repo)
    (repo / "data" / "firmware" / "victim" / "firmware.md").write_text(
        FW.format(fid="victim", name="Victim", popularity=POP_DL.format(stars=0, forks=0, downloads=1999)))
    _git(repo, "commit", "-qam", "sink victim below every floor")
    base2 = _base(repo)
    (repo / "data" / "firmware" / "victim" / "firmware.md").unlink()
    (repo / "data" / "recipes" / "m5cardputer__victim" / "recipe.md").unlink()
    _git(repo, "commit", "-qam", "delete victim and its recipe")
    rc, out = _run(repo, base2)
    assert rc == 0, out


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


# --- edge-correction override (jr/overrides/<firmware>__edges.json) --------------------------
# A recipe deleted while its firmware stays passes ONLY when an edge-correction override that
# is added or modified in this very change lists that exact path, carries every audit field,
# and preserves the recipe's original text byte-for-byte as it was at BASE.

EDGE_BOARDS = ("m5stack-cores3", "lilygo-t-display-s3")


def _recipe_path(board: str, fid: str = "victim") -> str:
    return f"data/recipes/{board}__{fid}/recipe.md"


def _recipe_text(board: str) -> str:
    return f"---\nid: {board}__victim\nstatus: declared\n---\n\nFalse edge on {board}.\n"


def _seed_edges(repo: Path, boards=EDGE_BOARDS) -> str:
    """Commit extra victim recipes on top of the fixture; returns the new base sha."""
    for board in boards:
        p = repo / _recipe_path(board)
        p.parent.mkdir(parents=True)
        p.write_text(_recipe_text(board))
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "seed false edges")
    return _base(repo)


def _edge_override(paths, fid: str = "victim", **overrides) -> dict:
    record = {
        "firmware": fid,
        "action": "edge_correction",
        "deletes": list(paths),
        "classification": "vendored_study_tree_not_build_target",
        "sources": ["https://github.com/o/victim/blob/abc1234/reference/README.md",
                    "https://github.com/o/victim/commit/0ad6cd1657229c49a31880736f5de2efec130c13"],
        "historical_parent_sha": "b5e1b917ce0c9f036d21c209e2583f17758fd779",
        "directed_by": "repository owner",
        "date": "2026-11-05",
        "originals": {p: _recipe_text(p.split("/")[2].split("__")[0]) for p in paths},
    }
    record.update(overrides)
    return record


def _write_override(repo: Path, record, name: str = "victim__edges.json") -> None:
    d = repo / "jr" / "overrides"
    d.mkdir(parents=True, exist_ok=True)
    text = record if isinstance(record, str) else json.dumps(record, indent=2)
    (d / name).write_text(text)


def _delete(repo: Path, *paths: str) -> None:
    for p in paths:
        (repo / p).unlink()


def _commit_all(repo: Path, msg: str = "change") -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", msg)


def _edge_paths(boards=EDGE_BOARDS) -> list[str]:
    return [_recipe_path(b) for b in boards]


def test_edge_correction_with_firmware_kept_passes(repo):
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    _write_override(repo, _edge_override(paths))
    _commit_all(repo, "edge correction")
    rc, out = _run(repo, base)
    assert rc == 0, out


def test_edge_deletion_without_override_fails(repo):
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    _commit_all(repo, "strip edges, no override")
    rc, out = _run(repo, base)
    assert rc == 1
    assert all(p in out for p in paths), out


def test_stale_unchanged_override_authorizes_nothing(repo):
    paths = _edge_paths()
    _write_override(repo, _edge_override(paths))   # committed in the BASE, not in the change
    base = _seed_edges(repo)
    _delete(repo, *paths)
    _commit_all(repo, "reuse an old override")
    rc, out = _run(repo, base)
    assert rc == 1
    assert all(p in out for p in paths), out


def test_unlisted_extra_recipe_deletion_fails(repo):
    base = _seed_edges(repo)
    listed, extra = _edge_paths()
    _delete(repo, listed, extra)
    _write_override(repo, _edge_override([listed]))
    _commit_all(repo, "one listed, one smuggled")
    rc, out = _run(repo, base)
    assert rc == 1
    assert f"deleting recipe '{extra}'" in out
    assert f"deleting recipe '{listed}'" not in out, out


def test_listed_path_not_actually_deleted_fails(repo):
    base = _seed_edges(repo)
    deleted, kept = _edge_paths()
    _delete(repo, deleted)
    _write_override(repo, _edge_override([deleted, kept]))
    _commit_all(repo, "override lists a recipe that stays")
    rc, out = _run(repo, base)
    assert rc == 1 and kept in out, out


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda r: r.pop("sources"), id="missing-sources"),
    pytest.param(lambda r: r.update(sources=[]), id="empty-sources"),
    pytest.param(lambda r: r.update(sources="https://github.com/o/victim"), id="sources-not-a-list"),
    pytest.param(lambda r: r.update(sources=["http://github.com/o/victim"]), id="non-https-source"),
    pytest.param(lambda r: r.update(sources=["https://"]), id="hostless-source"),
    pytest.param(lambda r: r.pop("classification"), id="missing-classification"),
    pytest.param(lambda r: r.update(classification="  "), id="blank-classification"),
    pytest.param(lambda r: r.update(action="delete"), id="wrong-action"),
    pytest.param(lambda r: r.pop("action"), id="missing-action"),
    pytest.param(lambda r: r.pop("historical_parent_sha"), id="missing-parent-sha"),
    pytest.param(lambda r: r.update(historical_parent_sha="not-a-sha"), id="malformed-parent-sha"),
    pytest.param(lambda r: r.pop("directed_by"), id="missing-directed-by"),
    pytest.param(lambda r: r.pop("date"), id="missing-date"),
    pytest.param(lambda r: r.update(date="2026-13-45"), id="malformed-date"),
    pytest.param(lambda r: r.pop("deletes"), id="missing-deletes"),
    pytest.param(lambda r: r.update(deletes=[]), id="empty-deletes"),
    pytest.param(lambda r: r.pop("originals"), id="missing-originals"),
    pytest.param(lambda r: r["originals"].pop(next(iter(r["originals"]))), id="original-missing-for-a-path"),
    pytest.param(lambda r: r["originals"].update({"data/recipes/x__victim/recipe.md": "x"}),
                 id="original-for-unlisted-path"),
    pytest.param(lambda r: r.pop("firmware"), id="missing-firmware"),
])
def test_malformed_edge_override_fails(repo, mutate):
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    record = _edge_override(paths)
    mutate(record)
    _write_override(repo, record)
    _commit_all(repo, "malformed override")
    rc, out = _run(repo, base)
    assert rc == 1, out
    assert "victim__edges.json" in out, out


def test_edge_override_invalid_json_fails(repo):
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    _write_override(repo, '{"firmware": "victim", "deletes": [')
    _commit_all(repo, "broken json")
    rc, out = _run(repo, base)
    assert rc == 1 and "victim__edges.json" in out, out


def test_edge_override_not_an_object_fails(repo):
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    _write_override(repo, json.dumps([_edge_override(paths)]))
    _commit_all(repo, "json array")
    rc, out = _run(repo, base)
    assert rc == 1 and "victim__edges.json" in out, out


def test_malformed_edge_override_fails_even_without_deletions(repo):
    base = _base(repo)
    _write_override(repo, "{not json")
    _commit_all(repo, "broken override alone")
    rc, out = _run(repo, base)
    assert rc == 1 and "victim__edges.json" in out, out


def test_wrong_firmware_id_fails(repo):
    """The override names a different (existing) firmware than the recipes it deletes."""
    (repo / "data" / "firmware" / "other").mkdir(parents=True)
    (repo / "data" / "firmware" / "other" / "firmware.md").write_text(
        FW.format(fid="other", name="Other", popularity=""))
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    _write_override(repo, _edge_override(paths, fid="other"), name="other__edges.json")
    _commit_all(repo, "override for the wrong firmware")
    rc, out = _run(repo, base)
    assert rc == 1 and "other__edges.json" in out, out


def test_override_filename_must_match_firmware_field(repo):
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    _write_override(repo, _edge_override(paths), name="somethingelse__edges.json")
    _commit_all(repo, "filename mismatch")
    rc, out = _run(repo, base)
    assert rc == 1 and "somethingelse__edges.json" in out, out


def test_unknown_firmware_id_fails(repo):
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    _write_override(repo, _edge_override(paths, fid="ghost"), name="ghost__edges.json")
    _commit_all(repo, "override for a firmware that does not exist")
    rc, out = _run(repo, base)
    assert rc == 1 and "ghost" in out, out


@pytest.mark.parametrize("bad", [
    "data/firmware/victim/firmware.md",
    "data/recipes/m5stack-cores3__victim/notes.md",
    "data/recipes/m5stack-cores3__victimx/recipe.md",
])
def test_listed_path_outside_the_firmwares_recipes_fails(repo, bad):
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    record = _edge_override(paths)
    record["deletes"].append(bad)
    record["originals"][bad] = "x\n"
    _write_override(repo, record)
    _commit_all(repo, "path mismatch")
    rc, out = _run(repo, base)
    assert rc == 1 and bad in out, out


def test_originals_mismatch_vs_base_fails(repo):
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths)
    record = _edge_override(paths)
    record["originals"][paths[0]] = record["originals"][paths[0]].rstrip("\n")   # one byte short
    _write_override(repo, record)
    _commit_all(repo, "tampered original")
    rc, out = _run(repo, base)
    assert rc == 1 and paths[0] in out and "victim__edges.json" in out, out


def test_originals_are_compared_as_bytes_not_newline_normalised(repo):
    """CRLF at BASE must be preserved verbatim; an LF-only copy is not the original."""
    crlf = "---\r\nid: m5stack-cores3__victim\r\n---\r\n"
    p = repo / _recipe_path("m5stack-cores3")
    p.parent.mkdir(parents=True)
    p.write_bytes(crlf.encode())
    _commit_all(repo, "seed crlf recipe")
    base = _base(repo)
    _delete(repo, _recipe_path("m5stack-cores3"))
    record = _edge_override([_recipe_path("m5stack-cores3")])
    record["originals"] = {_recipe_path("m5stack-cores3"): crlf.replace("\r\n", "\n")}
    _write_override(repo, record)
    _commit_all(repo, "lf copy of a crlf original")
    rc, out = _run(repo, base)
    assert rc == 1, out
    record["originals"] = {_recipe_path("m5stack-cores3"): crlf}
    _write_override(repo, record)
    _commit_all(repo, "exact original")
    rc, out = _run(repo, base)
    assert rc == 0, out


@pytest.mark.parametrize("with_firmware_override", [False, True])
def test_firmware_deleted_alongside_edge_override_fails(repo, with_firmware_override):
    """An edge correction is for a firmware that STAYS; deleting it in the same change is a
    misuse of the edge lane and fails, whatever the whole-firmware override says."""
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, *paths, "data/firmware/victim/firmware.md")
    _write_override(repo, _edge_override(paths))
    if with_firmware_override:
        _write_override(repo, {"why": "human said so"}, name="victim.json")
    _commit_all(repo, "firmware and edges together")
    rc, out = _run(repo, base)
    assert rc == 1 and "victim__edges.json" in out, out


def test_edge_override_does_not_unlock_firmware_deletion(repo):
    """The firmware-deletion rules are untouched: an edge override never stands in for
    jr/overrides/<id>.json."""
    base = _seed_edges(repo)
    paths = _edge_paths()
    _delete(repo, "data/firmware/victim/firmware.md", "data/recipes/m5cardputer__victim/recipe.md", *paths)
    _write_override(repo, _edge_override(paths))
    _commit_all(repo, "delete floor-passing firmware under an edge override only")
    rc, out = _run(repo, base)
    assert rc == 1 and "deleting firmware 'victim'" in out, out


def test_warble_style_whole_firmware_override_still_passes(repo):
    (repo / "data" / "firmware" / "victim" / "signals.json").write_text("{}\n")
    _commit_all(repo, "add signals")
    base = _base(repo)
    deletes = ["data/firmware/victim/firmware.md", "data/firmware/victim/signals.json",
               "data/recipes/m5cardputer__victim/recipe.md"]
    _delete(repo, *deletes)
    _write_override(repo, {
        "id": "victim", "repo": "o/victim", "action": "delete", "deletes": deletes,
        "classification": "host_only_backend_not_esp_firmware", "why": "not ESP firmware",
        "source": "https://github.com/o/victim#readme", "directed_by": "repository owner",
        "date": "2026-11-04"}, name="victim.json")
    _commit_all(repo, "warble-style removal")
    rc, out = _run(repo, base)
    assert rc == 0, out


def test_edge_override_path_helper():
    assert g2_guard.edge_override_firmware_id("jr/overrides/nucleoos__edges.json") == "nucleoos"
    assert g2_guard.edge_override_firmware_id("jr/overrides/warble.json") is None
    assert g2_guard.edge_override_firmware_id("jr/overrides/x/y__edges.json") is None
    assert g2_guard.edge_override_firmware_id("jr/overrides/__edges.json") is None
    assert g2_guard.changed_paths("A\tjr/overrides/a__edges.json\nM\tb\nD\tc\n") == [
        "jr/overrides/a__edges.json", "b"]
