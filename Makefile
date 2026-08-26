.PHONY: coverage validate inference-oracle build-guide-oracle

# Re-runnable evidence that run_guide/parse_intent stay grounded across
# diverse ESP32 kinds/purposes -- see docs/coverage-matrix.md and
# ROADMAP.md. No network calls (the LLM is stubbed/dead throughout).
coverage:
	scripts/coverage.sh

# The dataset's own correctness gate (schema + soc->module->board chain).
validate:
	python3 scripts/validate.py

# ON-DEMAND, not CI: exercises REAL Groq inference (live HTTP endpoint, prod
# by default, or a real GroqClient if GROQ_API_KEY is set) against the golden
# query matrix in apps/core/tests/data/inference_golden.py. See
# docs/coverage-matrix.md for what it checks and why the fast suite can't.
inference-oracle:
	python3 scripts/inference_oracle.py

# ON-DEMAND, not CI: same idea as inference-oracle, for build_guide's
# project->firmware picks -- see apps/core/tests/data/build_guide_golden.py.
build-guide-oracle:
	python3 scripts/build_guide_oracle.py
