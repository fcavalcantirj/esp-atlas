# esp-atlas-web

Next.js (App Router + TypeScript) frontend over `esp-atlas-api`. Per
`INTERFACE-SPEC.md`'s "smart API, dumb client" rule: this app never
re-implements search ranking or wizard scoring — it only calls the backend,
renders the response, forwards user input, and shows loading/error states.

## Install

```bash
npm install
```

## Configure

Copy `.env.example` to `.env.local` and point it at your running API (default
already matches):

```bash
cp .env.example .env.local
# NEXT_PUBLIC_API_URL=http://localhost:8000
# NEXT_PUBLIC_REPO_URL=https://github.com/fcavalcantirj/esp-atlas
```

`NEXT_PUBLIC_REPO_URL` is the GitHub repo the "contribute" links point at —
override it in a fork so "Edit on GitHub" etc. point at the fork instead of
upstream.

## Run

With `esp-atlas-api` already running on port 8000 (see `apps/api/README.md`):

```bash
npm run dev
```

Open http://localhost:3000.

## Pages

- `/` — wizard (guided needs -> ranked parts with reasons) + free-text/filter search
- `/parts/[id]` — one record: full specs + clickable source URLs + "Edit on
  GitHub" / "View source" links to the record's markdown file
- `/compare` — pick multiple parts, see a side-by-side spec table

Every page also has a header ("Add a part", "Contribute on GitHub") and a
footer (link to the `data/` folder on GitHub) — see `app/layout.tsx`.

## Layout

- `lib/api.ts` — typed fetch client for `/health /search /wizard /parts`, no logic
- `lib/github.ts` — builds GitHub URLs (repo root, edit/blob file links, `CONTRIBUTING.md`, `data/`) from `NEXT_PUBLIC_REPO_URL`, no other logic
- `components/WizardForm.tsx`, `components/SearchBox.tsx` — client components, call the API and render results/loading/error
- `components/PartResultCard.tsx` — shared result row (search results and wizard results, with score+reasons when present)
- `app/parts/[id]/page.tsx`, `app/compare/page.tsx` — part detail and compare views

## Test

```bash
npx tsc --noEmit
npm run lint
npm run build
```

No frontend unit tests are added for M1 — all ranking/filtering logic (the
part that needs test coverage) lives in `esp_atlas_core` / `esp-atlas-api`,
already covered there. This app was smoke-tested end to end in a real browser
against a live API (wizard, search, part detail with source links, compare).
