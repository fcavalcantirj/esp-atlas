# esp-atlas-api

FastAPI backend over `esp_atlas_core` — per `INTERFACE-SPEC.md`, a thin HTTP
shell: it calls into core's `search()` / `wizard()` and shapes the result for
JSON. It never re-implements retrieval, filtering, or scoring itself.

## Install (editable, for development)

```bash
cd apps/core && pip install -e .
cd ../api && pip install -e ".[test]"
```

## Run

```bash
uvicorn esp_atlas_api.main:app --reload --port 8000
```

On startup, if `esp-atlas.db` (repo root, or `ESP_ATLAS_DB_PATH` if set) is
missing, it's built automatically from `data/**/*.md` via
`esp_atlas_core.index_build.build_index`.

## Endpoints

- `GET /health` -> `{status, count}`
- `GET /search?q=&type=&radio=&band=&form=&protocol=&ieee802154=&ble=&bt_classic=&usb_native=`
  -> `{results: [record...]}` — structured filters + free-text, no LLM.
- `POST /wizard` body `{needs: {protocol?, radio?, band?, ble?, bt_classic?,
  usb_native?, ieee802154?, form?, type?, budget?}}` -> `{results: [record + score + reasons...]}`.
  `budget` is one of `cheap` / `medium` / `expensive` (or omitted). It's a
  **spending ceiling**, not an exact match: `budget=cheap` keeps only
  `price_tier: cheap`, `budget=medium` keeps `cheap` + `medium`, and
  `budget=expensive` keeps everything. A part with no `price_tier` set is
  **unrated, not free** — it's always kept regardless of `budget`, since an
  unknown price is never grounds to hide a part. `budget` only filters, it
  never scores (see `price_tier` note below). Omitting `budget` applies no
  price filtering at all.
- `GET /parts` -> `{results: [record...]}` (every soc/module/board)
- `GET /parts/{id}` -> a single record, or 404
- `POST /validate` body `{markdown: "<full md w/ frontmatter>"}` or
  `{kind: "soc"|"module"|"board", frontmatter: {...}}` -> `{ok, errors: [string...], kind}` —
  self-check a proposed record (schema, source-or-omit, inheritance refs) before opening a PR.
  No auth.

CORS is open (`allow_origins=["*"]`) so the Next.js dev server can call it
directly; tighten this before any public deploy (out of scope for M1).

## `price_tier` — editorial, not a spec

Every record may carry an optional `price_tier: cheap|medium|expensive`. This
is an **approximate, editorial street-price bucket** set by hand when a board
is added — it carries no `sources:` entry and is exempt from the
source-or-omit rule that governs every other field (see `SPEC.md`'s "if it
isn't verified it isn't stated"). It exists only to power the wizard's
`budget` filter and is never rendered next to, or mistaken for, a
datasheet-verified spec.

## Test

```bash
python3 -m pytest --cov=esp_atlas_api --cov-report=term-missing
```

Every endpoint is covered against a real `esp-atlas.db` built once per test
session from the actual seeded `data/` directory (see `tests/conftest.py`),
including `band=5` (returns `esp32-c5`) and a `protocol=zigbee` +
`usb_native=true` wizard case. Core-layer `ValueError`s (unknown filter/need)
are exercised via monkeypatch and surface as HTTP 400; malformed request
shapes (bad `type`, unknown wizard need) are rejected by Pydantic as 422.

## Layout

- `settings.py` — resolves the `esp-atlas.db` path (`ESP_ATLAS_DB_PATH` env, default repo root)
- `models.py` — Pydantic request/response shapes (no logic)
- `main.py` — the FastAPI app: `create_app(db_path=None)` factory + `app` instance for uvicorn
