# esp-atlas-cli

The `esp-atlas` command-line front end over `esp_atlas_core` — a thin shell,
per `INTERFACE-SPEC.md`: it calls into core and renders human-readable output,
it never re-implements retrieval, scoring, or grounding logic itself.

## Install (editable, for development)

```bash
cd apps/core && pip install -e .
cd ../cli && pip install -e ".[test]"
```

This registers the `esp-atlas` console script.

## Usage

```bash
# build/refresh the SQLite index from data/**/*.md
esp-atlas build-index

# deterministic search — free text + structured filters, no LLM
esp-atlas search zigbee
esp-atlas search "" --radio wifi-6 --band 5 --form xiao
esp-atlas search "" --protocol thread --type board

# deterministic wizard — flags, or guided (interactive) with no flags
esp-atlas wizard --protocol zigbee --usb-native --no-guided
esp-atlas wizard   # prompts interactively

# grounded, cited natural-language question (calls Groq — needs GROQ_API_KEY)
export GROQ_API_KEY=...
esp-atlas ask "Does the ESP32-C6 support Zigbee?"

# self-check a record against schema/, source-or-omit, id/brand, and inheritance
# rules — the same checks CI runs — before opening a PR
esp-atlas validate data/boards/acme/my-board/board.md
cat draft-board.md | esp-atlas validate -   # read a full doc from stdin
```

Every `esp-atlas ask` answer prints a `Sources:` section — citations are
derived from the retrieved records' own `sources:` frontmatter, so they're
always present even if the model's reply doesn't restate them.

Pass `--db <path>` before the subcommand to point at a non-default
`esp-atlas.db` (default: `<repo root>/esp-atlas.db`).

## Test

```bash
python3 -m pytest --cov=esp_atlas_cli --cov-report=term-missing
```

CLI tests monkeypatch `esp_atlas_cli.main.core_ask`, so `ask` tests never
construct a real `GroqClient` or touch the network.
