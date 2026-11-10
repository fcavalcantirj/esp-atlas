"""Offline checks for Jr's hash-pinned runtime lock and the CI job that install-verifies it.

Nothing here touches the network: the live download/build/install run is the
`jr-lock-install` job (scripts/ci/jr_lock_install_check.sh). These tests pin the inputs
and the wiring so that job can't silently drift into checking less than it claims.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
LOCK_DIR = ROOT / "jr" / "runtime-lock"
RUNTIME_IN = LOCK_DIR / "runtime.in"
RUNTIME_LOCK = LOCK_DIR / "runtime-cp312-x86_64.lock"
BUILD_LOCK = LOCK_DIR / "build-constraints.lock"
WORKFLOW = ROOT / ".github" / "workflows" / "validate.yml"
SCRIPT = ROOT / "scripts" / "ci" / "jr_lock_install_check.sh"
SCRIPT_REF = "scripts/ci/jr_lock_install_check.sh"

ESPTOOL_SDIST_SHA256 = "86c7249e9cc3a824e032ede9ba20abad057a2c49e231418cc4f02b177bb36f42"
REQ_LINE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==(\S+)")
HASH = re.compile(r"--hash=sha256:([0-9a-f]{64})\b")


def _canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _requirements(lock: Path) -> dict[str, list[str]]:
    """{canonical name: [sha256, ...]} -- an independent parser, deliberately not the helper's."""
    reqs: dict[str, list[str]] = {}
    current = None
    for line in lock.read_text().splitlines():
        match = REQ_LINE.match(line)
        if match:
            current = _canonical(match.group(1))
            assert current not in reqs, f"{current} pinned twice"
            reqs[current] = []
        if current is not None:
            reqs[current].extend(HASH.findall(line))
    return reqs


def _runtime_in_names() -> set[str]:
    names = set()
    for line in RUNTIME_IN.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            names.add(_canonical(re.split(r"[=<>!~ ;\[]", line, maxsplit=1)[0]))
    return names


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]


def test_lock_pins_exactly_the_31_packages_named_in_runtime_in():
    names = _runtime_in_names()
    assert len(names) == 31
    assert set(_requirements(RUNTIME_LOCK)) == names


def test_every_runtime_requirement_carries_at_least_one_sha256():
    unhashed = [name for name, hashes in _requirements(RUNTIME_LOCK).items() if not hashes]
    assert unhashed == []


def test_esptool_is_pinned_to_its_sdist_hash_only():
    assert _requirements(RUNTIME_LOCK)["esptool"] == [ESPTOOL_SDIST_SHA256]


def test_build_constraints_pin_only_hashed_setuptools():
    reqs = _requirements(BUILD_LOCK)
    assert list(reqs) == ["setuptools"]
    assert reqs["setuptools"], "setuptools must be hash-pinned"


def test_lock_install_job_exists_on_ubuntu_with_python_312_and_runs_only_the_script():
    job = _jobs()["jr-lock-install"]
    assert job["runs-on"] == "ubuntu-latest"
    assert "env" not in job
    steps = job["steps"]
    setup = [s for s in steps if str(s.get("uses", "")).startswith("actions/setup-python")]
    assert len(setup) == 1 and str(setup[0]["with"]["python-version"]) == "3.12"
    runs = [s["run"] for s in steps if "run" in s]
    assert len(runs) == 1 and SCRIPT_REF in runs[0]
    assert all("env" not in s for s in steps)
    assert "secrets." not in yaml.safe_dump(job)
    for loosener in ("if", "continue-on-error"):
        assert loosener not in job and all(loosener not in s for s in steps)


def test_script_is_strict_bash():
    text = SCRIPT.read_text()
    assert text.startswith("#!/usr/bin/env bash")
    assert "set -euo pipefail" in text


