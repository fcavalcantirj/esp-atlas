"""Tests for jr/image_sandbox.py — jr/esp_image.validate run in a restricted child process.

Owner spec 2026-11-04: the parser reads bytes a stranger chose, so it runs in a fresh `python -I`
with an empty environment (no tokens), the asset on stdin only, CPU / wall-clock / memory limits,
no network (socket patched before esptool is imported) and no serial port. The parent turns a
crash, a timeout or output that is not the validator's JSON into needs_review, never esp_target.
Each probe below is a tiny module the child runs in place of esp_image.validate.

Every test here needs the real bwrap sandbox: the `sandbox` mark makes jr/conftest.py skip them, with
the reason, on a host that cannot build it. What such a host must do instead (fail closed) is
jr/test_image_sandbox_fail_closed.py, which always runs."""
from __future__ import annotations

import hashlib
import os
import textwrap
import time
from pathlib import Path

import pytest

import esp_image
import image_sandbox as sb

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "esp_image"
IMAGES = sorted(FIXTURES.glob("*.bin")) + sorted((FIXTURES / "real").glob("*.bin"))

pytestmark = pytest.mark.sandbox


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


# --- checker findings 2026-11-04: what plain Python could still reach --------------------------------

def _all_refused(got):
    assert got["ok"], got
    assert got["value"] and all(v.startswith("PermissionError") for v in got["value"].values()), got["value"]


def test_a_child_cannot_reach_libc_through_ctypes(tmp_path):
    got = run(tmp_path, """
        out = {}
        for name, attempt in {"import+CDLL": lambda: __import__("ctypes").CDLL(None),
                              "libc.socket": lambda: __import__("ctypes").CDLL(None).socket(2, 1, 0)}.items():
            try:
                attempt()
                out[name] = "reached"
            except Exception as e:
                out[name] = type(e).__name__ + ": " + str(e)
        return out
    """)
    _all_refused(got)


def test_a_child_cannot_change_existing_files(tmp_path, tmp_path_factory):
    victim = tmp_path_factory.mktemp("victim") / "keep.txt"
    victim.write_text("precious")
    got = run(tmp_path, f"""
        import os
        p = {str(victim)!r}
        out = {{}}
        for name, attempt in {{"remove": lambda: os.remove(p), "rename": lambda: os.rename(p, p + ".x"),
                               "truncate": lambda: os.truncate(p, 0), "chmod": lambda: os.chmod(p, 0o777),
                               "symlink": lambda: os.symlink(p, p + ".lnk"), "mkdir": lambda: os.mkdir(p + ".d"),
                               "utime": lambda: os.utime(p, (0, 0))}}.items():
            try:
                attempt()
                out[name] = "done"
            except Exception as e:
                out[name] = type(e).__name__ + ": " + str(e)
        return out
    """)
    _all_refused(got)
    assert victim.read_text() == "precious" and sorted(p.name for p in victim.parent.iterdir()) == ["keep.txt"]


def test_a_child_cannot_signal_other_processes(tmp_path):
    got = run(tmp_path, """
        import os, signal
        out = {}
        for name, attempt in {"kill parent (signal 0)": lambda: os.kill(os.getppid(), 0),
                              "killpg": lambda: os.killpg(os.getpgid(0), 0),
                              "pthread_kill": lambda: signal.pthread_kill(__import__("threading").main_thread().ident, 0)}.items():
            try:
                attempt()
                out[name] = "sent"
            except Exception as e:
                out[name] = type(e).__name__ + ": " + str(e)
        return out
    """)
    _all_refused(got)


