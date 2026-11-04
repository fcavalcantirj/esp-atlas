"""jr/image_sandbox.py FAILS CLOSED (owner spec 2026-11-04): when bwrap is missing, or cannot build
the sandbox (user namespaces refused — the stock GitHub ubuntu runner), the answer is needs_review
with reason sandbox_unavailable and the parser never runs, sandboxed or not.

These tests are not `sandbox`-marked: they run on every host, so a CI runner without bwrap still
proves the path it actually takes."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import device_evidence as dev
import esp_image
import fake_https
import image_sandbox as sb
from test_device_evidence_fetch import gate, why

VALID = (Path(__file__).resolve().parent / "fixtures" / "esp_image" / "app_esp32s3.bin").read_bytes()
NO_NAMESPACE = ("bwrap: No permissions to create a new namespace, likely because the kernel does not allow "
                "non-privileged user namespaces.")


@pytest.fixture
def started(monkeypatch):
    """Every command run_isolated starts (each still runs)."""
    calls = []
    real = subprocess.run

    def record(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return real(cmd, *args, **kwargs)

    monkeypatch.setattr(sb.subprocess, "run", record)
    return calls


@pytest.fixture
def refusing_bwrap(tmp_path, monkeypatch) -> Path:
    """A bwrap that fails the way a host refusing unprivileged user namespaces makes the real one fail."""
    fake = tmp_path / "bwrap"
    fake.write_text(f"#!/bin/sh\necho '{NO_NAMESPACE}' >&2\nexit 1\n")
    fake.chmod(0o755)
    monkeypatch.setattr(sb, "BWRAP", fake)
    return fake


def _sandbox_unavailable(got) -> bool:
    return got["status"] == esp_image.NEEDS_REVIEW and got["chip"] is None \
        and any(sb.SANDBOX_UNAVAILABLE in r for r in got["reasons"])


def test_without_bwrap_a_valid_image_is_needs_review_and_nothing_is_started(monkeypatch, started):
    monkeypatch.setattr(sb, "BWRAP", Path("/nonexistent/bwrap"))
    got = sb.validate(VALID)
    assert _sandbox_unavailable(got) and "/nonexistent/bwrap not found" in got["reasons"][0], got
    assert started == []


def test_a_bwrap_refused_its_namespaces_is_sandbox_unavailable_and_only_bwrap_ran(refusing_bwrap, started):
    got = sb.validate(VALID)
    assert _sandbox_unavailable(got) and "No permissions to create a new namespace" in got["reasons"][0], got
    assert [cmd[0] for cmd in started] == [str(refusing_bwrap)]     # the interpreter only as bwrap's argument


def test_the_validator_is_bound_read_only_where_the_child_loads_it(refusing_bwrap, started):
    """What test_image_sandbox's write test proves at runtime for the module in the validator's slot,
    pinned here for esp_image.py itself: the child loads it from its real path, a --ro-bind covers that
    path in the sandbox, nothing is bound writable and the root is remounted read-only."""
    sb.validate(VALID)
    (cmd,) = started
    bwrap, child = cmd[:cmd.index("--")], cmd[cmd.index("--") + 1:]
    module = str(sb.ESP_IMAGE)
    assert child[child.index("-c") + 2] == module
    ro_binds = [(bwrap[i + 1], bwrap[i + 2]) for i, arg in enumerate(bwrap) if arg == "--ro-bind"]
    assert any(src == dest and (module == src or module.startswith(src + "/")) for src, dest in ro_binds), ro_binds
    assert not {"--bind", "--bind-try", "--tmpfs", "--file", "--bind-data"} & set(bwrap), bwrap
    assert [(bwrap[i + 1], bwrap[i + 2]) for i, arg in enumerate(bwrap) if arg == "--dev-bind"] == \
        [(dev, dev) for dev in sb.DEVICES], bwrap
    assert bwrap[-2:] == ["--remount-ro", "/"], bwrap


def test_a_bwrap_that_cannot_be_executed_is_sandbox_unavailable(tmp_path, monkeypatch):
    broken = tmp_path / "bwrap"
    broken.write_text("not a program")
    broken.chmod(0o644)
    monkeypatch.setattr(sb, "BWRAP", broken)
    got = sb.validate(VALID)
    assert _sandbox_unavailable(got) and "could not run" in got["reasons"][0], got


def test_unavailable_reason_names_the_refusal(refusing_bwrap):
    assert sb.unavailable_reason() == f"{sb.SANDBOX_UNAVAILABLE}: {NO_NAMESPACE}"


def test_a_child_failure_is_not_mistaken_for_an_unavailable_sandbox(tmp_path, monkeypatch):
    """Only bwrap's own refusal is sandbox_unavailable; this fake ran its child and the child crashed."""
    fake = tmp_path / "bwrap"
    fake.write_text("#!/bin/sh\necho 'Traceback: parser exploded' >&2\nexit 1\n")
    fake.chmod(0o755)
    monkeypatch.setattr(sb, "BWRAP", fake)
    got = sb.run_isolated(sb.ESP_IMAGE, "validate", VALID)
    assert got == {"ok": False, "why": "child exited with status 1: Traceback: parser exploded"}


def test_the_release_bin_gate_fails_closed_without_the_sandbox(https_server, refusing_bwrap):
    https_server.routes["/o/r/releases/download/v1/fw.bin"] = fake_https.exact(VALID)
    res = gate(https_server)
    assert res["verdict"] == dev.NEEDS_REVIEW and sb.SANDBOX_UNAVAILABLE in why(res), res


def test_this_host_either_sandboxes_the_validator_or_fails_closed():
    """No skip either way: on a host that cannot build the sandbox (CI), the real path is exercised."""
    unavailable = sb.unavailable_reason()
    got = sb.validate(VALID)
    if unavailable:
        assert _sandbox_unavailable(got), got
    else:
        assert got == esp_image.validate(VALID) and got["status"] == esp_image.ESP_TARGET


@pytest.mark.sandbox
def test_a_real_namespace_refusal_is_sandbox_unavailable(monkeypatch):
    """The real bwrap, made to fail creating its user namespace: an RLIMIT_NPROC of 1 set before exec
    (why the module sets NPROC inside the sandbox instead) is charged against the user's whole count."""
    hard_limits = sb._hard_limits

    def with_nproc(memory, cpu):
        apply = hard_limits(memory, cpu)

        def both():
            apply()
            sb.resource.setrlimit(sb.resource.RLIMIT_NPROC, (1, 1))
        return both

    monkeypatch.setattr(sb, "_hard_limits", with_nproc)
    got = sb.validate(VALID)
    assert _sandbox_unavailable(got) and "bwrap: " in got["reasons"][0], got
