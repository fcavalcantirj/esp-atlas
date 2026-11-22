"""jr/claims_pio.py — build-target facts from PlatformIO's own config semantics (Jr redesign plan, step 4).

Fixtures: NightDriverStrip's platformio.ini at commit 971c066b (61 envs, resolved by PlatformIO 6.2.0) and two
pioarduino 55.03.37 board manifests. Synthetic projects cover each refusal. No network.
"""
import json
from pathlib import Path

import pytest

import claims_pio as cp

FIX = Path(__file__).resolve().parent / "fixtures" / "claims_pio"
NDS = FIX / "nds-971c066b"
PIOARDUINO_37 = "https://github.com/pioarduino/platform-espressif32/releases/download/55.03.37/platform-espressif32.zip"


def manifest(board_id):
    return (FIX / f"{board_id}.pioarduino-55.03.37.json").read_bytes()


def manifests_for(spec, board_id):
    """The fake platform index: pioarduino 55.03.37 only, with the fixture manifests."""
    if spec != PIOARDUINO_37:
        return None
    p = FIX / f"{board_id}.pioarduino-55.03.37.json"
    return {"package_digest": "f" * 64, "manifest": p.read_bytes()} if p.exists() else {"package_digest": "f" * 64, "manifest": None}


@pytest.fixture(scope="module")
def nds():
    return cp.resolve_project(NDS)


def test_platformio_resolves_every_env_of_the_real_project(nds):
    assert nds["loaded"] == ["platformio.ini"]
    assert len(nds["envs"]) == 61
    assert nds["envs"]["heltecv3demo"]["board"] == "heltec_wifi_kit_32_V3"
    assert nds["envs"]["heltecv3demo"]["platform"] == PIOARDUINO_37


def test_heltecv3demo_is_a_fact_its_mcu_matches_the_definition(nds):
    facts, refusals = cp.judge(nds, manifests_for)
    by_env = {f["env"]: f for f in facts}
    f = by_env["heltecv3demo"]
    assert f["board_id"] == "heltec_wifi_kit_32_V3"
    assert f["platform"]["spec"] == PIOARDUINO_37
    assert f["platform"]["manifest_digest"] == cp.sha256(manifest("heltec_wifi_kit_32_V3"))
    assert any(s["name"] == "env:heltecv3demo" for s in f["sections"])
    assert all(s["line"] >= 1 for s in f["sections"])


def test_m5plusdemo_is_refused_its_variant_overrides_the_definition(nds):
    facts, refusals = cp.judge(nds, manifests_for)
    assert "m5plusdemo" not in {f["env"] for f in facts}
    assert any(r["env"] == "m5plusdemo" and r["rule"] == "identity-override" for r in refusals)


def project(tmp_path, ini, extra=None):
    (tmp_path / "platformio.ini").write_text(ini, encoding="utf-8")
    for name, text in (extra or {}).items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return cp.resolve_project(tmp_path)


def rules(resolved, env):
    _facts, refusals = cp.judge(resolved, manifests_for)
    return {r["rule"] for r in refusals if r["env"] == env}


def test_an_external_environment_variable_in_board_is_refused(tmp_path):
    r = project(tmp_path, f"[env:x]\nplatform = {PIOARDUINO_37}\nboard = heltec_wifi_kit_32_V3${{sysenv.SUFFIX}}\n")
    assert "external-input" in rules(r, "x")


def test_the_resolution_ignores_the_callers_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("SUFFIX", "_evil")
    monkeypatch.setenv("PLATFORMIO_DEFAULT_ENVS", "x")
    r = project(tmp_path, f"[env:x]\nplatform = {PIOARDUINO_37}\nboard = heltec_wifi_kit_32_V3${{sysenv.SUFFIX}}\n")
    assert r["envs"]["x"]["board"] == "heltec_wifi_kit_32_V3"


def test_two_loaded_files_setting_the_same_contributing_option_are_refused(tmp_path):
    ini = f"[platformio]\nextra_configs = extra_*.ini\n\n[base]\nplatform = {PIOARDUINO_37}\n\n[env:x]\nextends = base\n"
    r = project(tmp_path, ini, {"extra_a.ini": "[base]\nboard = heltec_wifi_kit_32_V3\n",
                                "extra_b.ini": "[base]\nboard = m5stick-c\n"})
    assert "order-dependent" in rules(r, "x")


def test_a_floating_or_unknown_platform_is_refused(tmp_path):
    r = project(tmp_path, "[env:a]\nplatform = espressif32\nboard = heltec_wifi_kit_32_V3\n\n"
                          "[env:b]\nplatform = native\n\n[env:c]\nplatform = https://github.com/someone/fork/releases/download/1/p.zip\nboard = heltec_wifi_kit_32_V3\n")
    assert "platform-not-pinned" in rules(r, "a")
    assert rules(r, "b") & {"platform-not-allowed", "no-board"}
    assert "platform-not-allowed" in rules(r, "c")


def test_a_local_board_definition_shadowing_the_packaged_one_is_refused(tmp_path):
    r = project(tmp_path, f"[env:x]\nplatform = {PIOARDUINO_37}\nboard = heltec_wifi_kit_32_V3\n",
                {"boards/heltec_wifi_kit_32_V3.json": json.dumps({"name": "fake"})})
    assert "shadowed-definition" in rules(r, "x")


def test_a_board_the_platform_does_not_define_is_refused(tmp_path):
    r = project(tmp_path, f"[env:x]\nplatform = {PIOARDUINO_37}\nboard = no_such_board\n")
    assert "unknown-definition" in rules(r, "x")


def test_a_template_env_without_platform_is_refused(tmp_path):
    r = project(tmp_path, "[env:x]\nboard = heltec_wifi_kit_32_V3\n")
    assert rules(r, "x") & {"no-platform"}


def test_ci_and_the_reviewer_install_the_pinned_platformio():
    """Both must be able to run this file (2026-11-22: #1993 was BLOCKed when the reviewer lacked a dependency)."""
    root = Path(__file__).resolve().parent.parent
    assert "platformio==6.2.0" in (root / "jr" / "requirements-claims.txt").read_text()
    for wf in ("validate.yml", "agent-review.yml"):
        assert "pip install -r jr/requirements-claims.txt" in (root / ".github" / "workflows" / wf).read_text(), wf
