"""jr/image_sandbox.py reads what the child prints fail-closed (independent review 2026-11-04).

The child is the code a stranger's asset may have taken over, so its output is hostile too: stdout
and stderr are read concurrently under a hard byte cap each (a flood kills the child and its process
group at once — `output_overflow`, naming the stream), the wall clock runs while they are read, and
the result is decoded with a nesting limit checked before json ever sees it — anything that is not
the child's one-object envelope is `bad_child_output`, never an exception.

The decoder tests are plain unit tests and always run. The rest drive the real run_isolated with a
probe module and are `sandbox`-marked: jr/conftest.py skips them, with the reason, where bwrap cannot
build the sandbox."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

import image_sandbox as sb
from test_image_sandbox import probe

sandbox = pytest.mark.sandbox


def _running(marker: str) -> list[str]:
    """Host pids whose command line names `marker` (the probe's path is the child's argv)."""
    pids = []
    for entry in Path("/proc").iterdir():
        try:
            if entry.name.isdigit() and marker.encode() in (entry / "cmdline").read_bytes():
                pids.append(entry.name)
        except OSError:
            continue
    return pids


def _gone(marker: str, within: float = 3.0) -> bool:
    deadline = time.monotonic() + within
    while _running(marker):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.05)
    return True


def run_timed(tmp_path, body, **limits):
    module = probe(tmp_path, body)
    t0 = time.monotonic()
    got = sb.run_isolated(module, "run", b"", **limits)
    return got, time.monotonic() - t0, str(module)


# --- the decoder, without a sandbox -------------------------------------------------------------------

def envelope(value) -> bytes:
    return json.dumps({"value": value}).encode()


def _bad(got) -> bool:
    return got["ok"] is False and got["why"].startswith(sb.BAD_CHILD_OUTPUT + ": ")


def test_the_decoder_passes_the_envelope_s_value_through():
    value = {"status": "esp_target", "chip": "esp32s3", "reasons": ["ok"]}
    assert sb.decode_child_output(envelope(value)) == {"ok": True, "value": value}


def test_the_decoder_accepts_nesting_up_to_the_limit_and_refuses_one_more():
    at_limit = b'{"value": ' + b"[" * (sb.MAX_DEPTH - 1) + b"]" * (sb.MAX_DEPTH - 1) + b"}"
    assert sb.decode_child_output(at_limit)["ok"], sb.decode_child_output(at_limit)
    over = b'{"value": ' + b"[" * sb.MAX_DEPTH + b"]" * sb.MAX_DEPTH + b"}"
    got = sb.decode_child_output(over)
    assert _bad(got) and "nest" in got["why"], got


def test_the_decoder_refuses_100000_open_brackets_without_raising():
    got = sb.decode_child_output(b"[" * 100_000)
    assert _bad(got) and "nest" in got["why"], got


def test_brackets_inside_strings_are_not_nesting():
    deep_text = '[{"\\"' * 50
    assert sb.decode_child_output(envelope(deep_text)) == {"ok": True, "value": deep_text}


@pytest.mark.parametrize("raw", [b"[1, 2, 3]", b'"esp_target"', b"42", b"null", b"true",
                                 b'{"status": "esp_target"}', b'{"value": 1, "extra": 2}', b"{}"],
                         ids=["list", "string", "number", "null", "bool", "other-keys", "extra-key", "empty-dict"])
def test_the_decoder_refuses_anything_but_the_one_key_envelope(raw):
    got = sb.decode_child_output(raw)
    assert _bad(got) and "envelope" in got["why"], got


@pytest.mark.parametrize("raw", [b"", b"esp_target, trust me", b'{"value": ', b"\xff\xfe\x00garbage",
                                 b'{"value": 1}{"value": 2}'])
def test_the_decoder_refuses_what_is_not_json(raw):
    got = sb.decode_child_output(raw)
    assert _bad(got) and "not JSON" in got["why"], got


@pytest.mark.parametrize("error", [RecursionError, MemoryError, TypeError, ValueError])
def test_any_decode_error_is_bad_child_output(monkeypatch, error):
    def explode(*args, **kwargs):
        raise error("boom")

    monkeypatch.setattr(sb.json, "loads", explode)
    got = sb.decode_child_output(envelope({}))
    assert _bad(got) and "not JSON" in got["why"], got


# --- a fake bwrap, without a sandbox: the reader itself ------------------------------------------------

@pytest.fixture
def fake_bwrap(tmp_path, monkeypatch):
    """Install a shell script as bwrap; `body` runs in place of the sandbox."""
    def install(body: str) -> Path:
        fake = tmp_path / "bwrap"
        fake.write_text("#!/bin/sh\n" + body + "\n")
        fake.chmod(0o755)
        monkeypatch.setattr(sb, "BWRAP", fake)
        return fake
    return install


def test_an_overflow_kills_bwrap_s_whole_process_group(fake_bwrap, tmp_path):
    """A process bwrap left behind in its group dies with it (marked by argv: RLIMIT_FSIZE 0 forbids
    the fake writing a pid file)."""
    marker = f"left-behind-{tmp_path.name}"
    fake_bwrap(f"sh -c 'sleep 300; :' {marker} &\nexec yes")
    t0 = time.monotonic()
    got = sb.run_isolated(sb.ESP_IMAGE, "validate", b"", wall_timeout=30.0)
    assert got == {"ok": False, "why": f"{sb.OUTPUT_OVERFLOW}: child stdout exceeded {sb.STDOUT_CAP} bytes"}, got
    assert time.monotonic() - t0 < 5 and _gone(marker), _running(marker)


def test_the_wall_clock_holds_after_both_streams_close(fake_bwrap):
    fake_bwrap("exec >&- 2>&-\nexec sleep 300")
    t0 = time.monotonic()
    got = sb.run_isolated(sb.ESP_IMAGE, "validate", b"", wall_timeout=1.0)
    assert got == {"ok": False, "why": f"{sb.TIMEOUT}: killed after the 1 s wall-clock timeout"}, got
    assert time.monotonic() - t0 < 5


def test_a_bwrap_that_stops_reading_stdin_is_still_reported(fake_bwrap):
    """16 MB on stdin to a bwrap that refuses at once: the broken pipe ends the write, not the run."""
    fake_bwrap("exec 0<&-\necho 'bwrap: Creating new namespace failed' >&2\nexit 1")
    got = sb.run_isolated(sb.ESP_IMAGE, "validate", b"\xe9" * (16 * 1024 * 1024))
    assert got == {"ok": False, "why": f"{sb.SANDBOX_UNAVAILABLE}: bwrap: Creating new namespace failed"}, got


def test_an_error_reading_the_child_is_a_failure_and_the_child_is_killed(fake_bwrap, tmp_path, monkeypatch):
    marker = f"unread-{tmp_path.name}"
    fake_bwrap(f"exec sh -c 'sleep 300; :' {marker}")

    def unreadable(*args):
        raise OSError(5, "Input/output error")

    monkeypatch.setattr(sb, "_communicate", unreadable)
    got = sb.run_isolated(sb.ESP_IMAGE, "validate", b"")
    assert got == {"ok": False, "why": "could not read the child: [Errno 5] Input/output error"}, got
    assert _gone(marker), _running(marker)


# --- the real run_isolated: caps on what the child prints ---------------------------------------------

@sandbox
def test_ten_megabytes_on_stdout_is_an_overflow_and_the_child_is_killed(tmp_path):
    got, took, marker = run_timed(tmp_path, """
        import sys, time
        sys.stdout.write("x" * 10_000_000)
        sys.stdout.flush()
        time.sleep(60)
    """, wall_timeout=30.0)
    assert got == {"ok": False, "why": f"{sb.OUTPUT_OVERFLOW}: child stdout exceeded {sb.STDOUT_CAP} bytes"}, got
    assert took < 5 and _gone(marker), (took, _running(marker))


@sandbox
def test_ten_megabytes_on_stderr_is_an_overflow_and_the_child_is_killed(tmp_path):
    got, took, marker = run_timed(tmp_path, """
        import sys, time
        sys.stderr.write("e" * 10_000_000)
        sys.stderr.flush()
        time.sleep(60)
    """, wall_timeout=30.0)
    assert got == {"ok": False, "why": f"{sb.OUTPUT_OVERFLOW}: child stderr exceeded {sb.STDERR_CAP} bytes"}, got
    assert took < 5 and _gone(marker), (took, _running(marker))


@sandbox
def test_output_just_under_the_cap_still_comes_through(tmp_path):
    size = sb.STDOUT_CAP - len(envelope("")) - 64
    got = sb.run_isolated(probe(tmp_path, f"return 'y' * {size}"), "run", b"")
    assert got == {"ok": True, "value": "y" * size}


@sandbox
@pytest.mark.parametrize("count,cap", [(100_000, 1024 * 1024), (60_000, None)], ids=["100000-raised-cap", "60000-default-cap"])
def test_deeply_nested_output_is_bad_child_output_and_nothing_escapes(tmp_path, count, cap):
    got, _, _ = run_timed(tmp_path, f"""
        import os, sys
        sys.stdout.write("[" * {count})
        sys.stdout.flush()
        os._exit(0)
    """, stdout_cap=cap)
    assert got["ok"] is False and got["why"].startswith(sb.BAD_CHILD_OUTPUT + ": ") and "nest" in got["why"], got


@sandbox
def test_a_json_list_instead_of_the_envelope_is_bad_child_output(tmp_path):
    got, _, _ = run_timed(tmp_path, """
        import os, sys
        sys.stdout.write('["esp_target", "esp32s3"]')
        sys.stdout.flush()
        os._exit(0)
    """)
    assert got["ok"] is False and got["why"].startswith(sb.BAD_CHILD_OUTPUT + ": ") and "envelope" in got["why"], got


# --- the real run_isolated: the wall clock while reading ----------------------------------------------

@sandbox
def test_a_silent_child_past_the_wall_clock_is_a_timeout_and_is_killed(tmp_path):
    got, took, marker = run_timed(tmp_path, "import time\ntime.sleep(60)", wall_timeout=1.0)
    assert got == {"ok": False, "why": f"{sb.TIMEOUT}: killed after the 1 s wall-clock timeout"}, got
    assert took < 5 and _gone(marker), (took, _running(marker))


@sandbox
def test_a_child_that_closes_its_output_and_hangs_is_still_a_timeout(tmp_path):
    got, took, marker = run_timed(tmp_path, "import os, time\nos.close(1)\nos.close(2)\ntime.sleep(60)", wall_timeout=1.0)
    assert got["ok"] is False and got["why"].startswith(sb.TIMEOUT + ": "), got
    assert took < 5 and _gone(marker), (took, _running(marker))


@sandbox
def test_a_child_dripping_output_cannot_outrun_the_wall_clock(tmp_path):
    got, took, marker = run_timed(tmp_path, """
        import sys, time
        while True:
            sys.stdout.write(" ")
            sys.stdout.flush()
            time.sleep(0.05)
    """, wall_timeout=1.0)
    assert got["ok"] is False and got["why"].startswith(sb.TIMEOUT + ": "), got
    assert took < 5 and _gone(marker), (took, _running(marker))
