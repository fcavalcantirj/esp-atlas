"""Tests for jr/backfill_boards.py — the audit + backfill driver (SPEC-firmware-board-mapping.md
§6-§7). Hermetic: every network effect (`manifest_api`, `readme_fetch`) is a fake built from the
real captured fixtures board_declared's own oracle uses (jr/fixtures/board_declared/), and every
write lands under `tmp_path`, never the real data/ tree. Board RESOLUTION still reads the real
catalog (board_resolver.resolve_boards() is hardwired to data/boards/, same as its own oracle) —
only the firmware/recipe TREE being audited/backfilled is a temp copy.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import backfill_boards as bb
import tools

FIX = Path(__file__).resolve().parent / "fixtures" / "board_declared"
ESP_CLAW_TREE = json.loads((FIX / "esp-claw-tree.json").read_text())
EVIL_M5PROJECT_README = (FIX / "evil-m5project-README.md").read_text()

ESP_CLAW_RESOLVED_BOARDS = {
    "m5stack-cores3", "esp32-s3-devkitc-1", "firebeetle-2-esp32-s3", "xiao-esp32s3-sense",
    "m5stick-s3", "lilygo-t-display-s3", "waveshare-esp32-s3-rlcd-42",
}
EVIL_M5PROJECT_RESOLVED_BOARDS = {
    "m5cardputer", "m5stack-core2", "m5stack-cores3", "m5atoms3",
    "m5stack-fire", "m5stack-core-aws", "m5stack-cores3-se", "m5stick-c", "m5stick-cplus",
}


class FakeApi:
    def __init__(self, routes: dict):
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, path: str):
        self.calls.append(path)
        if path not in self.routes:
            raise RuntimeError(f"404: {path}")
        return self.routes[path]


def fake_readme(text: str):
    def fetch(url: str):
        return text
    return fetch


def _write_firmware(root: Path, fid: str, url: str, socs: list[str]) -> Path:
    d = root / "data" / "firmware" / fid
    d.mkdir(parents=True)
    socs_block = "\n".join(f"- {s}" for s in socs)
    (d / "firmware.md").write_text(
        "---\n"
        f"id: {fid}\n"
        "type: firmware\n"
        f"name: {fid}\n"
        f"url: {url}\n"
        "category: multi\n"
        "socs:\n"
        f"{socs_block}\n"
        "sources:\n"
        f"- field: '*'\n  url: {url}\n  verified: '2026-08-27'\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )
    return d / "firmware.md"


def _write_recipe(root: Path, board: str, fid: str) -> Path:
    d = root / "data" / "recipes" / f"{board}__{fid}"
    d.mkdir(parents=True)
    chip = tools.board_soc(board) or "esp32"
    (d / "recipe.md").write_text(
        "---\n"
        f"id: {board}__{fid}\n"
        "type: recipe\n"
        f"board: {board}\n"
        f"firmware: {fid}\n"
        "status: unverified\n"
        f"chip_family: {chip}\n"
        "sources:\n"
        f"- field: '*'\n  url: https://example.com\n  verified: '2026-08-27'\n"
        "---\n\nBody.\n",
        encoding="utf-8",
    )
    return d / "recipe.md"


@pytest.fixture
def root(tmp_path):
    (tmp_path / "data" / "recipes").mkdir(parents=True)
    return tmp_path


ESP_CLAW_API = FakeApi({
    "repos/espressif/esp-claw": {"default_branch": "master"},
    "repos/espressif/esp-claw/git/trees/master?recursive=1": ESP_CLAW_TREE,
})
EVIL_M5PROJECT_API = FakeApi({
    "repos/7h30th3r0n3/Evil-M5Project": {"default_branch": "main"},
    "repos/7h30th3r0n3/Evil-M5Project/git/trees/main?recursive=1": {"tree": []},
})


# ─────────────────────────── audit_one ───────────────────────────

def test_audit_one_esp_claw_added_present_stale_and_socs_delta(root):
    _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=[])
    present_board = "m5stick-s3"
    stale_board = "m5cardputer"          # a genesis seed the manifest tree does not declare
    _write_recipe(root, present_board, "esp-claw")
    _write_recipe(root, stale_board, "esp-claw")

    r = bb.audit_one("esp-claw", root=root, manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""), ref="master")

    assert set(r["added"]) == ESP_CLAW_RESOLVED_BOARDS - {present_board}
    assert r["present"] == [present_board]
    assert r["stale_seed"] == [stale_board]
    assert "esp32_p4_eye" in r["unresolved_candidates"]
    assert len(r["unresolved_candidates"]) == 39 - len(ESP_CLAW_RESOLVED_BOARDS)
    assert r["socs_delta"] == ["esp32-s3"]
    for board in ESP_CLAW_RESOLVED_BOARDS:
        assert r["resolved"][board]["source_type"] == "manifest_tree"


def test_audit_one_evil_m5project_readme_only(root):
    _write_firmware(root, "evil-m5project", "https://github.com/7h30th3r0n3/Evil-M5Project", socs=["esp32"])

    r = bb.audit_one("evil-m5project", root=root, manifest_api=EVIL_M5PROJECT_API,
                      readme_fetch=fake_readme(EVIL_M5PROJECT_README), ref="main")

    assert set(r["added"]) == EVIL_M5PROJECT_RESOLVED_BOARDS
    assert r["present"] == []
    assert r["stale_seed"] == []
    assert r["socs_delta"] == ["esp32-s3"]      # esp32 already declared; only esp32-s3 is new
    for board in EVIL_M5PROJECT_RESOLVED_BOARDS:
        assert r["resolved"][board]["source_type"] == "readme_table"


def test_audit_one_skips_firmware_without_a_github_url(root):
    _write_firmware(root, "gitlab-thing", "https://gitlab.com/o/r", socs=[])
    r = bb.audit_one("gitlab-thing", root=root, manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""))
    assert r["skipped"]


# ─────────────────────────── audit (all) + coverage ───────────────────────────

def test_audit_all_computes_catalog_coverage_metric(root):
    _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=["esp32-s3"])
    _write_firmware(root, "empty-repo", "https://github.com/o/r", socs=[])

    def manifest_api(path):
        if path.startswith("repos/espressif/esp-claw"):
            return ESP_CLAW_API(path)
        if path == "repos/o/r":
            return {"default_branch": "main"}
        if path == "repos/o/r/git/trees/main?recursive=1":
            return {"tree": []}
        raise RuntimeError(f"404: {path}")

    report = bb.audit(root, manifest_api=manifest_api, readme_fetch=fake_readme(""))

    assert set(report["firmware"]) == {"esp-claw", "empty-repo"}
    assert report["coverage"] == {"considered": 2, "with_declared_board": 1, "pct": 50.0}


def test_audit_all_can_be_scoped_to_specific_firmware_ids(root):
    _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=["esp32-s3"])
    _write_firmware(root, "empty-repo", "https://github.com/o/r", socs=[])
    report = bb.audit(root, ["esp-claw"], manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""))
    assert set(report["firmware"]) == {"esp-claw"}
    assert report["coverage"]["considered"] == 1


# ─────────────────────────── dry_run: never writes ───────────────────────────

def test_dry_run_writes_nothing(root):
    _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=[])
    before = (root / "data" / "firmware" / "esp-claw" / "firmware.md").read_text()
    before_recipes = sorted((root / "data" / "recipes").iterdir())

    report = bb.dry_run(root, ["esp-claw"], manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""))

    assert set(report["firmware"]["esp-claw"]["added"]) == ESP_CLAW_RESOLVED_BOARDS
    assert (root / "data" / "firmware" / "esp-claw" / "firmware.md").read_text() == before
    assert sorted((root / "data" / "recipes").iterdir()) == before_recipes


# ─────────────────────────── apply ───────────────────────────

def test_apply_writes_expected_recipes_with_declared_status_and_provenance(root):
    fmd = _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=[])
    report = bb.audit(root, ["esp-claw"], manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""))

    out = bb.apply(report, root=root, today="2026-09-21")

    assert set(out["written"]) == {f"{b}__esp-claw" for b in ESP_CLAW_RESOLVED_BOARDS}
    for board in ESP_CLAW_RESOLVED_BOARDS:
        rc = tools._frontmatter(root / "data" / "recipes" / f"{board}__esp-claw" / "recipe.md")
        assert rc["status"] == "declared"
        assert rc["chip_family"] == tools.board_soc(board)
        assert rc["sources"] == [{
            "field": "boards",
            "url": "https://github.com/espressif/esp-claw/tree/master/application/edge_agent/boards",
            "verified": "2026-09-21",
        }]
    fm = tools._frontmatter(fmd)
    assert fm["socs"] == ["esp32-s3"]
    assert {"field": "socs", "url": "https://github.com/espressif/esp-claw/tree/master/application/edge_agent/boards",
            "verified": "2026-09-21"} in fm["sources"]


def test_apply_never_writes_a_recipe_for_an_unresolved_candidate(root):
    _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=[])
    report = bb.audit(root, ["esp-claw"], manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""))
    bb.apply(report, root=root, today="2026-09-21")

    written_boards = {p.name.split("__")[0] for p in (root / "data" / "recipes").iterdir()}
    assert written_boards == ESP_CLAW_RESOLVED_BOARDS      # never esp32_p4_eye or any unresolved raw ref
    assert not any((root / "data" / "recipes" / f"{raw}__esp-claw").exists()
                   for raw in report["firmware"]["esp-claw"]["unresolved_candidates"])


def test_apply_never_touches_a_stale_seed_recipe(root):
    _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=["esp32-s3"])
    stale_rc = _write_recipe(root, "m5cardputer", "esp-claw")   # not declared by the manifest tree
    before = stale_rc.read_text()

    report = bb.audit(root, ["esp-claw"], manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""))
    assert "m5cardputer" in report["firmware"]["esp-claw"]["stale_seed"]
    bb.apply(report, root=root, today="2026-09-21")

    assert stale_rc.read_text() == before
    assert stale_rc.exists()


def test_apply_is_idempotent(root):
    _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=[])
    report1 = bb.audit(root, ["esp-claw"], manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""))
    out1 = bb.apply(report1, root=root, today="2026-09-21")
    assert len(out1["written"]) == len(ESP_CLAW_RESOLVED_BOARDS)

    # a fresh audit of the now-backfilled tree sees nothing left to add
    report2 = bb.audit(root, ["esp-claw"], manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""))
    assert report2["firmware"]["esp-claw"]["added"] == []
    assert report2["firmware"]["esp-claw"]["socs_delta"] == []

    out2 = bb.apply(report2, root=root, today="2026-09-22")
    assert out2["written"] == []
    assert out2["socs_widened"] == {}
    # re-applying the ORIGINAL report a second time is also a no-op (existing recipes untouched)
    out3 = bb.apply(report1, root=root, today="2026-09-23")
    assert out3["written"] == []


def test_apply_emits_a_ranked_candidate_boards_report(root):
    _write_firmware(root, "esp-claw", "https://github.com/espressif/esp-claw", socs=[])
    report = bb.audit(root, ["esp-claw"], manifest_api=ESP_CLAW_API, readme_fetch=fake_readme(""))
    out = bb.apply(report, root=root, today="2026-09-21")

    names = {c["name"] for c in out["candidates"]}
    assert "esp32_p4_eye" in names
    for c in out["candidates"]:
        assert c["firmware"] == ["esp-claw"]
        assert c["count"] == 1
    counts = [c["count"] for c in out["candidates"]]
    assert counts == sorted(counts, reverse=True)
