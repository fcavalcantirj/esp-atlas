"""F1 (plans/2026-11-03-jr-fixes.md): every subprocess Jr spawns to run repo Python must use
sys.executable — the interpreter running the tick (JR_PYTHON) — never a PATH lookup of
"python3". Under the Hermes cron worker PATH resolves python3 to a bundled Python without
PyYAML, so scripts/validate.py died with ModuleNotFoundError and every authored firmware
was dropped as guard_red.
"""
import ast
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tools

JR_DIR = Path(__file__).resolve().parent
BARE_INTERPRETERS = {"python", "python3"}


@pytest.fixture
def captured_argv(monkeypatch):
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(tools.subprocess, "run", fake_run)
    return calls


def test_run_guard_invokes_the_tick_interpreter(captured_argv):
    assert tools.run_guard()["ok"] is True
    assert captured_argv == [[sys.executable, "scripts/validate.py"]]


def test_run_ci_tests_invokes_the_tick_interpreter(captured_argv):
    assert tools.run_ci_tests()["ok"] is True
    assert len(captured_argv) == 1
    assert captured_argv[0][:3] == [sys.executable, "-m", "pytest"]


def _bare_interpreter_argvs(source: str) -> list[int]:
    """Line numbers of list/tuple literals whose argv[0] is a bare "python"/"python3" string."""
    hits = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.List, ast.Tuple)) and node.elts:
            first = node.elts[0]
            if isinstance(first, ast.Constant) and first.value in BARE_INTERPRETERS:
                hits.append(node.lineno)
    return hits


def test_detector_flags_a_bare_python3_argv():
    src = 'import subprocess\nsubprocess.run(["python3", "scripts/validate.py"])\n'
    assert _bare_interpreter_argvs(src) == [2]


def test_detector_ignores_sys_executable_and_docstring_mentions():
    src = '"""Run: python3 jr/tick.py"""\nimport subprocess, sys\nsubprocess.run([sys.executable, "-m", "pytest"])\n'
    assert _bare_interpreter_argvs(src) == []


def test_no_jr_source_spawns_a_bare_python_interpreter():
    offenders = {}
    for path in sorted(JR_DIR.glob("*.py")):
        if path.name.startswith("test_") or path.name == "conftest.py":
            continue
        hits = _bare_interpreter_argvs(path.read_text())
        if hits:
            offenders[path.name] = hits
    assert offenders == {}, f"use sys.executable, not a PATH lookup: {offenders}"
