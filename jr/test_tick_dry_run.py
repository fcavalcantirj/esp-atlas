"""The dry-run is structurally read-only (jr/tick.py, jr/dry_run_tree.py).

Regression: run_tick(dry_run=True) used to run the stages against the real clone, and
jr/stage_backfill.py wrote board.md files and jr/board_cooldown.json straight into the checkout.
The old "writes nothing" test used an empty stage list, so it never ran the real backfill.

Here a temp checkout carries a GROUNDABLE board (an offline vendor page that yields a real
usb_serial + download_mode), a board whose page is unreachable (it would be cooled down), and an
existing jr/board_cooldown.json. The REAL hourly stage list runs (backfill included) on fake gh and
fake http. The dry-run must leave every byte of the checkout as it was and still list what a real
run would write; the same tick for real, on a copy, must write it (the fixture is groundable).

Run: cd jr && python3 -m pytest test_tick_dry_run.py -v
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from datetime import timedelta
from pathlib import Path

import pytest

import board_backfill as bb
import publish
import tick
import tools
from budget import Budget
from test_tick import GAUGE, GUARD_OK, NO_DEMAND, NO_SNAPSHOT, NOW, gh_ok, git_ok

GROUNDABLE = "esp32-s3-devkit-coder-1"
UNREACHABLE = "esp32-c6-devkit-coder-4"
ALREADY_COOLING = "esp32-h2-devkit-coder-5"
MANUAL_SENTENCE = ("Press and hold the Boot button, then press the Reset button, "
                   "then release Boot to enter Firmware Download mode")
VENDOR_PAGE = f"""<html><body>
<h1>ESP32-S3-DevKit-Coder-1 User Guide</h1>
<p>This board carries a CP2102N USB-to-UART bridge.</p>
<p>{MANUAL_SENTENCE}. After flashing, press Reset to run the application.</p>
</body></html>"""
GROUNDABLE_MD = f"data/boards/espressif/{GROUNDABLE}/board.md"


def _board(root: Path, board_id: str, soc: str) -> None:
    d = root / "data" / "boards" / "espressif" / board_id
    d.mkdir(parents=True)
    (d / "board.md").write_text(
        f"---\nid: {board_id}\ntype: board\nbrand: espressif\nname: {board_id}\nsoc: {soc}\n"
        f"sources:\n- field: '*'\n  url: https://example.test/{board_id}\n  verified: '2026-01-01'\n"
        f"---\n\n# {board_id}\n")


def _checkout(root: Path) -> Path:
    _board(root, GROUNDABLE, "esp32-s3")
    _board(root, UNREACHABLE, "esp32-c6")
    _board(root, ALREADY_COOLING, "esp32-h2")
    (root / "jr").mkdir()
    (root / "jr" / "board_cooldown.json").write_text(json.dumps({"by_board": {ALREADY_COOLING: {
        "board": ALREADY_COOLING, "reason": "doc-unreachable", "field_reasons": {},
        "timestamp": (NOW - timedelta(days=1)).isoformat(),
        "expires": (NOW + timedelta(days=6)).isoformat()}}}, indent=2, sort_keys=True) + "\n")
    lapsed = {"id": "old-fw", "repo": "o/old-fw", "status": "seen", "reason": "below floor", "pr_ref": None,
              "timestamp": (NOW - timedelta(days=40)).isoformat(), "expires": (NOW - timedelta(days=10)).isoformat()}
    (root / "jr" / "proposed_ledger.json").write_text(
        json.dumps({"by_id": {"old-fw": lapsed}, "by_repo": {"o/old-fw": "old-fw"}}, indent=2, sort_keys=True) + "\n")
    (root / "docs" / "telemetry").mkdir(parents=True)
    (root / "docs" / "telemetry" / "data-trend.jsonl").write_text("")
    (root / "COVERAGE.md").write_text("# coverage\n")
    (root / "untracked-notes.txt").write_text("an untracked file the owner left lying around\n")
    return root


def _fingerprint(root: Path) -> dict:
    """relpath -> sha256 for EVERY file (dotfiles, untracked, bookkeeping), plus every directory."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for d in dirnames:
            out[str(Path(dirpath, d).relative_to(root)) + "/"] = "dir"
        for f in filenames:
            p = Path(dirpath, f)
            out[str(p.relative_to(root))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def _vendor_fetch(url):
    """Fake http: the groundable board's user guide answers 200, everything else 404."""
    if url == bb.board_user_guide_url(GROUNDABLE, "esp32-s3"):
        return {"ok": True, "status": 200, "text": VENDOR_PAGE}
    return {"ok": False, "status": 404, "error": "HTTP 404"}


@pytest.fixture
def offline(monkeypatch):
    monkeypatch.setattr(bb, "default_fetch", _vendor_fetch)
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda *a, **k: [])