def test_a_child_cannot_read_credentials_outside_the_interpreter_and_its_module(tmp_path, tmp_path_factory, monkeypatch):
    """Not the parent's environment through /proc, not a token file elsewhere on disk, not a listing."""
    monkeypatch.setenv("GH_TOKEN", "ghp_secret_for_the_test")
    secret = tmp_path_factory.mktemp("config") / "hosts.yml"
    secret.write_text("oauth_token: ghp_secret_for_the_test\n")
    got = run(tmp_path, f"""
        import os
        out = {{}}
        for name, attempt in {{"parent environ": lambda: open(f"/proc/{{os.getppid()}}/environ", "rb").read(),
                               "token file": lambda: open({str(secret)!r}).read(),
                               "os.open": lambda: os.open({str(secret)!r}, os.O_RDONLY),
                               "listdir": lambda: os.listdir({str(secret.parent)!r}),
                               "scandir": lambda: list(os.scandir("/home"))}}.items():
            try:
                out[name] = "read: " + str(attempt())[:40]
            except Exception as e:
                out[name] = type(e).__name__ + ": " + str(e)
        return out
    """)
    _all_refused(got)
    assert "ghp_secret" not in str(got)


def test_a_child_cannot_raise_its_own_limits(tmp_path):
    got = run(tmp_path, """
        import resource
        try:
            resource.setrlimit(resource.RLIMIT_CPU, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))
            return {"setrlimit": "raised"}
        except Exception as e:
            return {"setrlimit": type(e).__name__ + ": " + str(e)}
    """)
    _all_refused(got)


def test_the_child_can_still_import_the_library_it_needs(tmp_path):
    got = run(tmp_path, "import json, hashlib, struct, esptool\nfrom esptool import bin_image\nreturn esptool.__version__")
    assert got == {"ok": True, "value": esp_image.PINNED_ESPTOOL}


# --- the OS layer alone: guard=False drops the Python-level guard, the jail must still hold ---------

def bare(tmp_path, body, data=b"", **limits):
    return sb.run_isolated(probe(tmp_path, body), "run", data, guard=False, **limits)


ATTEMPT = """
out = {}
for name, attempt in ATTEMPTS.items():
    try:
        out[name] = "done: " + str(attempt())[:60]
    except Exception as e:
        out[name] = type(e).__name__ + ": " + str(e)
return out
"""


def attempts(tmp_path, attempts_src: str, **kw):
    got = bare(tmp_path, "import os, socket, signal, resource\nATTEMPTS = " + attempts_src + ATTEMPT, **kw)
    assert got["ok"], got
    return got["value"]


def test_without_the_guard_the_network_is_unreachable(tmp_path):
    out = attempts(tmp_path, """{"tcp": lambda: socket.create_connection(("93.184.215.14", 443), 1),
                                 "dns": lambda: socket.getaddrinfo("github.com", 443)}""")
    assert out["tcp"].startswith("OSError: [Errno 101]") and out["dns"].startswith("gaierror"), out


def test_without_the_guard_no_host_file_is_there_to_read(tmp_path, tmp_path_factory, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "ghp_secret_for_the_test")
    secret = tmp_path_factory.mktemp("config") / "hosts.yml"
    secret.write_text("oauth_token: ghp_secret_for_the_test\n")
    out = attempts(tmp_path, f"""{{"token file": lambda: open({str(secret)!r}).read(),
                                   "passwd": lambda: open("/etc/passwd").read(),
                                   "parent environ": lambda: open("/proc/1/environ", "rb").read(),
                                   "repo": lambda: open({str(Path(sb.__file__).with_name("tick.py"))!r}).read(),
                                   "list /": lambda: os.listdir("/"), "list /home": lambda: os.listdir("/home"),
                                   "environ": lambda: sorted(os.environ)}}""")
    assert out["token file"].startswith("FileNotFoundError") and out["parent environ"].startswith("FileNotFoundError"), out
    assert out["repo"].startswith("FileNotFoundError"), out
    assert out["passwd"] == "done: validator:x:%d:%d::/nonexistent:/nonexistent\n" % (os.getuid(), os.getgid()), out
    assert out["list /"].startswith("PermissionError") and out["list /home"].startswith("PermissionError"), out
    assert out["environ"] == "done: ['LC_CTYPE']" and "ghp_secret" not in str(out), out


