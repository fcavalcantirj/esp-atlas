# Architecture

The design goal: **correct, always-fresh answers with zero hallucinated specs.** Everything below serves that.

## 1. Data as code — the repo is the database

There is no separate database. The `data/**/*.md` files *are* the dataset. The website is a pure function of the repo: it stores nothing authoritative, so a merged PR is instantly the new truth, and correctness is crowd-verifiable in git history.

## 2. Retrieval — GitHub is the dataset, no vector DB

The corpus is small and **structured** (dozens–hundreds of files, YAML frontmatter). That means the right retrieval is a **structured query over frontmatter**, not semantic vector search — and the freshest source is GitHub itself.

```
merge to main ──▶ CI runs scripts/build_index.py ──▶ index.json published
                                                      (GitHub Pages / raw)
site ──fetch index.json (live)──▶ structured filter ──▶ wizard / compare
chat ──fetch the matched chip.md files (raw)──▶ inject into LLM context
```

- **`index.json`** is one small compiled artifact of every record's frontmatter. The site fetches it live from GitHub → **always fresh**, nothing to sync.
- **No vector store in v0.** Embeddings (RAG) are added later *only if* free-text prose search demands it. For structured specs they add cost and staleness for no gain.
- **Not zvec.** zvec / semantic-memory tools are for private agents, not a public backend.

## 3. The chat layer — grounded or silent

Runs on **Groq** (free tier: fast open-model inference; no embeddings needed, which is why there's no vector DB). The contract:

- **Temperature 0.** Deterministic.
- Answers **only** from the ESP context injected into the prompt (the retrieved `index.json` slice + full `chip.md` files).
- **Cites** the file and its datasheet source for every spec it states.
- When the answer isn't in the data: **"That's not in esp-atlas yet — want to open a PR?"** — never invents a number.
- Refuses off-topic questions: it answers about ESPs, nothing else.

The exact system prompt is versioned at [`prompts/system.md`](prompts/system.md) so its behaviour is reviewable and diffable like any other code.

### API keys
The Groq key is read from the `GROQ_API_KEY` environment variable only — **never committed, never hard-coded, never borrowed from another project.** Provision a dedicated key for this deployment and set it as a platform/CI secret.

## 4. The oracle-loop — an automated contributor

The community flywheel is slow to start, so a scheduled agent ("oracle-loop") bootstraps and maintains coverage:

1. Diff the dataset against the known ESP universe → pick the next **missing or stale** part (a SoC, module, or board).
2. Fetch its **official datasheet**, extract specs, emit a schema-valid `*.md` with `sources:` filled in.
3. Open a **pull request**, labelled `oracle-loop`, for human review.

Hard rules: it **opens PRs, never auto-merges**; it obeys the same source-or-omit discipline as human contributors; a human is always the merge gate. It complements human PRs — it doesn't replace review.

## 5. Why this shape holds up

- Adding a field = editing markdown + a source line. No migrations.
- Wizard, compare, and chat are all queries over the same structured frontmatter.
- Freshness is free (GitHub is the source); correctness is enforced (CI schema gate + source rule).