def _run(dry_run: bool, git, tmp_path: Path):
    return tick.run_tick(dry_run=dry_run, git=git, gh=gh_ok(), now=NOW, env={}, stages=None,
                         gauge=GAUGE, guard=GUARD_OK, notifier=None, snapshot=NO_SNAPSHOT,
                         demand=NO_DEMAND, budget=Budget(clock=lambda: 0.0),
                         lock_path=tmp_path / "lock")


def test_dry_run_with_the_real_stages_leaves_the_checkout_byte_identical(tmp_path, monkeypatch, offline, capsys):
    checkout = _checkout(tmp_path / "checkout")
    monkeypatch.setattr(tick, "REPO", checkout)
    before = _fingerprint(checkout)

    r = _run(True, git_ok(tmp_path), tmp_path)

    assert not r.aborted, r.aborted
    assert _fingerprint(checkout) == before          # no byte changed, no file or dir appeared
    assert [s["name"] for s in r.stages][0] == "backfill"
    writes = {(w["path"], w["field"]) for w in r.would_write}
    assert (GROUNDABLE_MD, "usb_serial") in writes
    assert (GROUNDABLE_MD, "download_mode") in writes
    assert ("jr/board_cooldown.json", f"by_board.{UNREACHABLE}") in writes
    assert ("jr/proposed_ledger.json", "by_id.old-fw") in writes       # the lapsed decision a real tick expires
    assert ("docs/telemetry/data-trend.jsonl", "row 2026-09-05") in writes
    assert not r.paths                                # nothing was WRITTEN, only would-be
    line = capsys.readouterr().out
    assert f"{GROUNDABLE_MD}[download_mode,usb_serial," in line
    assert f"jr/board_cooldown.json[by_board.{UNREACHABLE}]" in line


def test_the_scratch_copy_is_removed_after_the_dry_run(tmp_path, monkeypatch, offline):
    checkout = _checkout(tmp_path / "checkout")
    monkeypatch.setattr(tick, "REPO", checkout)
    made = []
    real_copy = tick.dry_run_tree.copy
    monkeypatch.setattr(tick.dry_run_tree, "copy", lambda src: made.append(real_copy(src)) or made[-1])

    r = _run(True, git_ok(tmp_path), tmp_path)

    assert not r.aborted and len(made) == 1
    assert checkout not in made[0].parents and made[0] != checkout
    assert not made[0].exists()


def test_the_same_tick_for_real_writes_the_field_so_the_fixture_is_groundable(tmp_path, monkeypatch, offline):
    checkout = _checkout(tmp_path / "checkout")
    monkeypatch.setattr(tick, "REPO", checkout)
    wt = tmp_path / "wt"
    shutil.copytree(checkout, wt)
    monkeypatch.setattr(publish.tempfile, "mkdtemp", lambda prefix="": str(wt))

    r = _run(False, git_ok(wt, diff=f"M\0{GROUNDABLE_MD}\0"), tmp_path)

    assert not r.aborted, r.aborted
    fm, _ = bb.parse_frontmatter(wt / GROUNDABLE_MD)
    assert fm["usb_serial"] == "cp2102n"
    assert fm["download_mode"] == {"mode": "manual", "steps": MANUAL_SENTENCE}
    cooled = json.loads((wt / "jr" / "board_cooldown.json").read_text())["by_board"]
    assert UNREACHABLE in cooled and ALREADY_COOLING in cooled
    assert GROUNDABLE_MD in r.paths and "jr/board_cooldown.json" in r.paths


def test_a_step_that_ignores_dry_run_writes_only_the_copy_and_is_reported(tmp_path, monkeypatch, offline):
    checkout = _checkout(tmp_path / "checkout")
    monkeypatch.setattr(tick, "REPO", checkout)
    before = _fingerprint(checkout)

    def careless(ctx):
        (ctx.root / "data" / "boards" / "espressif" / GROUNDABLE / "board.md").write_text("clobbered\n")
        (ctx.root / "data" / "stray.json").write_text("{}\n")
        return tick.StageResult("careless")

    r = tick.run_tick(dry_run=True, git=git_ok(tmp_path), gh=gh_ok(), now=NOW, env={}, stages=[careless],
                      gauge=GAUGE, guard=GUARD_OK, notifier=None, snapshot=NO_SNAPSHOT, demand=NO_DEMAND,
                      budget=Budget(clock=lambda: 0.0))

    assert not r.aborted, r.aborted
    assert _fingerprint(checkout) == before
    writes = {(w["path"], w["field"]) for w in r.would_write}
    assert {(GROUNDABLE_MD, "*"), ("data/stray.json", "*")} <= writes
    assert sum("ignores dry-run" in w for w in r.warnings) == 2
