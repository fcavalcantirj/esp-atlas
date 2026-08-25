#!/usr/bin/env bash
# Reproducible entrypoint for the run_guide/parse_intent coverage matrix
# (apps/core/tests/test_coverage_matrix.py) -- see docs/coverage-matrix.md
# for the human-readable table this test pins, and ROADMAP.md for the known
# gaps it surfaces on purpose. No network calls: the LLM is stubbed/dead
# throughout, so this is safe to run offline and in CI.
#
# Usage: scripts/coverage.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

python3 -m pytest apps/core/tests/test_coverage_matrix.py -v
