# AGENTS.md — esp-atlas contributor guide for AI agents

esp-atlas is a community-maintained, datasheet-verified knowledge base for the ESP32
family of chips and the boards built on them, stored as plain markdown with YAML
frontmatter and validated by schema + CI. This file tells an agent how to add or fix
a record correctly, in one pass, without breaking `scripts/validate.py`.

## Data model

Three layers, specs declared once and inherited — never re-type a chip's radio specs
on every board:

```
soc      the silicon (ESP32, -S3, -C6, -H4, -P4, …)
  └─ module   a soc sealed in a can w/ flash/PSRAM/antenna (WROOM, WROVER, MINI…)
       └─ board   a module (or bare soc) on a board w/ USB/regulator/headers, by brand
```

A `module` declares `soc: <soc-id>`. A `board` declares `module: <module-id>` **or**
`soc: <soc-id>` (bare-chip boards), never both required — exactly one reference chain.
Query a board and you inherit the chip's radios from the chain, not from restated values.

## Folder layout

```
data/
  socs/<soc-id>/chip.md            # e.g. data/socs/esp32-s3/chip.md
  modules/<module-id>/module.md    # e.g. data/modules/esp32-s3-wroom-1/module.md
  boards/<brand>/<board-id>/board.md   # e.g. data/boards/lilygo/lilygo-t-display-s3/board.md
  brands/, companions/             # vendor profiles, non-ESP companion radios
schema/            # JSON Schema — the contract every record's frontmatter must satisfy
  soc.schema.json · module.schema.json · board.schema.json
scripts/validate.py   # the CI correctness gate (schema + source-or-omit + id/brand + refs)
templates/          # copy these to start a new record — see below
```

## Frontmatter contract

Every record is YAML frontmatter (`---` fenced) + a short human-readable prose
section below it. The frontmatter for each type must validate against its schema:

- soc → `schema/soc.schema.json`
- module → `schema/module.schema.json`
- board → `schema/board.schema.json`

Read the relevant schema file before filling a record — it is the authoritative
field list, types, and enums (not this doc, which will drift).

## Hard rules — non-negotiable

1. **Source-or-omit.** Every hard spec field must be backed by an entry in `sources:`.
   `field` is `"*"` for the whole record or a dotted path (e.g. `radios.bluetooth`).
   If you cannot verify a value against an official datasheet or vendor product page,
   **omit the field** — never guess, never estimate, never carry over a value from
   memory or another part without checking it against this part's source.
2. **id is kebab-case and equals the folder name.** `id: esp32-s3-wroom-1` must live
   at `data/modules/esp32-s3-wroom-1/module.md`. Same for socs and boards.
3. **Board `brand` equals its brand folder.** `data/boards/lilygo/…` → `brand: lilygo`.
4. **References must resolve.** A module's `soc:` and a board's `module:`/`soc:` must
   be an id that actually exists under `data/socs/` / `data/modules/`.
5. **Do not restate inherited specs.** If a value is already on the soc (or module),
   don't repeat it lower in the chain — reference it via `soc:`/`module:` instead.

## Required workflow

1. **SEARCH BEFORE ADD** — check the part doesn't already exist (dedup is your job,
   not the reviewer's):
   ```bash
   esp-atlas search "<name>"
   # or: GET /search?q=<name>
   ```
2. **Copy the matching template** from `templates/` (`soc.template.md`,
   `module.template.md`, or `board.template.md`) into the correct `data/` path.
3. **Fill it with datasheet-cited values.** Every field you set needs a `sources:`
   entry pointing at an official source; every field you can't verify, delete.
4. **Self-VALIDATE before opening a PR:**
   ```bash
   esp-atlas validate data/<path>/<file>.md
   # or: POST /validate  {"markdown": "<full file contents>"}
   ```
   Fix everything it reports. This runs the exact same checks as CI
   (`python3 scripts/validate.py`) — a clean local run means a green PR check.
5. **Open a PR** with your source links in the description.

## Also see

- [CONTRIBUTING.md](CONTRIBUTING.md) — human-facing contribution guide (same rules).
- [SPEC.md](SPEC.md) / [ARCHITECTURE.md](ARCHITECTURE.md) — project vision and data-flow design.
- [skills/esp-atlas/SKILL.md](skills/esp-atlas/SKILL.md) — this same workflow as a portable
  agent-framework skill.
- [llms.txt](llms.txt) — curated entry points for LLM tooling.
