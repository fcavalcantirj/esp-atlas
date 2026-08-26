#!/usr/bin/env python3
"""GOLDEN ORACLE for real-Groq build_guide inference (SPEC-build-guide.md §7).

Same shape and purpose as scripts/inference_oracle.py (parse_intent's own
oracle), but against `esp_atlas_core.build_guide.build_guide` / `POST /build`
and the query matrix in apps/core/tests/data/build_guide_golden.py.

This is an ON-DEMAND acceptance check, not a CI gate: live Groq output is not
deterministic. It is deliberately NOT wired into the blocking test suite --
see apps/core/tests/test_build_guide_golden_live.py for the pytest-skippable
wrapper, and `make build-guide-oracle` / `npm run build-guide:oracle` for how
to run it.

Usage:
    python3 scripts/build_guide_oracle.py                    # HTTP against prod
    ESP_ATLAS_API=http://localhost:8000 python3 scripts/build_guide_oracle.py
    GROQ_API_KEY=... python3 scripts/build_guide_oracle.py    # direct GroqClient
"""
import importlib.util
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_SRC = REPO_ROOT / "apps" / "core" / "src"
GOLDEN_PATH = REPO_ROOT / "apps" / "core" / "tests" / "data" / "build_guide_golden.py"

DEFAULT_API_URL = "https://esp-atlas.com/api"


def _load_golden():
    spec = importlib.util.spec_from_file_location("build_guide_golden", GOLDEN_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.GOLDEN


def _check(entry, result, board_exists):
    """One golden entry vs. one build_guide()-shaped result -> list of failure
    strings (empty = PASS). `board_exists(board_id) -> bool` lets HTTP mode
    verify a board id against the live /parts endpoint and direct mode verify
    it against the local index, without this function knowing which."""
    failures = []

    expect_firmware = entry.get("expect_firmware")
    allowed = (expect_firmware,) if not isinstance(expect_firmware, tuple) else expect_firmware
    firmware = result.get("firmware") or {}
    firmware_id = firmware.get("id")
    if firmware_id not in allowed:
        failures.append(f"firmware.id={firmware_id!r}, expected one of {allowed!r}")

    boards = result.get("boards") or []
    if not boards:
        failures.append("boards is empty -- must never be a dead end")
    for board in boards:
        board_id = board.get("board_id")
        if not board_id or not board_exists(board_id):
            failures.append(f"invented or unresolvable board id: {board_id!r}")
        if not board.get("why"):
            failures.append(f"board {board_id!r} has no grounded why")

    return failures


def _run_http(golden, url):
    import httpx

    results = []
    with httpx.Client(timeout=30) as client:
        known_boards = {}

        def board_exists(board_id):
            if board_id not in known_boards:
                known_boards[board_id] = client.get(f"{url}/parts/{board_id}").status_code == 200
            return known_boards[board_id]

        for entry in golden:
            try:
                response = client.post(f"{url}/build", json={"query": entry["query"]})
                response.raise_for_status()
                results.append((entry, response.json(), board_exists, None))
            except Exception as exc:  # network/HTTP error -- record as a failed run, don't crash the table
                results.append((entry, {}, board_exists, str(exc)))
    return results


def _run_direct(golden):
    sys.path.insert(0, str(CORE_SRC))
    from esp_atlas_core.build_guide import build_guide
    from esp_atlas_core.index_build import build_index
    from esp_atlas_core.llm import FAST_MODEL, GroqClient
    from esp_atlas_core.search import get_part

    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "esp-atlas.db"
        build_index(db_path=db_path)
        client = GroqClient(model=FAST_MODEL)

        def board_exists(board_id):
            return get_part(board_id, db_path=db_path) is not None

        results = []
        for entry in golden:
            try:
                result = build_guide(entry["query"], llm_client=client, db_path=db_path)
                results.append((entry, result, board_exists, None))
            except Exception as exc:
                results.append((entry, {}, board_exists, str(exc)))
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

    print(f"build_guide_oracle: mode={mode}, {len(golden)} golden queries\n")

    passed = 0
    failures_by_query = []
    for entry, parsed, board_exists, error in results:
        if error is not None:
            status = "FAIL"
            reasons = [f"error: {error}"]
        else:
            reasons = _check(entry, parsed, board_exists)
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
