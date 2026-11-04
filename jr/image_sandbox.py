"""EspAtlas Jr — jr/esp_image.validate in an OS-level sandbox (jr/image_sandbox.py).

The release asset device_evidence downloads was chosen by a stranger, and the pinned esptool
parser reading it is a large dependency tree. Owner spec 2026-11-04: parse in a restricted process
— no credentials, no network, no serial. validate(data) runs esp_image.validate in a fresh
`python -I -B` under bubblewrap (/usr/bin/bwrap):

  namespaces      --unshare-all plus a mandatory user and cgroup namespace (net, pid, ipc, uts,
                  user, cgroup), --disable-userns, --cap-drop ALL, --new-session, --die-with-parent
  a tmpfs root    remounted read-only, holding only read-only binds of the interpreter's prefixes
                  (a venv and the install it links to), the site-packages esptool lives in, the
                  validator module, the dynamic loader's libraries (/usr/lib, /lib*, ld.so.cache:
                  the interpreter is dynamically linked), /dev/null + /dev/urandom, and a one-line
                  /etc/passwd of its own (home /nonexistent — esptool's config lookup wants one). No /home,
                  no /proc, no /tmp, no /etc, no serial device. Every other directory on the way
                  to a bind is 0111: traversable, never listable
  an empty env    env={} and --clearenv (bwrap's own PWD is dropped first thing; Python adds only
                  LC_CTYPE)
  hard rlimits    RLIMIT_AS, RLIMIT_CPU (SIGXCPU), RLIMIT_NOFILE, RLIMIT_FSIZE 0 and RLIMIT_CORE 0
                  set in the forked child before it execs bwrap, so they bind the whole sandbox
                  from its first instruction; RLIMIT_NPROC 0 is the child's first act instead —
                  a NPROC cap set before bwrap makes the kernel refuse the user namespace (its
                  process count is charged to the user's whole count). Hard limits stay lowered:
                  raising one needs CAP_SYS_RESOURCE in the initial namespace
  a wall clock    the parent kills bwrap's process group after WALL_TIMEOUT, counted while the
                  output is read; --die-with-parent and the pid namespace take the rest
  stdin only      the asset arrives on stdin; the result leaves as one JSON envelope on stdout
  capped output   stdout (STDOUT_CAP) and stderr (STDERR_CAP) are read concurrently; a stream one
                  byte over its cap kills the process group at once: `output_overflow`

FAIL CLOSED: no bwrap, or bwrap failing to build the sandbox (namespace creation refused, a bind
it cannot make), is needs_review with reason `sandbox_unavailable`. There is no unsandboxed path.

On top of the jail, the child keeps a Python-level guard (`guard=False` turns it off, for the tests
that prove the OS layer holds by itself): `socket` patched before esptool is imported, and an
audit hook (PEP 578: it cannot be removed) refusing with PermissionError every socket, ctypes and
process-start event, any write, any read or listing outside the bound roots, any device node but
the two harmless ones, file mutation, signals and rlimit changes. The guard makes refusals uniform
and readable; it is not what keeps native code in — the namespaces are.

The parent maps a crash, a signal, a timeout, an output overflow, output that is not the child's
`{"value": ...}` envelope (`bad_child_output`: not JSON, nested deeper than MAX_DEPTH — checked
before json decodes it — or any decode error), or a value that is not a well-formed validator
result to needs_review — never esp_target. A well-formed result passes
through unchanged. `run_isolated` is the generic runner the tests drive with probe modules.
"""
from __future__ import annotations

import importlib.util
import json
import os
import resource
import select
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import esp_image

