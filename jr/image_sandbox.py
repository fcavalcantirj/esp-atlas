"""EspAtlas Jr — jr/esp_image.validate in a restricted child process (jr/image_sandbox.py).

The release asset device_evidence downloads was chosen by a stranger, and the pinned esptool
parser reading it is a large dependency tree. Owner spec 2026-11-04: parse in a restricted process
— no credentials, no network, no serial. validate(data) runs esp_image.validate in

  a fresh interpreter   `sys.executable -I -B`: no PYTHON* variables, no user site, no cwd on
                        sys.path, no bytecode written; cwd is /
  an empty environment  env={} — no GH_TOKEN, no API keys (Python itself adds only LC_CTYPE)
  stdin only            the asset arrives on stdin; the result leaves as one JSON document
  hard limits           RLIMIT_CPU (SIGXCPU), RLIMIT_AS (MemoryError), RLIMIT_FSIZE 0, no core,
                        and a wall-clock timeout after which the parent kills it
  no network            `socket`/`_socket` patched BEFORE esptool is imported (socket(),
                        socketpair, create_connection, getaddrinfo... raise), and an audit hook
                        refusing every `socket.*` event underneath, so a saved reference to the
                        original class is refused too
  no serial, no I/O     the same hook refuses opening any device node (anything under /dev but
                        null/random/urandom, or any char/block device reached by a symlink), any
                        file write, and starting a process (subprocess, system, fork, exec, spawn)

An audit hook cannot be removed once added (PEP 578). It is a guard against the parser's own code
paths, not a jail against native code: there is no seccomp/namespace here.

The parent maps a crash, a signal, a timeout, output that is not JSON, or JSON that is not a
well-formed validator result to needs_review — never esp_target. A well-formed result passes
through unchanged. `run_isolated` is the generic runner the tests drive with probe modules.
"""
from __future__ import annotations

import json
import signal
import subprocess
import sys
from pathlib import Path

import esp_image

ESP_IMAGE = Path(__file__).resolve().with_name("esp_image.py")
WALL_TIMEOUT = 60.0             # seconds: a 16 MB image validates in well under 2 s on the Pi
CPU_SECONDS = 30
MEMORY_BYTES = 512 * 1024 * 1024    # address space; the child peaks near 75 MB of it on a 16 MB asset

# The child's whole program, passed with -c so nothing on disk but the validated module is loaded
# from outside the interpreter's own library. argv: module path, function, memory bytes, cpu seconds.
_CHILD = r'''
import os
import stat
import sys

NO_NET = "network is disabled in the image validator sandbox"
NO_PROC = "starting a process is disabled in the image validator sandbox"
_NO_PROCESS = {"subprocess.Popen", "os.system", "os.fork", "os.forkpty", "os.exec", "os.posix_spawn",
               "os.spawn", "pty.spawn"}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_HARMLESS_DEVICES = {"/dev/null", "/dev/random", "/dev/urandom"}


def _limits(memory, cpu):
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def _deny(*args, **kwargs):
    raise PermissionError(NO_NET)


def _patch_socket():
    import _socket
    import socket

    class NoSocket(socket.socket):
        def __init__(self, *args, **kwargs):
            raise PermissionError(NO_NET)

    for module in (socket, _socket):
        module.socket = NoSocket
        for name in ("socketpair", "fromfd", "create_connection", "create_server", "getaddrinfo",
                     "gethostbyname", "gethostbyname_ex", "gethostbyaddr", "getnameinfo"):
            if hasattr(module, name):
                setattr(module, name, _deny)


def _is_device(path):
    real = os.path.realpath(os.fsdecode(path))
    if real in _HARMLESS_DEVICES:
        return False
    if real.startswith("/dev/"):
        return True
    try:
        mode = os.stat(real).st_mode
    except OSError:
        return False
    return stat.S_ISCHR(mode) or stat.S_ISBLK(mode)


def _check_open(path, mode=None, flags=None):
    if isinstance(path, (str, bytes)) and _is_device(path):
        raise PermissionError(f"serial and device files are disabled in the image validator sandbox: {path!r}")
    writes = flags & _WRITE_FLAGS if isinstance(flags, int) else any(c in (mode or "") for c in "wax+")
    if writes:
        raise PermissionError(f"file writes are disabled in the image validator sandbox: {path!r}")


def _hook(event, args):
    if event.startswith("socket."):
        raise PermissionError(NO_NET)
    if event in _NO_PROCESS:
        raise PermissionError(NO_PROC)
    if event == "open":
        _check_open(*args[:3])


def main():
    path, func, memory, cpu = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
    _limits(memory, cpu)
    _patch_socket()                 # before anything imports esptool or pyserial
    sys.addaudithook(_hook)
    data = sys.stdin.buffer.read()
    import importlib.util
    import json
    spec = importlib.util.spec_from_file_location("sandboxed_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.stdout.write(json.dumps(getattr(module, func)(data)))


main()
'''


