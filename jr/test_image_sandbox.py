"""Tests for jr/image_sandbox.py — jr/esp_image.validate run in a restricted child process.

Owner spec 2026-11-04: the parser reads bytes a stranger chose, so it runs in a fresh `python -I`
with an empty environment (no tokens), the asset on stdin only, CPU / wall-clock / memory limits,
no network (socket patched before esptool is imported) and no serial port. The parent turns a
crash, a timeout or output that is not the validator's JSON into needs_review, never esp_target.
Each probe below is a tiny module the child runs in place of esp_image.validate."""
from __future__ import annotations

import hashlib
import textwrap
import time
from pathlib import Path

import pytest

import esp_image
import image_sandbox as sb

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "esp_image"
IMAGES = sorted(FIXTURES.glob("*.bin")) + sorted((FIXTURES / "real").glob("*.bin"))


def probe(tmp_path, body: str, name="probe") -> Path:
    """A module whose `run(data)` is `body` (the child calls it with the stdin bytes)."""
    path = tmp_path / f"{name}.py"
    path.write_text("def run(data):\n" + textwrap.indent(textwrap.dedent(body), "    "))
    return path


def run(tmp_path, body, data=b"", **limits):
    return sb.run_isolated(probe(tmp_path, body), "run", data, **limits)


# --- the real validator, isolated --------------------------------------------------------------------

@pytest.mark.parametrize("image", IMAGES, ids=lambda p: p.name)
def test_the_isolated_validator_agrees_with_the_in_process_one(image):
    data = image.read_bytes()
    assert sb.validate(data) == esp_image.validate(data)


def test_a_valid_image_is_esp_target_through_the_sandbox():
    got = sb.validate((FIXTURES / "app_esp32s3.bin").read_bytes())
    assert got["status"] == esp_image.ESP_TARGET and got["chip"] == "esp32s3"


# --- what the child cannot do --------------------------------------------------------------------------

def test_a_child_that_tries_to_open_a_socket_fails(tmp_path):
    got = run(tmp_path, """
        import socket, _socket
        out = {}
        attempts = {
            "socket.socket": lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM),
            "_socket.socket": lambda: _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM),
            "create_connection": lambda: socket.create_connection(("93.184.215.14", 443), 1),
            "getaddrinfo": lambda: socket.getaddrinfo("github.com", 443),
            "_socket.getaddrinfo": lambda: _socket.getaddrinfo("github.com", 443),
            "socketpair": lambda: socket.socketpair(),
            "unix": lambda: socket.socket(socket.AF_UNIX),
            "the original class": lambda: socket.socket.__mro__[-2](socket.AF_INET, socket.SOCK_STREAM),
        }
        for name, attempt in attempts.items():
            try:
                attempt()
                out[name] = "opened"
            except Exception as e:
                out[name] = type(e).__name__ + ": " + str(e)
        return out
    """)
    assert got["ok"], got
    assert got["value"] and all("network is disabled" in v for v in got["value"].values()), got["value"]


def test_the_socket_module_is_patched_before_esptool_is_imported(tmp_path):
    """esptool (and pyserial's rfc2217/socket:// handlers) bind `socket` at import: they must see
    the patched one."""
    got = run(tmp_path, """
        import esptool, serial.rfc2217, socket
        try:
            serial.serial_for_url("socket://93.184.215.14:443")
            return "opened"
        except Exception as e:
            return type(e).__name__ + ": " + str(e)
    """)
    assert got["ok"] and "disabled" in got["value"], got


def test_a_child_cannot_open_a_serial_port(tmp_path):
    got = run(tmp_path, """
        out = {}
        for dev in ("/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyS0"):
            try:
                open(dev, "rb")
                out[dev] = "opened"
            except Exception as e:
                out[dev] = type(e).__name__ + ": " + str(e)
        try:
            import serial
            serial.Serial("/dev/ttyACM0")
            out["pyserial"] = "opened"
        except Exception as e:
            out["pyserial"] = type(e).__name__ + ": " + str(e)
        return out
    """)
    assert got["ok"], got
    assert all("device files are disabled" in v for v in got["value"].values()), got["value"]   # pyserial rewraps it


def test_a_child_sees_none_of_the_parent_s_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_secret_for_the_test")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_secret_for_the_test")
    got = run(tmp_path, "import os\nreturn dict(os.environ)")
    assert got["ok"] and set(got["value"]) <= {"LC_CTYPE"}, got