ESP_IMAGE = Path(__file__).resolve().with_name("esp_image.py")
BWRAP = Path("/usr/bin/bwrap")
SANDBOX_UNAVAILABLE = "sandbox_unavailable"
TIMEOUT = "timeout"
OUTPUT_OVERFLOW = "output_overflow"
BAD_CHILD_OUTPUT = "bad_child_output"
WALL_TIMEOUT = 60.0             # seconds: a 16 MB image validates in well under 2 s on the Pi
CPU_SECONDS = 30
MEMORY_BYTES = 512 * 1024 * 1024    # address space; the child peaks near 75 MB of it on a 16 MB asset
OPEN_FILES = 64
STDOUT_CAP = 64 * 1024          # bytes: a validator result is well under 1 KiB
STDERR_CAP = 16 * 1024          # bytes: enough for a traceback's last line
MAX_DEPTH = 8                   # JSON nesting, the envelope included: a validator result is 3 deep
_READ_CHUNK = 32 * 1024
DEVICES = ("/dev/null", "/dev/urandom")
# What the dynamic loader needs, bound read-only (a symlinked one, as on merged-/usr, is recreated).
LOADER_PATHS = ("/usr/lib", "/usr/lib64", "/usr/lib32", "/lib", "/lib64", "/lib32", "/etc/ld.so.cache")

# The child's whole program, passed with -c so nothing on disk but the validated module is loaded
# from outside the interpreter's own library. argv: module path, function, JSON list of the
# readable roots, "guard" or "noguard".
_CHILD = r'''
import json
import os
import stat
import sys

NO_NET = "network is disabled in the image validator sandbox"
NO_PROC = "starting a process is disabled in the image validator sandbox"
_REFUSED = {
    **dict.fromkeys(("subprocess.Popen", "os.system", "os.fork", "os.forkpty", "os.exec", "os.posix_spawn",
                     "os.spawn", "pty.spawn"), NO_PROC),
    **dict.fromkeys(("os.remove", "os.rename", "os.rmdir", "os.mkdir", "os.truncate", "os.chmod", "os.chown",
                     "os.chflags", "os.utime", "os.symlink", "os.link", "os.setxattr", "os.removexattr"),
                    "changing files is disabled in the image validator sandbox"),
    **dict.fromkeys(("os.kill", "os.killpg", "signal.pthread_kill"),
                    "signalling processes is disabled in the image validator sandbox"),
    **dict.fromkeys(("resource.setrlimit", "resource.prlimit"),
                    "changing resource limits is disabled in the image validator sandbox"),
}
_REFUSED_PREFIXES = {"socket.": NO_NET, "ctypes.": "native code through ctypes is disabled in the image validator sandbox",
                     "shutil.": "changing files is disabled in the image validator sandbox"}
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC
_HARMLESS_DEVICES = {"/dev/null", "/dev/urandom"}
_ROOTS = []


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


def _real(path):
    return os.path.realpath(os.fsdecode(path))


def _is_device(real):
    if real in _HARMLESS_DEVICES:
        return False
    if real.startswith("/dev/"):
        return True
    try:
        mode = os.stat(real).st_mode
    except OSError:
        return False
    return stat.S_ISCHR(mode) or stat.S_ISBLK(mode)


def _readable(real):
    return real in _HARMLESS_DEVICES or any(real == r or real.startswith(r + os.sep) for r in _ROOTS)


def _check_read(path):
    if isinstance(path, int):
        return
    if not _readable(_real("." if path is None else path)):
        raise PermissionError(f"reading outside the interpreter and the validator module is disabled in the image validator sandbox: {path!r}")


def _check_open(path, mode=None, flags=None):
    if isinstance(path, int):
        return
    if _is_device(_real(path)):
        raise PermissionError(f"serial and device files are disabled in the image validator sandbox: {path!r}")
    writes = flags & _WRITE_FLAGS if isinstance(flags, int) else any(c in (mode or "") for c in "wax+")
    if writes:
        raise PermissionError(f"file writes are disabled in the image validator sandbox: {path!r}")
    _check_read(path)


def _hook(event, args):
    why = _REFUSED.get(event) or next((w for p, w in _REFUSED_PREFIXES.items() if event.startswith(p)), None)
    if why:
        raise PermissionError(why)
    if event == "open":
        _check_open(*args[:3])
    elif event in ("os.listdir", "os.scandir"):
        _check_read(args[0])


def _no_more_processes():
    import resource
    resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))


def main():
    path, func, roots, guard = sys.argv[1], sys.argv[2], json.loads(sys.argv[3]), sys.argv[4] == "guard"
    os.environ.pop("PWD", None)     # bwrap's own, set after --clearenv
    _no_more_processes()
    if guard:
        _ROOTS.extend(os.path.realpath(r) for r in roots)
        _patch_socket()             # before anything imports esptool or pyserial
        sys.addaudithook(_hook)
    data = sys.stdin.buffer.read()
    import importlib.util
    spec = importlib.util.spec_from_file_location("sandboxed_validator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.stdout.write(json.dumps({"value": getattr(module, func)(data)}))


main()
'''


