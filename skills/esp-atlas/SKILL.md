---
name: esp-atlas
description: Search, add, or fix ESP32 chip/module/board records in the esp-atlas dataset — a community-maintained, datasheet-verified knowledge base of ESP32 SoCs, modules, and dev boards. Use when asked to add a new ESP32 part, correct a spec, or look up ESP32 chip/module/board data in the esp-atlas repo.
---

# esp-atlas contributor skill

esp-atlas is a plain-markdown, schema-validated dataset of ESP32 SoCs, modules,
and dev boards, each frontmatter record backed by cited official sources. This
skill is the portable version of the repo's [AGENTS.md](../../AGENTS.md) — load
it in any agent framework that needs to contribute to esp-atlas correctly.

## When to use this skill

- Adding a new ESP32 chip, module, or dev board to `data/`.
- Fixing an incorrect or stale spec in an existing record.
- Answering "does esp-atlas already have X?" before creating a duplicate.

## Data model

`soc → module → board`, specs declared once and inherited. A module references
its `soc:`; a board references its `module:` (or bare `soc:` for chip-only
boards). Never restate a spec that's already declared up the chain.

```
data/socs/<soc-id>/chip.md
data/modules/<module-id>/module.md
data/boards/<brand>/<board-id>/board.md
```

Each type's frontmatter must validate against `schema/soc.schema.json`,
`schema/module.schema.json`, or `schema/board.schema.json` respectively — read
the relevant schema file before filling a record.

## Hard rules

- **Source-or-omit.** Every hard spec needs a `sources:` entry (an official
  datasheet or vendor page + the date you verified it). Can't verify it? Omit
  the field. Never guess.
- **id is kebab-case and equals the folder name.**
- **A board's `brand` equals its brand folder.**
- **References must resolve** — `soc:`/`module:` must point at ids that exist.

## Workflow

1. **Search before add**, to avoid duplicates:
   ```bash
   esp-atlas search "<name>"
   ```
   or `GET /search?q=<name>` against the esp-atlas API.
2. **Copy the matching template** from `templates/` (`soc.template.md`,
   `module.template.md`, `board.template.md`) to the correct `data/` path.
3. **Fill it in with datasheet-cited values** — every field set needs a source;
   every field you can't verify, delete rather than guess.
4. **Self-validate:**
   ```bash
   esp-atlas validate data/<path>/<file>.md
   ```
   or `POST /validate {"markdown": "<file contents>"}`. This runs the exact
   checks CI runs (`python3 scripts/validate.py`) — fix everything it reports.
5. **Open a PR** with your source links in the description.

## Also see

- [AGENTS.md](../../AGENTS.md) — same rules, repo-root version for coding agents.
- [CONTRIBUTING.md](../../CONTRIBUTING.md) — human contribution guide.
- [llms.txt](../../llms.txt) — curated entry points for LLM tooling.