def run_isolated(module_path: Path, func: str, data: bytes, *, wall_timeout: float = WALL_TIMEOUT,
                 cpu_seconds: int = CPU_SECONDS, memory_bytes: int = MEMORY_BYTES) -> dict:
    """{"ok": True, "value": <the JSON `func(data)` returned>} or {"ok": False, "why": str} for
    `module_path`'s `func` run on `data` in the restricted child."""
    cmd = [sys.executable, "-I", "-B", "-c", _CHILD, str(module_path), func, str(memory_bytes), str(cpu_seconds)]
    try:
        proc = subprocess.run(cmd, input=bytes(data), capture_output=True, env={}, cwd="/", timeout=wall_timeout)
    except subprocess.TimeoutExpired:
        return _failed(f"killed after the {wall_timeout:g} s wall-clock timeout")
    except OSError as e:
        return _failed(f"could not start the child: {e}")
    if proc.returncode != 0:
        return _failed(f"child {_exit(proc.returncode)}: {_last_line(proc.stderr)}")
    try:
        return {"ok": True, "value": json.loads(proc.stdout)}
    except ValueError:
        return _failed(f"child output is not JSON: {proc.stdout[:120]!r}")


def validate(data: bytes, *, module: Path | None = None, func: str = "validate", **limits) -> dict:
    """esp_image.validate(data)'s result, computed in the restricted child; any failure of the
    child, or a result not shaped like the validator's, is needs_review with the reason."""
    run = run_isolated(module or ESP_IMAGE, func, data, **limits)
    if not run["ok"]:
        return _review(run["why"])
    result = run["value"]
    if not _well_formed(result):
        return _review(f"malformed validator result: {json.dumps(result)[:160]}")
    return result


def _well_formed(result) -> bool:
    if not (isinstance(result, dict) and set(result) == {"status", "chip", "reasons"}):
        return False
    reasons_ok = isinstance(result["reasons"], list) and bool(result["reasons"]) \
        and all(isinstance(r, str) for r in result["reasons"])
    if result["status"] == esp_image.ESP_TARGET:
        return reasons_ok and isinstance(result["chip"], str) and bool(result["chip"])
    return reasons_ok and result["status"] == esp_image.NEEDS_REVIEW and result["chip"] is None


def _review(why: str) -> dict:
    return {"status": esp_image.NEEDS_REVIEW, "chip": None, "reasons": [f"image validator sandbox: {why}"]}


def _failed(why: str) -> dict:
    return {"ok": False, "why": why}


def _exit(code: int) -> str:
    if code < 0:
        try:
            return f"killed by {signal.Signals(-code).name}"
        except ValueError:
            return f"killed by signal {-code}"
    return f"exited with status {code}"


def _last_line(stderr: bytes) -> str:
    lines = [ln for ln in stderr.decode("utf-8", "replace").splitlines() if ln.strip()]
    return lines[-1][:200] if lines else "no error output"
