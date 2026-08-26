#!/usr/bin/env python3
"""GOLDEN ORACLE for real-Groq intent inference (SPEC-INDEX G4).

apps/core/tests/test_intent_oracle.py and test_coverage_matrix.py inject a
fake/dead LLM -- they prove the plumbing around parse_intent never breaks,
but they cannot catch Groq itself being inconsistent about WHEN to infer a
spec from a vague noun (measured on prod: "cheap wearable" -> battery,
"esp32 with a camera" -> psram_min:2, but "waterproof gps tracker" and
"build a plant monitoring system" -> nothing -- same rule, applied unevenly).

This script runs the curated matrix in apps/core/tests/data/inference_golden.py
against REAL inference, in one of two modes:

  (a) HTTP  -- POST {url}/intent for each query, against a live esp-atlas API.
               url defaults to the production API (https://esp-atlas.com/api),
               override with env ESP_ATLAS_API.
  (b) direct -- calls esp_atlas_core.intent.parse_intent with a real GroqClient
               directly, no HTTP hop. Used automatically when GROQ_API_KEY is
               set, since it is the cheaper/more direct path.

This is an ON-DEMAND acceptance check, not a CI gate: live Groq output is not
deterministic and prod may not be reachable from every environment. It is
deliberately NOT wired into the blocking test suite -- see
apps/core/tests/test_intent_golden_live.py for the pytest-skippable wrapper,
and `make inference-oracle` / `npm run inference:oracle` for how to run it.

Usage:
    python3 scripts/inference_oracle.py                    # HTTP against prod
    ESP_ATLAS_API=http://localhost:8000 python3 scripts/inference_oracle.py
    GROQ_API_KEY=... python3 scripts/inference_oracle.py    # direct GroqClient
"""
import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
GOLDEN_PATH = REPO_ROOT / "apps" / "core" / "tests" / "data" / "inference_golden.py"

DEFAULT_API_URL = "https://esp-atlas.com/api"


def _load_golden():
    spec = importlib.util.spec_from_file_location("inference_golden", GOLDEN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GOLDEN


def _check(entry, result):
    """One golden entry vs. one real parse_intent()-shaped result -> list of failure strings (empty = PASS)."""
    failures = []
    kind = result.get("kind")
    expect_kind = entry.get("expect_kind")
    allowed_kinds = (expect_kind,) if isinstance(expect_kind, str) else tuple(expect_kind)
    if kind not in allowed_kinds:
        failures.append(f"kind={kind!r}, expected one of {allowed_kinds!r}")

    filters = result.get("filters") or {}

    if entry.get("filters_empty"):
        if filters:
            failures.append(f"expected empty filters, got {filters!r}")

    for key, value in entry.get("must_filters", {}).items():
        if key not in filters:
            failures.append(f"missing must_filters[{key!r}] (expected {value!r})")
        elif filters[key] != value:
            failures.append(f"must_filters[{key!r}] = {filters[key]!r}, expected {value!r}")

    for key in entry.get("forbid_filters", []):
        if key in filters:
            failures.append(f"forbidden filter {key!r} present (value={filters[key]!r}) -- invented")

    unmapped = [str(u).lower() for u in (result.get("unmapped") or [])]
    for substr in entry.get("must_unmapped", []):
        if not any(substr.lower() in u for u in unmapped):
            failures.append(f"expected {substr!r} in unmapped, got {result.get('unmapped')!r}")

    return failures


def _run_http(golden, url):
    import httpx

    results = []
    with httpx.Client(timeout=30) as client:
        for entry in golden:
            try:
                response = client.post(f"{url}/intent", json={"query": entry["query"]})
                response.raise_for_status()
                results.append((entry, response.json(), None))
            except Exception as exc:  # network/HTTP error -- record as a failed run, don't crash the table
                results.append((entry, {}, str(exc)))
    return results


def _run_direct(golden):
    sys.path.insert(0, str(CORE_SRC))
    from esp_atlas_core.index_build import build_index
    from esp_atlas_core.intent import parse_intent
    from esp_atlas_core.llm import FAST_MODEL, GroqClient

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "esp-atlas.db"
        build_index(db_path=db_path)
        client = GroqClient(model=FAST_MODEL)

        results = []
        for entry in golden:
            try:
                parsed = parse_intent(entry["query"], llm_client=client, db_path=db_path, use_cache=False)
                results.append((entry, parsed, None))
            except Exception as exc:
                results.append((entry, {}, str(exc)))
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

    print(f"inference_oracle: mode={mode}, {len(golden)} golden queries\n")

    passed = 0
    failures_by_query = []
    for entry, parsed, error in results:
        if error is not None:
            status = "FAIL"
            reasons = [f"error: {error}"]
        else:
            reasons = _check(entry, parsed)
            status = "PASS" if not reasons else "FAIL"

        if status == "PASS":
            passed += 1
        else:
            failures_by_query.append((entry, reasons))

        print(f"[{status}] {entry['id']:32s} {entry['query']!r}")
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
