"""Tests for jr/stage_admit.py — the Track A admission stage, end to end on a tmp tree with
fake network. The tmp root carries a COPY of the real data/boards + data/modules (the stage
resolves chips against the tree it writes), so nothing real is written."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import memory
import stage_admit
import tick
import tools
import writers
from budget import Budget

REPO = Path(__file__).resolve().parent.parent
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=timezone.utc)

SEED_FW = """\
---
id: seed-original
type: firmware
name: Seed Original
url: https://github.com/o/original
category: multi
socs:
- esp32
sources:
- field: '*'
  url: https://github.com/o/original
  verified: '2026-09-01'
---

Seed.
"""


def _meta(full_name, stars=30, forks=0, fork=False, source=None, archived=False, description=None,
          license="MIT", rid=1):
    return {"full_name": full_name, "description": description, "license": {"spdx_id": license},
            "topics": [], "homepage": None, "default_branch": "main",
            "stargazers_count": stars, "archived": archived, "forks_count": forks,
            "id": rid, "fork": fork,
            "source": {"full_name": source} if source else None,
            "parent": {"full_name": source} if source else None,
            "pushed_at": "2026-09-01T00:00:00Z", "language": "C"}


def _entry(name, github, category="cardputer", download=100, description=None):
    return {"name": name, "description": description, "category": category, "github": github,
            "download": download}


@pytest.fixture
def root(tmp_path):
    shutil.copytree(REPO / "data" / "boards", tmp_path / "data" / "boards")
    shutil.copytree(REPO / "data" / "modules", tmp_path / "data" / "modules")
    (tmp_path / "data" / "firmware" / "seed-original").mkdir(parents=True)
    (tmp_path / "data" / "firmware" / "seed-original" / "firmware.md").write_text(SEED_FW)
    (tmp_path / "data" / "recipes").mkdir()
    (tmp_path / "jr").mkdir()
    return tmp_path


def _ctx(root, dry_run=False, budget=None, metas=None):
    metas = metas or {}
    budget = budget or Budget(clock=lambda: 0.0)

    def gh(*a):
        doc = metas.get(a[1])
        if doc is None:
            return SimpleNamespace(returncode=1, stdout="", stderr="404 not found")
        return SimpleNamespace(returncode=0, stdout=json.dumps(doc), stderr="")

    return tick.TickContext(root=root, ledger_path=root / "jr" / "proposed_ledger.json", now=NOW,
                            gh=budget.wrap(gh), git=lambda *a: None,
                            budget=budget, dry_run=dry_run, env={})


def _firmware_schema():
    return json.loads((REPO / "schema" / "firmware.schema.json").read_text())


def _read_fm(path):
    import jsonschema
    fm = yaml.safe_load(path.read_text().split("\n---\n")[0].split("---\n", 1)[1])
    jsonschema.validate(fm, _firmware_schema())   # the real schema, additionalProperties false
    return fm


def test_fork_of_catalogued_is_rejected_without_writing(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Fork Tool", "https://github.com/f/fork")])
    metas = {"repos/f/fork": _meta("f/fork", fork=True, source="o/original", rid=11)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.name == "admit" and res.admitted == 0 and res.paths == []
    assert res.rejects == {"fork_of_catalogued": 1}
    assert "fork_of_catalogued" in res.summary
    assert {p.name for p in (root / "data" / "firmware").iterdir()} == {"seed-original"}
    led = memory.load(root / "jr" / "proposed_ledger.json")
    rec = led["by_id"]["fork"]
    assert rec["status"] == "rejected" and rec["repo_id"] == 11
    assert rec["expires"] is not None   # TTL'd, re-checked after SEEN_TTL_DAYS


def test_floor_failing_repo_is_rejected_with_ttl_and_blocked(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Tiny Tool", "https://github.com/t/tiny")])
    metas = {"repos/t/tiny": _meta("t/tiny", stars=3, forks=4, rid=12)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 0 and res.rejects == {"below_floor": 1}
    led = memory.load(root / "jr" / "proposed_ledger.json")
    assert memory.is_blocked(led, repo_id=12, now=NOW)
    rec = led["by_id"]["tiny"]
    assert rec["reason"].startswith("below_floor:") and rec["repo_id"] == 12


def test_admitted_record_is_schema_valid_proposed_and_cited(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("My Cardputer Tool", "https://github.com/n/newtool")])
    metas = {"repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 1 and not res.needs_human and res.rejects == {}
    assert res.paths == ["data/firmware/newtool/firmware.md"]
    fm = _read_fm(root / "data" / "firmware" / "newtool" / "firmware.md")
    assert fm["id"] == "newtool" and fm["type"] == "firmware"
    assert fm["url"] == "https://github.com/n/newtool" and fm["category"] == "multi"
    assert fm["socs"] == ["esp32-s3"] and fm["maintainer"] == "n"
    assert fm["sources"] == [
        {"field": "*", "url": "https://github.com/n/newtool", "verified": "2026-09-07"},
        {"field": "popularity", "url": "https://github.com/n/newtool", "verified": "2026-09-07"}]
    body = (root / "data" / "firmware" / "newtool" / "firmware.md").read_text().split("---\n")[-1]
    assert "Admitted by jr/scorer.py rule authored." in body
    led = memory.load(root / "jr" / "proposed_ledger.json")
    assert led["by_id"]["newtool"]["status"] == "proposed"
    assert led["by_id"]["newtool"]["repo_id"] == 13


def test_high_star_admission_flags_needs_human(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Big Tool", "https://github.com/b/big", download=10)])
    metas = {"repos/b/big": _meta("b/big", stars=60000, description="A Cardputer tool", rid=14)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert res.admitted == 1 and res.needs_human
    assert "(needs_human)" in res.summary
    body = (root / "data" / "firmware" / "big" / "firmware.md").read_text()
    assert "Admitted by jr/scorer.py rule needs_human." in body


def test_second_run_admits_nothing(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("My Cardputer Tool", "https://github.com/n/newtool")])
    metas = {"repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13)}
    first = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert first.admitted == 1
    second = stage_admit.run(_ctx(root, metas=metas), budget=3)
    assert second.admitted == 0 and second.paths == [] and second.rejects == {}
    assert "already decided" in second.summary


def test_budget_stop_line_and_order_are_deterministic(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("B Tool", "https://github.com/n/btool"),
        _entry("A Tool", "https://github.com/n/atool"),
    ])
    metas = {"repos/n/atool": _meta("n/atool", stars=30, description="A Cardputer tool", rid=15),
             "repos/n/btool": _meta("n/btool", stars=30, description="B Cardputer tool", rid=16)}
    res = stage_admit.run(_ctx(root, metas=metas), budget=1)
    assert res.admitted == 1 and res.paths == ["data/firmware/atool/firmware.md"]  # name, then github
    assert "budget reached (1 admitted)" in res.summary


def test_dry_run_scores_and_reports_but_writes_nothing(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog", lambda: [
        _entry("My Cardputer Tool", "https://github.com/n/newtool"),
        _entry("Tiny Tool", "https://github.com/t/tiny"),
    ])
    metas = {"repos/n/newtool": _meta("n/newtool", stars=30, description="A Cardputer tool", rid=13),
             "repos/t/tiny": _meta("t/tiny", stars=1, forks=0, rid=12)}
    res = stage_admit.run(_ctx(root, metas=metas, dry_run=True), budget=3)
    assert res.admitted == 0 and res.paths == [] and res.rejects == {"below_floor": 1}
    assert "would admit" in res.summary
    assert not (root / "data" / "firmware" / "newtool").exists()
    assert not (root / "jr" / "proposed_ledger.json").exists()   # memory untouched


def test_repo_id_memory_hit_skips_before_fetch(root, monkeypatch):
    monkeypatch.setattr(tools, "fetch_launcher_catalog",
                        lambda: [_entry("Bruce 1.12", "https://github.com/BruceDevices/firmware")])
    memory.record_rejected("bruce", "brucedevices/firmware", "duplicate_of bruce (repo_id 795166961)",
                           ttl_days=None, repo_id=795166961,
                           path=root / "jr" / "proposed_ledger.json", now=NOW)
    def boom(*a):
        raise AssertionError("must not fetch a memory-blocked repo")
    c = _ctx(root)
    c = tick.TickContext(root=c.root, ledger_path=c.ledger_path, now=c.now,
                         gh=c.budget.wrap(boom), git=c.git, budget=c.budget, dry_run=False, env=c.env)
    res = stage_admit.run(c, budget=3)
    assert res.admitted == 0 and res.rejects == {} and "already decided" in res.summary


def test_render_firmware_refuses_a_non_schema_id():
    with pytest.raises(ValueError):
        writers.render_firmware({"id": "Bad Id!", "chip": "esp32"}, [], "2026-09-07")