def run_isolated(module_path: Path, func: str, data: bytes, *, wall_timeout: float | None = None,
                 cpu_seconds: int | None = None, memory_bytes: int | None = None, stdout_cap: int | None = None,
                 guard: bool = True) -> dict:
    """{"ok": True, "value": <the JSON `func(data)` returned>} or {"ok": False, "why": str} for
    `module_path`'s `func` run on `data` in the sandboxed child. Unset limits are the module's.
    A `why` starting with SANDBOX_UNAVAILABLE means the sandbox was never built: nothing ran."""
    wall_timeout, cpu_seconds = wall_timeout or WALL_TIMEOUT, cpu_seconds or CPU_SECONDS
    memory_bytes, stdout_cap = memory_bytes or MEMORY_BYTES, stdout_cap or STDOUT_CAP
    if not BWRAP.is_file():
        return _failed(f"{SANDBOX_UNAVAILABLE}: {BWRAP} not found")
    if not Path(sys.executable).is_file():
        return _failed(f"could not start the child: no interpreter at {sys.executable}")
    module = Path(module_path).resolve()
    roots = _python_roots()
    child = [sys.executable, "-I", "-B", "-c", _CHILD, str(module), func, json.dumps(roots + [str(module)]),
             "guard" if guard else "noguard"]
    with tempfile.TemporaryDirectory(prefix="image-sandbox-") as private:
        deadline = time.monotonic() + wall_timeout
        try:
            proc = subprocess.Popen(sandbox_command(roots + [str(module)], child, passwd=_passwd_file(private)),
                                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env={}, cwd="/", process_group=0,
                                    preexec_fn=_hard_limits(memory_bytes, cpu_seconds))
        except OSError as e:
            return _failed(f"{SANDBOX_UNAVAILABLE}: could not run {BWRAP}: {e}")
        try:
            stdout, stderr, cut = _communicate(proc, bytes(data), deadline, stdout_cap)
        except OSError as e:
            return _failed(f"could not read the child: {e}")
        finally:
            _stop(proc)
    if cut == TIMEOUT:
        return _failed(f"{TIMEOUT}: killed after the {wall_timeout:g} s wall-clock timeout")
    if cut:
        return _failed(f"{OUTPUT_OVERFLOW}: child {cut}")
    if proc.returncode != 0:
        refused = _bwrap_error(stderr)
        if refused:
            return _failed(f"{SANDBOX_UNAVAILABLE}: {refused}")
        return _failed(f"child {_exit(proc.returncode)}: {_last_line(stderr)}")
    return decode_child_output(stdout)


