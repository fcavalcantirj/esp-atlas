.PHONY: coverage validate

# Re-runnable evidence that run_guide/parse_intent stay grounded across
# diverse ESP32 kinds/purposes -- see docs/coverage-matrix.md and
# ROADMAP.md. No network calls (the LLM is stubbed/dead throughout).
coverage:
	scripts/coverage.sh

# The dataset's own correctness gate (schema + soc->module->board chain).
validate:
	python3 scripts/validate.py