def test_script_final_install_is_offline_and_hash_required():
    install = [
        line for line in _logical_lines(SCRIPT.read_text())
        if "install" in line and "$DERIVED_LOCK" in line and "$WHEELHOUSE" in line
    ]
    assert install, "final install against the derived lock + wheelhouse not found"
    for line in install:
        for flag in ("--require-hashes", "--no-index", "--only-binary :all:", "--find-links"):
            assert flag in line, f"{flag} missing from: {line}"


def test_script_builds_esptool_offline_without_build_isolation():
    wheel = [line for line in _logical_lines(SCRIPT.read_text()) if "-m pip wheel" in line]
    assert len(wheel) == 1
    for flag in ("--no-index", "--no-build-isolation", "--require-hashes", "--no-cache-dir"):
        assert flag in wheel[0], f"{flag} missing from: {wheel[0]}"


def test_script_runs_both_negative_installs():
    negatives = [line for line in _logical_lines(SCRIPT.read_text()) if line.startswith("expect_install_fails ")]
    targets = " ".join(negatives)
    assert len(negatives) == 2
    for target in ("$TAMPERED_LOCK", "$NO_ESPTOOL_WHEELHOUSE"):
        assert target in targets
    for line in negatives:
        assert "--require-hashes" in line and "--no-index" in line and "--only-binary :all:" in line


def test_the_missing_artifact_negative_removes_only_the_esptool_wheel():
    text = SCRIPT.read_text()
    assert 'cp "$WHEELHOUSE"/*.whl "$NO_ESPTOOL_WHEELHOUSE/"' in text
    assert 'rm -f "$NO_ESPTOOL_WHEELHOUSE"/esptool-*.whl' in text
    assert "No matching distribution found for esptool" in text


def test_final_and_negative_installs_bypass_the_cache():
    lines = _logical_lines(SCRIPT.read_text())
    final = [l for l in lines if "install" in l and "$DERIVED_LOCK" in l and "$RUN_VENV" in l]
    assert final and all("--no-cache-dir" in l for l in final)
    helper = [l for l in lines if l.strip().startswith('if "$venv/bin/python" -m pip install')]
    assert helper and all("--no-cache-dir" in l for l in helper)


def test_committed_locks_carry_no_absolute_paths():
    """uv records `-r <input>` provenance comments; they must stay repo-relative."""
    absolute = re.compile(r"(?m)(?:^|\s)(?:-r|-c)\s+/|(?:^|\s)/(?:home|srv|Users|root|tmp|var|opt)/")
    for lock in LOCK_DIR.glob("*"):
        assert not absolute.search(lock.read_text()), f"{lock.name} contains an absolute host path"


def test_script_never_weakens_hash_checking():
    text = SCRIPT.read_text()
    assert "--no-require-hashes" not in text
    assert "--trusted-host" not in text
    assert "--extra-index-url" not in text


def test_script_labels_itself_as_not_proof_of_the_pi_archive():
    assert "NOT proof of the Pi archive" in SCRIPT.read_text()


def _logical_lines(text: str) -> list[str]:
    """Join backslash-continued shell lines so one command reads as one string."""
    return text.replace("\\\n", " ").splitlines()


REQUIREMENTS_IMAGE = ROOT / "jr" / "requirements-image.txt"


def _pins(path: Path) -> dict[str, str]:
    pins: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        match = REQ_LINE.match(line)
        if match:
            pins[_canonical(match.group(1))] = match.group(2)
    return pins


def test_runtime_in_carries_every_pin_of_requirements_image_unchanged():
    """jr/requirements-image.txt is what the image checks install from; runtime.in is what the
    lock verifies. A bump in one without the other leaves CI proving a runtime nobody runs."""
    image, runtime = _pins(REQUIREMENTS_IMAGE), _pins(RUNTIME_IN)
    drift = {name: (ver, runtime.get(name)) for name, ver in image.items() if runtime.get(name) != ver}
    assert not drift, f"requirements-image.txt vs runtime.in (image, runtime.in): {drift}"
