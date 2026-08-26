"""pytest wrapper around the REAL-Groq clarify() golden query matrix
(SPEC-clarify.md §8).

Every other test around clarify injects a fake/dead LLM -- see
test_clarify.py's own docstring. This file is the deliberate exception: it
drives the SAME golden matrix (apps/core/tests/data/clarify_golden.py, also
used by scripts/clarify_oracle.py) against REAL inference, either a live HTTP
endpoint (env ESP_ATLAS_API) or a real GroqClient (env GROQ_API_KEY).

It is SKIPPED by default -- neither env var is set in a normal `pytest` run,
so this file adds zero cost/flakiness to the fast unit suite and is NOT part
of the blocking CI job. Run it on demand:

    ESP_ATLAS_API=https://esp-atlas.com/api pytest -m inference
    GROQ_API_KEY=... pytest -m inference
    make clarify-oracle   # same matrix, a readable PASS/FAIL table instead
"""
import importlib.util
import os
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
ORACLE_PATH = REPO_ROOT / "scripts" / "clarify_oracle.py"


def _load_oracle():
    spec = importlib.util.spec_from_file_location("clarify_oracle", ORACLE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_oracle = _load_oracle()
_GOLDEN = _oracle._load_golden()

_LIVE = bool(os.environ.get("ESP_ATLAS_API") or os.environ.get("GROQ_API_KEY"))
_SKIP_REASON = "set ESP_ATLAS_API or GROQ_API_KEY to run this against real Groq inference"

pytestmark = pytest.mark.inference


@pytest.mark.skipif(not _LIVE, reason=_SKIP_REASON)
@pytest.mark.parametrize("entry", _GOLDEN, ids=[e["id"] for e in _GOLDEN])
def test_golden_query_against_real_inference(entry):
    if os.environ.get("GROQ_API_KEY"):
        results = _oracle._run_direct([entry])
    else:
        url = os.environ.get("ESP_ATLAS_API", _oracle.DEFAULT_API_URL)
        results = _oracle._run_http([entry], url)

    entry_result, reasons = results[0]
    assert entry_result is entry
    assert not reasons, "; ".join(reasons)
