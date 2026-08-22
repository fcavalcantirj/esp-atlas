# Contributing to esp-atlas

Thank you — a wrong number fixed or a board added makes this useful for everyone.

> **AI coding agent?** Read [AGENTS.md](AGENTS.md) instead (or in addition) — it
> covers the same rules with the search/copy-template/fill/validate/PR workflow
> spelled out for automated contributors.

## The one hard rule

**Cite an official source for every spec, or leave it out.** No guessing. If you
can't verify a value against a datasheet or vendor product page, omit it (or note
the uncertainty in `notes:`) rather than inventing it. This rule is what makes the
data trustworthy.

## What to contribute

- **Fix a spec** — found a wrong value? Correct it and update/point to the source.
- **Add a board** — `data/boards/<brand>/<board-id>/board.md`, start from
  [`templates/board.template.md`](templates/board.template.md). See
  [COVERAGE.md](COVERAGE.md) for the backlog of known boards still needing
  coverage.
- **Add a module** — `data/modules/<module-id>/module.md`, start from
  [`templates/module.template.md`](templates/module.template.md).
- **Add a SoC** — `data/socs/<soc-id>/chip.md`, start from
  [`templates/soc.template.md`](templates/soc.template.md).
- **Improve prose** — the human-readable section below the frontmatter.

Before adding anything new, search the dataset to avoid a duplicate:
```bash
esp-atlas search "<name>"      # or: GET /search?q=<name>
```

## How

1. Fork, branch.
2. Copy the matching file from `templates/` and fill it in, or edit an existing
   record. Keep frontmatter conformant to `schema/`.
3. Self-check the file(s) you touched, then the full gate:
   ```bash
   pip install jsonschema pyyaml
   esp-atlas validate data/<path>/<file>.md   # or: POST /validate
   python3 scripts/validate.py                # same checks CI runs, whole dataset
   ```
4. Open a PR and fill in the template — including your source links.

## Data model

Three layers, specs declared once and inherited: **soc → module → board**. A board
references its `module`; a module references its `soc`. Don't re-type a chip's radio
specs on every board — reference the chain.

Each hard spec field must be backed by an entry in `sources:` (`field` may be `"*"`
for the whole record, or a dotted path like `radios.bluetooth`).

## Licensing

Data contributions are under **CC-BY-SA 4.0**; code under **MIT**. By submitting a
PR you agree to license your contribution accordingly.