def _communicate(proc: subprocess.Popen, data: bytes, deadline: float, stdout_cap: int):
    """(stdout, stderr, cut): `data` written to the child's stdin while both its output streams are
    read, each held to its cap, until both close and the child exits. `cut` is None, TIMEOUT once
    `deadline` passes, or "<stream> exceeded <cap> bytes" the moment a stream goes one byte over;
    the caller kills the child either way."""
    caps = {proc.stdout: ("stdout", stdout_cap), proc.stderr: ("stderr", STDERR_CAP)}
    output = {proc.stdout: bytearray(), proc.stderr: bytearray()}
    pending, offset = memoryview(data), 0
    with selectors.DefaultSelector() as selector:
        if pending:
            selector.register(proc.stdin, selectors.EVENT_WRITE)
        else:
            _close(proc.stdin)
        for stream in caps:
            selector.register(stream, selectors.EVENT_READ)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return bytes(output[proc.stdout]), bytes(output[proc.stderr]), TIMEOUT
            for key, _ in selector.select(remaining):
                stream = key.fileobj
                if stream is proc.stdin:
                    try:        # select promised room for PIPE_BUF bytes: this write cannot block
                        offset += os.write(stream.fileno(), pending[offset:offset + select.PIPE_BUF])
                    except BrokenPipeError:
                        offset = len(pending)
                    if offset >= len(pending):
                        selector.unregister(stream)
                        _close(stream)
                    continue
                name, cap = caps[stream]
                buf = output[stream]
                chunk = os.read(stream.fileno(), min(_READ_CHUNK, cap + 1 - len(buf)))
                if not chunk:
                    selector.unregister(stream)
                    _close(stream)
                    continue
                buf += chunk
                if len(buf) > cap:
                    return bytes(output[proc.stdout]), bytes(output[proc.stderr]), f"{name} exceeded {cap} bytes"
    try:
        proc.wait(timeout=max(deadline - time.monotonic(), 0))
    except subprocess.TimeoutExpired:
        return bytes(output[proc.stdout]), bytes(output[proc.stderr]), TIMEOUT
    return bytes(output[proc.stdout]), bytes(output[proc.stderr]), None


def _stop(proc: subprocess.Popen) -> None:
    """SIGKILL bwrap's process group (it leads its own: process_group=0) unless bwrap has already
    exited and been reaped — only then could its pid name someone else — and reap it."""
    if proc.returncode is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    proc.wait()
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        _close(stream)


def _close(stream) -> None:
    try:
        stream.close()
    except OSError:
        pass


