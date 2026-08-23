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
- `GET /search?q=&type=&radio=&band=&form=&protocol=&soc=&module=&ieee802154=&ble=&bt_classic=&usb_native=`
  -> `{results: [record...]}` — structured filters + free-text, no LLM. `soc=<id>` /
  `module=<id>` return only parts built on that SoC / module (exact id match).
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
- `GET /parts/{id}` -> the record plus everything a detail page needs, or 404:
  `frontmatter` (the record's full YAML frontmatter — board usb/power/display/extras,
  module flash/psram, soc cpu/memory/security...), `body` (the markdown prose),
  `chain: {soc, module}` (the parent records it inherits radios from; a soc has
  neither, a bare-chip board has no module), `related: [record...]` (other parts on
  the same soc — and, for a module, boards using it — excluding itself and its chain).
- `GET /facets` -> distinct values with counts for every filterable column:
  `type, vendor_or_brand, form_factor, wifi_standard, price_tier, soc_ref` plus the
  comma-joined columns split into tokens (`wifi_bands`, `ieee802154_protocols`), each a
  `[{value, count}...]` list sorted by count desc then value. Lets a UI build its
  dropdowns from the data instead of hardcoding them. `vendor_or_brand` entries are
  `{value, count, display_name, url?}` — `display_name`/`url` come from
  `data/brands/<value>/brand.md` (see `esp_atlas_core.brands`), falling back to the
  slug itself when no such brand record exists.
- `GET /brands/{slug}` -> `{brand: {slug, name, url}, results: [record...]}` — every
  part for that brand slug (same filter as `/search?brand=<slug>`), plus the brand's
  own editorial identity. An unknown slug still returns 200 with `results: []`, `name`
  falling back to `slug` and `url: null`.
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
including `band=5` (returns `esp32-c5`), a `protocol=zigbee` + `usb_native=true`
wizard case, the `/parts/{id}` detail shape (frontmatter, body, chain, related),
`/facets`, and the `soc=` / `module=` filters. Core-layer `ValueError`s (unknown filter/need)
are exercised via monkeypatch and surface as HTTP 400; malformed request
shapes (bad `type`, unknown wizard need) are rejected by Pydantic as 422.

## Layout

- `settings.py` — resolves the `esp-atlas.db` path (`ESP_ATLAS_DB_PATH` env, default repo root)
- `models.py` — Pydantic request/response shapes (no logic)
- `main.py` — the FastAPI app: `create_app(db_path=None)` factory + `app` instance for uvicorn
