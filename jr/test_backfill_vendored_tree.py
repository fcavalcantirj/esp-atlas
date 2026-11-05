"""THE ORACLE — backfill must not re-admit the NucleoOS false edges (plan
2026-11-05-nucleoos-correction.md spec C; SPEC-firmware-board-mapping.md §3.1).

Commit 7ab78445 ran jr/backfill_boards over the catalog and wrote six `declared` recipes for
nucleoos, all citing `reference/esp-claw/application/edge_agent/boards` — a vendored esp-claw
study copy NucleoOS's own reference/README.md says is "not built or shipped". Those six recipes
are deleted under jr/overrides/nucleoos__edges.json. This pins that a fresh audit + apply over a
NucleoOS-shaped tree (the real esp-claw tree fixture, nested under `reference/esp-claw/`) does
not write them back, while the same tree as esp-claw's own first-party root still does — so the
negative is the vendored-tree skip at work, not a fixture that resolves nothing.

Hermetic, same harness as test_backfill_boards.py: fake `manifest_api`/`readme_fetch`, every
write under `tmp_path`; only board resolution reads the real catalog.

Run: cd jr && python3 -m pytest test_backfill_vendored_tree.py -v
"""
from __future__ import annotations

import json
from pathlib import Path

import backfill_boards as bb
from test_backfill_boards import FakeApi, _write_firmware, _write_recipe, fake_readme, root  # noqa: F401

FIX = Path(__file__).resolve().parent / "fixtures" / "board_declared"
ESP_CLAW_TREE = json.loads((FIX / "esp-claw-tree.json").read_text())

NUCLEOOS_URL = "https://github.com/indecenti/NucleoOs"
VENDORED_PREFIX = "reference/esp-claw/"
CORRECTED_BOARDS = {
    "esp32-s3-devkitc-1", "firebeetle-2-esp32-s3", "lilygo-t-display-s3",
    "m5stack-cores3", "m5stick-s3", "waveshare-esp32-s3-rlcd-42",
}


def _tree_api(owner_repo: str, branch: str, tree: dict) -> FakeApi:
    return FakeApi({
        f"repos/{owner_repo}": {"default_branch": branch},
        f"repos/{owner_repo}/git/trees/{branch}?recursive=1": tree,
    })


def _nucleoos_shaped_tree() -> dict:
    vendored = [{**entry, "path": VENDORED_PREFIX + entry["path"]} for entry in ESP_CLAW_TREE["tree"]]
    own = [{"path": p, "type": "blob"} for p in ("README.md", "reference/README.md", "src/main.cpp")]
    return {"tree": own + vendored, "truncated": False}


def _recipe_dirs(root: Path, fid: str) -> set[str]:
    return {p.name for p in (root / "data" / "recipes").glob(f"*__{fid}") if p.is_dir()}


def test_backfill_over_a_nucleoos_shaped_tree_recreates_none_of_the_six_edges(root):
    _write_firmware(root, "nucleoos", NUCLEOOS_URL, socs=["esp32-s3"])
    _write_recipe(root, "m5cardputer", "nucleoos")          # the kept, README-declared edge
    api = _tree_api("indecenti/NucleoOs", "main", _nucleoos_shaped_tree())

    report = bb.audit(root, ["nucleoos"], manifest_api=api, readme_fetch=fake_readme(""))
    r = report["firmware"]["nucleoos"]
    assert r["resolved"] == {}
    assert r["added"] == []
    assert r["unresolved_candidates"] == []

    out = bb.apply(report, root=root, today="2026-11-04")
    assert out["written"] == []
    assert _recipe_dirs(root, "nucleoos") == {"m5cardputer__nucleoos"}
    assert not CORRECTED_BOARDS & {d[: -len("__nucleoos")] for d in _recipe_dirs(root, "nucleoos")}


def test_the_same_tree_as_a_first_party_root_still_resolves_all_six(root):
    # Control: un-nested, the identical fixture is esp-claw's own manifest tree and yields the six
    # boards — so the NucleoOS negative above is the vendored skip, not an empty fixture.
    _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=[])
    api = _tree_api("espressif/esp-claw", "master", ESP_CLAW_TREE)

    report = bb.audit(root, ["esp-claw"], manifest_api=api, readme_fetch=fake_readme(""))
    assert CORRECTED_BOARDS <= set(report["firmware"]["esp-claw"]["added"])