def decode_child_output(raw: bytes) -> dict:
    """{"ok": True, "value": ...} for the child's one-key `{"value": ...}` envelope, else a
    BAD_CHILD_OUTPUT failure. The nesting is checked before json sees the text, and no decode
    error (RecursionError and MemoryError included) gets past this function."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _failed(f"{BAD_CHILD_OUTPUT}: child output is not JSON (not UTF-8): {raw[:120]!r}")
    if _nested_deeper_than(text, MAX_DEPTH):
        return _failed(f"{BAD_CHILD_OUTPUT}: child output is nested deeper than {MAX_DEPTH}: {raw[:120]!r}")
    try:
        doc = json.loads(text)
    except (ValueError, RecursionError, MemoryError, TypeError):
        return _failed(f"{BAD_CHILD_OUTPUT}: child output is not JSON: {raw[:120]!r}")
    if not (isinstance(doc, dict) and set(doc) == {"value"}):
        return _failed(f"{BAD_CHILD_OUTPUT}: child output is not the child's envelope: {raw[:120]!r}")
    return {"ok": True, "value": doc["value"]}


def _nested_deeper_than(text: str, limit: int) -> bool:
    """Whether `text`'s arrays and objects (brackets outside strings) open more than `limit` deep.
    Exact for valid JSON; on invalid JSON json.loads stops at the first bracket this miscounts."""
    depth, in_string, escaped = 0, False, False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "[{":
            depth += 1
            if depth > limit:
                return True
        elif ch in "]}":
            depth -= 1
    return False


def unavailable_reason() -> str | None:
    """None when this host can build the sandbox, else why not (bwrap missing, user namespaces
    refused...). Runs the real validator on an empty asset through the real sandbox."""
    run = run_isolated(ESP_IMAGE, "validate", b"")
    return run["why"] if not run["ok"] and run["why"].startswith(SANDBOX_UNAVAILABLE) else None


def sandbox_command(binds: list[str], child: list[str], *, passwd: str) -> list[str]:
    """The bwrap argv running `child` with read-only `binds` (plus the loader, two devices and the
    `passwd` bound as /etc/passwd)."""
    cmd = [str(BWRAP), "--unshare-all", "--unshare-user", "--unshare-cgroup", "--disable-userns",
           "--die-with-parent", "--new-session", "--clearenv", "--cap-drop", "ALL",
           "--ro-bind", passwd, "/etc/passwd"]
    dests = ["/etc/passwd"]
    for path in LOADER_PATHS:
        if os.path.islink(path):
            cmd += ["--symlink", os.readlink(path), path]
        elif os.path.exists(path):
            cmd += ["--ro-bind", path, path]
            dests.append(path)
    for path in _outermost(binds):
        cmd += ["--ro-bind", path, path]
        dests.append(path)
    for dev in DEVICES:
        cmd += ["--dev-bind", dev, dev]
        dests.append(dev)
    for directory in _unlisted_ancestors(dests):
        cmd += ["--chmod", "0111", directory]
    return cmd + ["--chdir", "/", "--remount-ro", "/", "--"] + child


def _python_roots() -> list[str]:
    """The directories the interpreter runs from: its prefixes, every install a symlink hop of the
    executable lands in (a venv's bin/python -> the base install's), and esptool's site-packages.
    jr runs from jr/.venv (CI: setup-python's toolcache); a distro interpreter's prefix is all of /usr."""
    roots = {sys.prefix, sys.base_prefix, sys.exec_prefix, sys.base_exec_prefix}
    roots.update(os.path.dirname(os.path.dirname(hop)) for hop in _symlink_hops(sys.executable))
    spec = importlib.util.find_spec("esptool")
    if spec and spec.origin:
        roots.add(str(Path(spec.origin).parent.parent))
    return sorted(r for r in roots if r and os.path.isdir(r))


def _symlink_hops(path: str) -> list[str]:
    hops = [os.path.abspath(path)]
    while os.path.islink(hops[-1]) and len(hops) < 40:
        hops.append(os.path.normpath(os.path.join(os.path.dirname(hops[-1]), os.readlink(hops[-1]))))
    return hops


def _outermost(paths: list[str]) -> list[str]:
    """`paths` without the ones already inside another."""
    ordered = sorted(set(paths), key=len)
    return [p for i, p in enumerate(ordered) if not any(_inside(p, q) for q in ordered[:i])]


def _unlisted_ancestors(dests: list[str]) -> list[str]:
    """Every directory bwrap creates on the way to a bind (the root included), outermost first."""
    ancestors = {"/"}
    for dest in dests:
        parent = os.path.dirname(dest)
        while parent != "/":
            ancestors.add(parent)
            parent = os.path.dirname(parent)
    return sorted((a for a in ancestors if not any(_inside(a, d) for d in dests)), key=len)


def _inside(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def _passwd_file(private: str) -> str:
    """A one-line /etc/passwd for the sandbox's user, home /nonexistent, written in the run's private
    directory: esptool's config lookup (esp_pylib) asks for a home directory, and the host's passwd
    stays out. Bound, not copied in (--ro-bind-data writes a file, which RLIMIT_FSIZE 0 forbids)."""
    path = os.path.join(private, "passwd")
    with open(path, "w") as f:
        f.write(f"validator:x:{os.getuid()}:{os.getgid()}::/nonexistent:/nonexistent\n")
    return path


def _hard_limits(memory: int, cpu: int):
    def apply():        # in the forked child, before exec: only resource.setrlimit, no Python-level locks
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_NOFILE, (OPEN_FILES, OPEN_FILES))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


def _bwrap_error(stderr: bytes) -> str | None:
    """bwrap's own refusal (every message it prints starts "bwrap: "), which it emits before the
    child ever runs. A child printing one is still needs_review, so mimicry gains it nothing."""
    first = next((ln for ln in stderr.decode("utf-8", "replace").splitlines() if ln.strip()), "")
    return first[:200] if first.startswith("bwrap: ") else None


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
    """bwrap exits 128+N when its child dies of signal N; a negative code is bwrap itself killed."""
    signum = -code if code < 0 else code - 128 if code > 128 else 0
    if signum:
        try:
            return f"killed by {signal.Signals(signum).name}"
        except ValueError:
            return f"killed by signal {signum}"
    return f"exited with status {code}"


def _last_line(stderr: bytes) -> str:
    lines = [ln for ln in stderr.decode("utf-8", "replace").splitlines() if ln.strip()]
    return lines[-1][:200] if lines else "no error output"
