"""scripts/receipt_guard.py — a tick PR is mergeable on its evidence receipts alone only when every added
recipe's PASS receipt holds again on the live upstream. Throwaway git repos, fake GitHub answers."""
from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

import pytest

import receipt_guard as rg

BRANCH = "jr/tick-20261117-1900"
FW = """---
id: {fid}
type: firmware
name: {name}
url: https://github.com/o/{fid}
category: multi
socs:
- esp32-s3
sources:
- field: '*'
  url: https://github.com/o/{fid}
  verified: '2026-11-17'
---

Body.
"""
RECIPE = """---
id: {board}__{fid}
type: recipe
board: {board}
firmware: {fid}
status: unverified
chip_family: esp32-s3
notes: "{fid} names this board as {name} in its repository name/description; named in the repository itself, not verified on hardware.{receipt}"
sources:
- field: '*'
  url: https://github.com/o/{fid}
  verified: '2026-11-17'
---

# {board} x {fid}
"""
CATALOG = {"m5cardputer-adv": {"id": "m5cardputer-adv", "name": "Cardputer-Adv", "aka": [], "soc": "esp32-s3", "brand": "m5stack"},
           "m5cardputer": {"id": "m5cardputer", "name": "Cardputer", "aka": ["m5stack_cardputer"], "soc": "esp32-s3", "brand": "m5stack"}}


def _git(repo, *args):
    p = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, (args, p.stderr)
    return p.stdout


