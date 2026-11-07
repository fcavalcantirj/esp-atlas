"""Shared jr/ test fixtures."""
from __future__ import annotations

import os
import pwd
import shutil
import subprocess
from pathlib import Path

import pytest

import demand_closure
import derive
import device_evidence
import drain
import tick
import tools


@pytest.fixture(autouse=True)
def _no_live_popularity_state_or_gh(tmp_path, monkeypatch):
    """A forgotten injection in a Jr test must fail before touching the live bot.

    The hourly runner has a persistent state file and can open/arm a real PR. Keep
    every test's default state in its own tmp directory and reject an explicit
    live-state path or a real gh subprocess, including calls through default_gh.
    """
    import popularity_run

    # Resolve the account home independently of HOME: the suite may set HOME to
    # an empty sandbox, but a hard-coded path to the real state must still fail.
    live_state_root = (Path(pwd.getpwuid(os.getuid()).pw_dir) / ".local" / "state").resolve()
    test_state = tmp_path / "jr-popularity.json"
    monkeypatch.setenv("JR_POPULARITY_STATE_FILE", str(test_state))
    monkeypatch.setattr(popularity_run, "DEFAULT_STATE_FILE", test_state)
    monkeypatch.setenv("GH_CONFIG_DIR", str(tmp_path / "empty-gh-config"))
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    def check_state_path(path):
        resolved = Path(path).expanduser().resolve()
        if resolved == live_state_root or live_state_root in resolved.parents:
            raise AssertionError(f"Jr test attempted live state access: {resolved}")

    for name in ("_state_integrity", "_load_state", "_write_state"):
        original = getattr(popularity_run, name)

        def guarded_state(path, *args, _original=original, **kwargs):
            check_state_path(path)
            return _original(path, *args, **kwargs)

        monkeypatch.setattr(popularity_run, name, guarded_state)

    def is_gh(argv):
        executable = argv[0] if isinstance(argv, (list, tuple)) and argv else argv
        words = str(executable).split() if executable else []
        return bool(words) and Path(words[0]).name == "gh"

    original_run = subprocess.run
    original_popen = subprocess.Popen

    def guarded_run(argv, *args, **kwargs):
        if is_gh(argv):
            raise AssertionError("Jr test attempted real gh subprocess")
        return original_run(argv, *args, **kwargs)

    def guarded_popen(argv, *args, **kwargs):
        if is_gh(argv):
            raise AssertionError("Jr test attempted real gh subprocess")
        return original_popen(argv, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr(subprocess, "Popen", guarded_popen)


@pytest.fixture(autouse=True)
def _isolated_tick_lock(tmp_path, monkeypatch):
    """Every real-run tick under pytest takes its overlap lock in tmp_path, never the box's lock
    file: a test run must neither block nor be blocked by a live hourly tick on the same machine."""
    monkeypatch.setattr(tick, "DEFAULT_TICK_LOCK", tmp_path / "jr-tick-run.lock")


@pytest.fixture(autouse=True)
def _no_live_device_evidence(monkeypatch):
    """No jr test reaches GitHub. derive's default network effects raise (a test that forgets to
    inject `api`/`raw` sees its reads fail — derive._Calls turns that into an unreadable result,
    so the candidate is skipped, never fetched), and the drain's live device-build
    evidence check (jr/device_evidence.py) passes by default so the gates a drain test targets stay
    the only ones that bite; tests of that gate inject `evidence=` or patch it themselves. The
    gate's GET of a release asset is offline the same way, and so is the demand closure's live
    catalog search (demand_closure.default_fetch, the daily run's default getter)."""
    monkeypatch.setattr(demand_closure, "_urlopen", _offline)
    monkeypatch.setattr(derive, "default_api", _offline)
    monkeypatch.setattr(derive, "default_raw", _offline)
    monkeypatch.setattr(device_evidence, "default_fetch", _offline)
    monkeypatch.setattr(drain, "default_device_evidence",
                        lambda owner_repo, ref: {"ok": True, "verdict": device_evidence.ESP_TARGET, "kind": "arduino_sketch",
                                                 "url": None, "calls": 0, "notes": [], "ambiguous": []})


def _offline(*a, **k):
    raise RuntimeError("live network in a jr test: inject api/raw/head")


# The ESP fqbn `esp_sketch_raw` serves for every sketch.yaml.
ESP_SKETCH_YAML = "default_fqbn: esp32:esp32:m5stack_cardputer\n"


@pytest.fixture
def esp_sketch_raw(monkeypatch):
    """derive.default_raw (the stages' raw reader when a test passes none) serves every
    `sketch.yaml` as an ESP fqbn; any other read stays offline."""
    def raw(url):
        if url.endswith("/sketch.yaml"):
            return ESP_SKETCH_YAML
        return _offline(url)
    monkeypatch.setattr(derive, "default_raw", raw)


@pytest.fixture
def tmp_atlas(tmp_path, monkeypatch):
    """A throwaway copy of data/ that authoring writes into and the real guard validates — a test
    must never write into the real atlas (a killed run used to leave its fixture in data/).
    ESP_ATLAS_REPO_ROOT points the guard subprocess at the copy; scripts/, apps/ and schema/
    are read-only, so they're symlinked. Returns the copy's root."""
    repo = tools.REPO
    shutil.copytree(repo / "data", tmp_path / "data")
    for d in ("scripts", "apps", "schema"):
        (tmp_path / d).symlink_to(repo / d)
    monkeypatch.setenv("ESP_ATLAS_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(tools, "REPO", tmp_path)
    monkeypatch.setattr(tools, "FIRMWARE_DIR", tmp_path / "data" / "firmware")
    monkeypatch.setattr(tools, "BOARDS_DIR", tmp_path / "data" / "boards")
    monkeypatch.setattr(tools, "SOCS_DIR", tmp_path / "data" / "socs")
    monkeypatch.setattr(tools, "MODULES_DIR", tmp_path / "data" / "modules")
    return tmp_path


@pytest.fixture(scope="session")
def _test_cert(tmp_path_factory):
    import fake_https
    return fake_https.write_cert(tmp_path_factory.mktemp("tls"))


@pytest.fixture
def https_server(_test_cert):
    """A local HTTPS server (jr/fake_https.py) with fresh routes; `.seams()` reaches it."""
    import fake_https
    server = fake_https.Server(*_test_cert)
    yield server
    server.close()


def pytest_collection_modifyitems(config, items):
    """A `sandbox`-marked test needs jr/image_sandbox.py's real bwrap sandbox. On a host that cannot
    build it (no bwrap, user namespaces refused — the stock GitHub ubuntu runner) it is SKIPPED with
    that reason, never passed: `pytest -rs` lists every one. The fail-closed behaviour such a host
    must show is jr/test_image_sandbox_fail_closed.py, which is not marked and always runs."""
    marked = [item for item in items if item.get_closest_marker("sandbox")]
    if not marked:
        return
    import image_sandbox
    why = image_sandbox.unavailable_reason()
    if why:
        skip = pytest.mark.skip(reason=f"needs the bwrap image sandbox, unavailable on this host: {why}")
        for item in marked:
            item.add_marker(skip)

