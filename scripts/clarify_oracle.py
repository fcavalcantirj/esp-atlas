#!/usr/bin/env python3
"""GOLDEN ORACLE for real-Groq clarify() question selection (SPEC-clarify.md §8).

Same shape and purpose as scripts/build_guide_oracle.py, but against
`esp_atlas_core.clarify.clarify` / `POST /clarify` and the query matrix in
apps/core/tests/data/clarify_golden.py. The confidence GATE is pure
deterministic code (nothing to golden-test there); this oracle only checks
that live Groq picks grounded, sane dimension ids for a vague goal.

This is an ON-DEMAND acceptance check, not a CI gate: live Groq output is not
deterministic. It is deliberately NOT wired into the blocking test suite --
see apps/core/tests/test_clarify_golden_live.py for the pytest-skippable
wrapper, and `make clarify-oracle` / `npm run clarify:oracle` for how to run it.

Usage:
    python3 scripts/clarify_oracle.py                    # HTTP against prod
    ESP_ATLAS_API=http://localhost:8000 python3 scripts/clarify_oracle.py
    GROQ_API_KEY=... python3 scripts/clarify_oracle.py    # direct GroqClient
"""
import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
GOLDEN_PATH = REPO_ROOT / "apps" / "core" / "tests" / "data" / "clarify_golden.py"

DEFAULT_API_URL = "https://esp-atlas.com/api"

# Mirrors esp_atlas_core.clarify._CATALOG's keys -- kept as a plain constant
# here (rather than imported) so HTTP mode needs no local esp_atlas_core
# install, same pattern as build_guide_oracle.py's board_exists split.
_KNOWN_DIMENSION_IDS = {"power", "environment", "target", "interaction", "budget"}


def _load_golden():
    spec = importlib.util.spec_from_file_location("clarify_golden", GOLDEN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GOLDEN


def _check(entry, result):
    """One golden entry vs. one clarify()-shaped result -> list of failure
    strings (empty = PASS)."""
    failures = []

    if result.get("confident"):
        failures.append("confident=True, expected a grounded question set for a vague goal")

    questions = result.get("questions") or []
    ids = [q.get("id") for q in questions]

    if not ids:
        failures.append("no questions returned")

    invented = [i for i in ids if i not in _KNOWN_DIMENSION_IDS]
    if invented:
        failures.append(f"invented dimension id(s) outside the fixed catalog: {invented!r}")

    if len(ids) > 3:
        failures.append(f"{len(ids)} questions returned, expected at most 3")

    expected = entry["expect_any_of"]
    if not any(i in expected for i in ids):
        failures.append(f"question ids {ids!r} share nothing with expected {expected!r}")

    for question in questions:
        if not question.get("prompt"):
            failures.append(f"question {question.get('id')!r} has no prompt")
        if not question.get("options"):
            failures.append(f"question {question.get('id')!r} has no options")

    return failures


def _run_http(golden, url):
    import httpx

    results = []
    with httpx.Client(timeout=30) as client:
        for entry in golden:
            try:
                response = client.post(f"{url}/clarify", json={"query": entry["query"]})
                response.raise_for_status()
                reasons = _check(entry, response.json())
            except Exception as exc:  # network/HTTP error -- record as a failed run, don't crash the table
                reasons = [f"error: {exc}"]
            results.append((entry, reasons))
    return results


def _run_direct(golden):
    sys.path.insert(0, str(CORE_SRC))
    from esp_atlas_core.clarify import clarify
    from esp_atlas_core.index_build import build_index
    from esp_atlas_core.llm import FAST_MODEL, GroqClient

    import tempfile

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "esp-atlas.db"
        build_index(db_path=db_path)
        client = GroqClient(model=FAST_MODEL)

        for entry in golden:
            try:
                result = clarify(entry["query"], llm_client=client, db_path=db_path, use_cache=False)
                reasons = _check(entry, result)
            except Exception as exc:
                reasons = [f"error: {exc}"]
            results.append((entry, reasons))
    return results


def main():
    golden = _load_golden()

    groq_key = os.environ.get("GROQ_API_KEY")
    url = os.environ.get("ESP_ATLAS_API", DEFAULT_API_URL)

    if groq_key:
        mode = "direct (real GroqClient)"
        results = _run_direct(golden)
    else:
        mode = f"HTTP ({url})"
        results = _run_http(golden, url)

    print(f"clarify_oracle: mode={mode}, {len(golden)} golden queries\n")

    passed = 0
    failures_by_query = []
    for entry, reasons in results:
        status = "PASS" if not reasons else "FAIL"

        if status == "PASS":
            passed += 1
        else:
            failures_by_query.append((entry, reasons))

        print(f"[{status}] {entry['id']:24s} {entry['query']!r}")
        for reason in reasons:
            print(f"        - {reason}")

    total = len(golden)
    print(f"\n{passed}/{total} passed")

    if failures_by_query:
        print("\nFAILURES:")
        for entry, reasons in failures_by_query:
            print(f"  - {entry['id']} ({entry['query']!r}): {'; '.join(reasons)}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