def _commit(repo, subject):
    _git(repo, "add", "-A")
    _git(repo, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", subject)


def _write(repo, rel, text):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q", "-b", "main")
    _write(r, "data/firmware/seed/firmware.md", FW.format(fid="seed", name="Seed"))
    _write(r, "jr/proposed_ledger.json", "{}")
    _commit(r, "base")
    _git(r, "checkout", "-q", "-b", BRANCH)
    return r


def add_edge(repo, fid="uhf-expansion", board="m5cardputer-adv", name="Cardputer-Adv", receipt=" Evidence check v3 PASS — named: the source names m5cardputer-adv."):
    _write(repo, f"data/firmware/{fid}/firmware.md", FW.format(fid=fid, name=name))
    _write(repo, f"data/recipes/{board}__{fid}/recipe.md", RECIPE.format(board=board, fid=fid, name=name, receipt=receipt))
    _write(repo, "jr/proposed_ledger.json", json.dumps({"by_id": {fid: {"status": "proposed"}}}))
    _commit(repo, f"feat(jr): tick — {fid}")


def fake_upstream(description="", readme="", pio="", assets=()):
    def api(path):
        if path.endswith("/readme"):
            return {"content": base64.b64encode(readme.encode()).decode()}
        if "/releases" in path:
            return [{"assets": [{"name": a} for a in assets]}]
        return {"description": description, "default_branch": "main"}
    def raw(url):
        return pio if url.endswith("platformio.ini") else None
    return api, raw


def run(repo, **upstream):
    api, raw = fake_upstream(**upstream)
    return rg.check(repo, base="main", head="HEAD", branch=BRANCH, api=api, raw=raw, catalog=CATALOG)


def test_a_pass_receipt_that_holds_live_makes_the_pr_eligible(repo):
    add_edge(repo)
    problems, lines = run(repo, description="UHF expansion firmware for the M5Stack Cardputer-Adv")
    assert problems == [], problems
    # an old v3 receipt is re-judged by the CURRENT rules (v4 since 2026-11-19): that is the guard's point
    assert any("receipt v3 PASS; live re-check v4 PASS" in ln for ln in lines)


def test_a_receipt_that_no_longer_holds_on_the_live_upstream_is_not_eligible(repo):
    add_edge(repo)
    problems, _ = run(repo, description="A generic tool", readme="Runs on any ESP32-S3 board.")
    assert len(problems) == 1 and problems[0].startswith("E2") and "live re-check is FAIL" in problems[0]


def test_an_uncertain_or_missing_receipt_is_a_persons_or_the_agents(repo):
    add_edge(repo, receipt=" Evidence check v3 UNCERTAIN — sibling: named only generically.")
    assert any(p.startswith("E1") and "UNCERTAIN, not PASS" in p for p in run(repo, description="Cardputer-Adv tool")[0])
    add_edge(repo, fid="plain", board="m5cardputer", name="Cardputer", receipt="")
    assert any(p.startswith("E1") and "no evidence receipt" in p for p in run(repo, description="Cardputer tool")[0])


def test_an_edited_existing_record_or_a_deletion_is_not_eligible(repo):
    add_edge(repo)
    _write(repo, "data/firmware/seed/firmware.md", FW.format(fid="seed", name="Seed v2"))
    _commit(repo, "feat(jr): touch the seed")
    problems = run(repo, description="Cardputer-Adv tool")[0]
    assert any(p.startswith("E3") and "edited" in p for p in problems)


def test_a_tick_pr_that_adds_no_recipe_has_nothing_to_vouch_for(repo):
    _write(repo, "jr/proposed_ledger.json", '{"by_id": {"x": {"status": "rejected"}}}')
    _commit(repo, "feat(jr): tick — memory only")
    problems = run(repo)[0]
    assert problems == ["E4 no recipe added: nothing receipted to vouch for"]


def test_an_unreadable_upstream_is_no_verdict(repo):
    add_edge(repo)
    def api(path):
        raise rg.Unreadable("GitHub API repos/o/uhf-expansion: HTTP 503")
    with pytest.raises(rg.Unreadable):
        rg.check(repo, base="main", head="HEAD", branch=BRANCH, api=api, raw=lambda u: None, catalog=CATALOG)


def test_only_tick_branches_and_exit_codes(repo, capsys):
    with pytest.raises(rg.Unreadable):
        rg.check(repo, base="main", head="HEAD", branch="feat/x", catalog=CATALOG)
    assert rg.main(["--repo", str(repo), "--base", "main", "--branch", "feat/x"]) == 2


def test_receipt_of_reads_the_notes():
    assert rg.receipt_of({"notes": "x. Evidence check v3 PASS — named: y."}) == ("3", "PASS")
    assert rg.receipt_of({"notes": ["a", "Evidence check v2 UNCERTAIN — sibling"]}) == ("2", "UNCERTAIN")
    assert rg.receipt_of({"notes": "no receipt here"}) is None and rg.receipt_of({}) is None


def test_a_renamed_and_edited_existing_record_is_not_eligible(repo):
    # 4th review of #1809 (2026-11-19): without --no-renames a rename+edit showed as R096, neither M nor D
    add_edge(repo)
    _git(repo, "mv", "data/firmware/seed/firmware.md", "data/firmware/seed/firmware-renamed.md")
    _write(repo, "data/firmware/seed/firmware-renamed.md", FW.format(fid="seed", name="Seed v2"))
    _commit(repo, "feat(jr): rename and edit the seed")
    problems = run(repo, description="Cardputer-Adv tool")[0]
    assert any(p.startswith("E3") for p in problems), problems



def test_an_old_pass_receipt_the_current_rules_no_longer_grant_is_not_eligible(repo):
    # tick PR #1828 (2026-11-19): recipe m5cardputer__m5-crystal carried "Evidence check v3 PASS"; upstream says
    # "Cardputer-ADV (Cardputer v1.1)" and builds only [env:cardputer-adv]. Rules v4 answer UNCERTAIN.
    add_edge(repo, fid="m5-crystal", board="m5cardputer", name="Cardputer",
             receipt=" Evidence check v3 PASS — named: the source names m5cardputer.")
    problems = run(repo, description="Firmware for M5Stack devices",
                   readme="- Devices: M5StickCPlus2, M5StickS3, Cardputer-ADV (Cardputer v1.1)")[0]
    assert any(p.startswith("E2") and "UNCERTAIN" in p for p in problems), problems



def test_report_only_prints_the_verdict_and_exits_zero_when_not_eligible(repo, monkeypatch, capsys):
    add_edge(repo, receipt="")                                               # no receipt: E1
    api, raw = fake_upstream(description="UHF expansion firmware for the M5Stack Cardputer-Adv")
    real = rg.check
    monkeypatch.setattr(rg, "check", lambda r, **kw: real(r, **{**kw, "api": api, "raw": raw, "catalog": CATALOG}))
    args = ["--repo", str(repo), "--base", "main", "--branch", BRANCH]
    assert rg.main(args) == 1
    assert rg.main(args + ["--report-only"]) == 0
    assert "NOT ELIGIBLE" in capsys.readouterr().out