def test_a_child_cannot_start_a_process(tmp_path):
    got = run(tmp_path, """
        import os, subprocess
        out = {}
        for name, attempt in {"subprocess": lambda: subprocess.run(["true"]), "system": lambda: os.system("true"),
                              "fork": os.fork, "exec": lambda: os.execv("/bin/true", ["true"])}.items():
            try:
                attempt()
                out[name] = "ran"
            except Exception as e:
                out[name] = type(e).__name__ + ": " + str(e)
        return out
    """)
    assert got["ok"] and all(v.startswith("PermissionError") for v in got["value"].values()), got


def test_a_child_cannot_write_files(tmp_path):
    target = tmp_path / "written.txt"
    got = run(tmp_path, f"""
        try:
            open({str(target)!r}, "w").write("x")
            return "wrote"
        except Exception as e:
            return type(e).__name__ + ": " + str(e)
    """)
    assert got["ok"] and got["value"].startswith("PermissionError") and not target.exists(), got


def test_the_asset_reaches_the_child_on_stdin_only(tmp_path):
    data = bytes(range(256)) * 1000
    got = run(tmp_path, "import hashlib\nreturn [len(data), hashlib.sha256(data).hexdigest()]", data)
    assert got["ok"] and got["value"] == [len(data), hashlib.sha256(data).hexdigest()]


# --- limits and failure mapping ---------------------------------------------------------------------

def test_a_crashing_child_is_a_failure_with_its_error(tmp_path):
    got = run(tmp_path, "raise RuntimeError('parser exploded')")
    assert not got["ok"] and "exit" in got["why"] and "parser exploded" in got["why"]


def test_a_child_over_the_wall_clock_is_killed(tmp_path):
    t0 = time.monotonic()
    got = run(tmp_path, "import time\ntime.sleep(30)", wall_timeout=1.0)
    assert not got["ok"] and "wall" in got["why"] and time.monotonic() - t0 < 5


def test_a_child_over_the_cpu_limit_is_killed(tmp_path):
    t0 = time.monotonic()
    got = run(tmp_path, "while True:\n    pass", cpu_seconds=1, wall_timeout=20.0)
    assert not got["ok"] and "SIGXCPU" in got["why"] and time.monotonic() - t0 < 10


def test_a_child_over_the_memory_limit_fails(tmp_path):
    got = run(tmp_path, "return len(bytearray(1024 * 1024 * 1024))", memory_bytes=256 * 1024 * 1024)
    assert not got["ok"] and "MemoryError" in got["why"]


def test_non_json_output_is_a_failure(tmp_path):
    got = run(tmp_path, "print('esp_target, trust me')\nreturn {}")
    assert not got["ok"] and "not JSON" in got["why"]


@pytest.mark.parametrize("body,why", [("raise SystemExit(3)", "exit"), ("import time\ntime.sleep(30)", "wall"),
                                      ("print('garbage')\nreturn {}", "not JSON"),
                                      ("return {'status': 'esp_target', 'chip': None, 'reasons': ['x']}", "malformed"),
                                      ("return {'status': 'esp_target', 'chip': 'esp32', 'reasons': 'x'}", "malformed"),
                                      ("return {'status': 'ok', 'chip': 'esp32', 'reasons': ['x']}", "malformed"),
                                      ("return ['esp_target']", "malformed")])
def test_validate_maps_every_child_failure_to_needs_review(tmp_path, body, why):
    got = sb.validate(b"\xe9" * 64, module=probe(tmp_path, body), func="run", wall_timeout=1.0)
    assert got["status"] == esp_image.NEEDS_REVIEW and got["chip"] is None
    assert any(why in r for r in got["reasons"]), got


def test_validate_passes_a_well_formed_esp_target_through(tmp_path):
    body = "return {'status': 'esp_target', 'chip': 'esp32s3', 'reasons': ['esp32s3 image: verified']}"
    got = sb.validate(b"", module=probe(tmp_path, body), func="run")
    assert got == {"status": "esp_target", "chip": "esp32s3", "reasons": ["esp32s3 image: verified"]}


def test_a_child_that_cannot_start_is_a_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(sb.sys, "executable", str(tmp_path / "no-python-here"))
    got = sb.validate(b"")
    assert got["status"] == esp_image.NEEDS_REVIEW and "could not start" in got["reasons"][0]
