# Deploying esp-atlas

esp-atlas ships as a **single Vercel deployment**: the Next.js frontend
(`apps/web`) and the FastAPI backend (`apps/api`, `esp_atlas_api.main:app`)
same-origin, with the backend served as a Vercel Python serverless function
under `/api`.

## Layout

```
vercel.json         # builds+routes config — the source of truth for the split below
requirements.txt     # deps for the Python function (path-installs apps/core, apps/api)
api/
  index.py          # ASGI entrypoint the Python function actually runs
apps/
  web/              # Next.js app, built by @vercel/next
  api/              # FastAPI app (esp_atlas_api.main:app) — the real route table
  core/             # esp_atlas_core — search/wizard/validate/index-build, no HTTP
```

## How the split works

`vercel.json` uses the legacy `builds` + `routes` form (not zero-config), because
this is a monorepo with two build targets that don't fit the single-framework
default:

- `apps/web/package.json` → built with `@vercel/next`.
- `api/index.py` → built with `@vercel/python`, with `config.includeFiles`
  bundling `data/**` and `schema/**` alongside the function so the SQLite
  index can be built at cold start from the same markdown dataset used
  locally.

Routes: `/api/(.*)` → the Python function, `/(.*)` → the Next.js build. A
request to `/api/health` on the deployed site hits `api/index.py`, which does:

```python
app = FastAPI()
app.mount("/api", esp_atlas_api.main.app)
```

So `esp_atlas_api.main`'s own route table (`/health`, `/search`, `/wizard`,
`/parts`, `/validate`) is unchanged — it resolves under `/api/*` here and
under `/*` when run standalone (`uvicorn esp_atlas_api.main:app`, used for
local dev and the API's own test suite).

### Writable paths on a read-only function

`esp_atlas_core.paths` resolves `REPO_ROOT` (and `DATA_DIR`/`PROMPTS_DIR`
under it) via `ESP_ATLAS_REPO_ROOT`, defaulting to the package's on-disk
location. `vercel.json` sets `ESP_ATLAS_REPO_ROOT=/var/task`, which is where
`@vercel/python`'s `includeFiles` places bundled repo-relative paths — so
`data/` and `schema/` resolve correctly inside the function.

The function's filesystem is read-only outside `/tmp`. `esp_atlas_core.paths.resolve_db_path()`
honors an explicit `ESP_ATLAS_DB_PATH` override; absent that, it falls back to
`/tmp/esp-atlas.db` whenever the `VERCEL` env var is set (Vercel sets this
automatically) or the repo root isn't writable — so the first request's
`build_index()` call (see `esp_atlas_api.main`'s lifespan hook) never tries to
write next to read-only source.

### Frontend → API URL

`apps/web/lib/api.ts` calls the API at `NEXT_PUBLIC_API_URL`, which:

- defaults to `/api` (same-origin) when `NODE_ENV=production` and the env var
  is unset — the deployed case, routed by `vercel.json`.
- defaults to `http://localhost:8000` otherwise — local dev against
  `uvicorn esp_atlas_api.main:app --port 8000`.
- is always overridable by setting `NEXT_PUBLIC_API_URL` explicitly (e.g. to
  point a preview deployment's frontend at a different API origin).

## Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | No (future) | Groq API key for the grounded `ask()` chat layer (`esp_atlas_core.llm`). Not required for `/health`, `/search`, `/wizard`, `/parts`, `/validate`. |
| `NEXT_PUBLIC_REPO_URL` | No | Overrides the GitHub URL used for "edit on GitHub" / "view source" links (`apps/web/lib/github.ts`). Defaults to `https://github.com/fcavalcantirj/esp-atlas`. |
| `NEXT_PUBLIC_API_URL` | No | Overrides the frontend's API base URL. Leave unset in production — it defaults to `/api`. |
| `ESP_ATLAS_REPO_ROOT` | Set by `vercel.json` | Where `esp_atlas_core` looks for `data/`, `schema/`, `prompts/`. Already set to `/var/task` for the deployed function; only needed manually for non-standard layouts. |
| `ESP_ATLAS_DB_PATH` | No | Overrides where `esp-atlas.db` gets built/read. Defaults to `/tmp/esp-atlas.db` on Vercel. |

Never commit `GROQ_API_KEY` or any secret — set it in the Vercel project's
Environment Variables settings.

## Deploying

```bash
npm i -g vercel   # once
vercel login      # once
vercel            # preview deploy
vercel --prod     # production deploy
```

Vercel picks up `vercel.json` at the repo root automatically — no project
dashboard configuration (Root Directory, Framework Preset) is needed since
the `builds` array declares both targets explicitly.

## Verifying a deployment

```bash
curl https://<your-deployment>/api/health
curl "https://<your-deployment>/api/search?q=zigbee"
curl https://<your-deployment>/            # Next.js frontend
```

`/api/health` returns `{"status": "ok", "count": <n>}` once the function has
built its SQLite index from the bundled `data/` on cold start.
