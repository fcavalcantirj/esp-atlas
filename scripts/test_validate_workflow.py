"""The web unit tests (apps/web lib/*.test.ts, public-copy guard included) run inside the
REQUIRED `tests` job of .github/workflows/validate.yml — not in a side job branch protection
does not know about, and never as continue-on-error."""
from __future__ import annotations

import json
import shlex
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
WORKFLOW = REPO / ".github" / "workflows" / "validate.yml"
WEB = REPO / "apps" / "web"


def _tests_job() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())["jobs"]["tests"]


def _web_step(steps: list[dict], run: str) -> dict:
    matches = [s for s in steps if s.get("run") == run and s.get("working-directory") == "apps/web"]
    assert len(matches) == 1, f"expected exactly one `{run}` step in apps/web, got {matches}"
    return matches[0]


def test_tests_job_sets_up_node_22_then_installs_and_runs_the_web_suite():
    job = _tests_job()
    steps = job["steps"]
    assert "continue-on-error" not in job

    node = [i for i, s in enumerate(steps) if str(s.get("uses", "")).startswith("actions/setup-node@")]
    assert len(node) == 1, "the tests job needs exactly one actions/setup-node step"
    assert str(steps[node[0]]["with"]["node-version"]) == "22"

    ci, test = _web_step(steps, "npm ci"), _web_step(steps, "npm test")
    assert node[0] < steps.index(ci) < steps.index(test)
    for step in (steps[node[0]], ci, test):
        assert "continue-on-error" not in step, f"{step} must block the job"


def test_web_suite_is_not_a_separate_job():
    jobs = yaml.safe_load(WORKFLOW.read_text())["jobs"]
    others = [name for name, job in jobs.items() if name != "tests" and "npm test" in json.dumps(job)]
    assert others == []


def test_npm_test_runs_the_public_copy_guard():
    script = json.loads((WEB / "package.json").read_text())["scripts"]["test"]
    argv = shlex.split(script)
    assert argv[:2] == ["node", "--test"]
    ran = {p.relative_to(WEB).as_posix() for pattern in argv[2:] for p in WEB.glob(pattern)}
    assert "lib/public-copy.test.ts" in ran