def test_without_the_guard_nothing_can_be_written_or_changed(tmp_path, tmp_path_factory):
    victim = tmp_path_factory.mktemp("victim") / "keep.txt"
    victim.write_text("precious")
    module = str(Path(sb.ESP_IMAGE))
    out = attempts(tmp_path, f"""{{"new file at /": lambda: open("/x", "w"),
                                   "victim": lambda: os.remove({str(victim)!r}),
                                   "the bound validator": lambda: open({module!r}, "a"),
                                   "rename in the interpreter": lambda: os.rename(os.__file__, os.__file__ + ".x"),
                                   "fifo": lambda: os.mkfifo("/fifo")}}""")
    assert out["victim"].startswith("FileNotFoundError"), out
    for name in ("new file at /", "the bound validator", "rename in the interpreter", "fifo"):
        assert out[name].startswith("OSError: [Errno 30] Read-only file system"), out
    assert victim.read_text() == "precious"


def test_without_the_guard_no_serial_device_exists(tmp_path):
    out = attempts(tmp_path, """{dev: (lambda d=dev: open(d, "rb")) for dev in
                                 ("/dev/ttyUSB0", "/dev/ttyACM0", "/dev/ttyS0", "/dev/mem", "/dev/tty")}""")
    assert all(v.startswith("FileNotFoundError") for v in out.values()), out


def test_without_the_guard_processes_outside_the_sandbox_are_invisible(tmp_path):
    out = attempts(tmp_path, f"""{{"the test runner": lambda: os.kill({os.getpid()}, 0),
                                   "own pid": lambda: os.getpid()}}""")
    assert out["the test runner"].startswith("ProcessLookupError") and out["own pid"] == "done: 2", out


def test_without_the_guard_the_child_cannot_start_a_process(tmp_path):
    out = attempts(tmp_path, """{"fork": os.fork, "exec a shell": lambda: os.execv("/bin/sh", ["sh"])}""")
    assert out["fork"].startswith("BlockingIOError"), out           # RLIMIT_NPROC 0
    assert out["exec a shell"].startswith("FileNotFoundError"), out  # no /bin, no /usr/bin in the root


def test_without_the_guard_the_hard_limits_cannot_be_raised(tmp_path):
    out = attempts(tmp_path, """{name: (lambda r=r: resource.setrlimit(r, (resource.RLIM_INFINITY,) * 2))
                                 for name, r in {"cpu": resource.RLIMIT_CPU, "as": resource.RLIMIT_AS,
                                                 "nofile": resource.RLIMIT_NOFILE, "fsize": resource.RLIMIT_FSIZE,
                                                 "nproc": resource.RLIMIT_NPROC}.items()}""")
    assert all("not allowed to raise maximum limit" in v for v in out.values()), out


def test_without_the_guard_the_hard_limits_are_the_ones_set(tmp_path):
    out = attempts(tmp_path, """{name: (lambda r=r: resource.getrlimit(r)[1])
                                 for name, r in {"cpu": resource.RLIMIT_CPU, "as": resource.RLIMIT_AS,
                                                 "nofile": resource.RLIMIT_NOFILE, "fsize": resource.RLIMIT_FSIZE,
                                                 "core": resource.RLIMIT_CORE, "nproc": resource.RLIMIT_NPROC}.items()}""",
                   cpu_seconds=7, memory_bytes=300 * 1024 * 1024)
    assert out == {"cpu": "done: 8", "as": f"done: {300 * 1024 * 1024}", "nofile": f"done: {sb.OPEN_FILES}",
                   "fsize": "done: 0", "core": "done: 0", "nproc": "done: 0"}, out


def test_without_the_guard_the_validator_still_agrees(tmp_path):
    data = (FIXTURES / "app_esp32s3.bin").read_bytes()
    got = sb.run_isolated(sb.ESP_IMAGE, "validate", data, guard=False)
    assert got == {"ok": True, "value": esp_image.validate(data)}
