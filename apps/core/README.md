# esp-atlas-core

The reusable brain behind esp-atlas: builds a SQLite FTS5 index of the
`data/**/*.md` dataset and exposes deterministic `search()` / `wizard()` plus
a grounded, cited `ask()` (Groq-backed, temperature 0). See `INTERFACE-SPEC.md`
at the repo root for the full design. This package never touches `data/`,
`schema/`, or `scripts/` — it only reads them.

## Install (editable, for development)

```bash
cd apps/core
pip install -e ".[test]"
```

## Build the index

`esp-atlas.db` is a gitignored build artifact — regenerate it any time `data/`
changes:

```python
from esp_atlas_core.index_build import build_index
build_index()  # writes <repo root>/esp-atlas.db
```

or via the CLI: `esp-atlas build-index` (see `apps/cli/README.md`).

## Use

```python
from esp_atlas_core.facets import facets
from esp_atlas_core.search import get_part, search
from esp_atlas_core.wizard import wizard
from esp_atlas_core.ask import ask

search("zigbee", filters={"form": "xiao"})
search("", filters={"soc": "esp32-c6", "type": "board"})  # boards built on one SoC
get_part("xiao-esp32c6")  # record + frontmatter + body + chain + related
facets()                  # {"form_factor": [{"value": "devkit", "count": 19}, ...], ...}
wizard({"protocol": "zigbee", "usb_native": True})
wizard({"budget": "cheap"})  # spending ceiling over each board's editorial price_tier

# ask() calls Groq — set GROQ_API_KEY (and optionally GROQ_MODEL) first
ask("Does the ESP32-C6 support Zigbee?")
```

`ask()`'s `llm_client` argument is injectable — pass anything with a
`.complete(system_prompt, user_prompt, temperature=0) -> str` method (this is
how tests avoid any real network call; see `tests/test_ask.py`).

### Environment

- `GROQ_API_KEY` — required for real `ask()` calls; never hardcode it. Raised
  as `esp_atlas_core.llm.GroqConfigError` only at call time if missing.
- `GROQ_MODEL` — optional, defaults to a current Llama-70B-class Groq instruct
  model (`llama-3.3-70b-versatile`).

## Test

```bash
python3 -m pytest --cov=esp_atlas_core --cov-report=term-missing
```

No test calls the real Groq API — `ask()` tests inject a fake LLM client, and
`llm.py`'s own tests inject an `httpx.MockTransport`.

## Layout

- `frontmatter.py` — shared YAML-frontmatter parser for `data/**/*.md`
- `validate.py` — schema + source-or-omit + id/brand + inheritance-ref validation
  for a single soc/module/board record; the shared implementation behind
  `scripts/validate.py` (CI), `esp-atlas validate` (CLI), and `POST /validate` (API)
- `index_build.py` — resolves soc/module/board radio+USB inheritance into
  `esp-atlas.db` (`parts` structured table, incl. each record's full frontmatter
  JSON and prose body, + `parts_fts` FTS5 table); older db files are migrated in
  place (missing columns are added) on the next build
- `db.py` — schema DDL + connection helpers
- `search.py` — structured `WHERE` + FTS5 `MATCH`, no LLM; `get_part(id)` returns one
  record with its frontmatter, prose body, inheritance chain and related parts
- `facets.py` — distinct values + counts per filterable column (data-driven dropdowns);
  `vendor_or_brand` entries are enriched with `display_name`/`url` via `brands.py`
- `brands.py` — `get_brand(slug)` / `list_brands()`: editorial name + homepage lookup
  from `data/brands/<slug>/brand.md`, kept out of `parts` on purpose
- `wizard.py` — deterministic needs -> scored, ranked parts, no LLM
- `llm.py` — injectable Groq chat-completions client (429 backoff, rate-limit
  headers, lazy key resolution)
- `ask.py` — retrieval + prompt assembly + citations + answer cache
