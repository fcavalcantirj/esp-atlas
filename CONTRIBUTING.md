# Contributing to esp-atlas

Thank you — a wrong number fixed or a board added makes this useful for everyone.

## The one hard rule

**Cite an official source for every spec, or leave it out.** No guessing. If you
can't verify a value against a datasheet or vendor product page, omit it (or note
the uncertainty in `notes:`) rather than inventing it. This rule is what makes the
data trustworthy.

## What to contribute

- **Fix a spec** — found a wrong value? Correct it and update/point to the source.
- **Add a board** — `data/boards/<brand>/<board-id>/board.md` (module/board schema coming; open an issue if it's not there yet and you want to add boards now).
- **Add a module** — `data/modules/<module-id>/module.md`.
- **Improve prose** — the human-readable section below the frontmatter.

## How

1. Fork, branch.
2. Edit or add the markdown file. Keep frontmatter conformant to `schema/`.
3. Run the gate locally:
   ```bash
   pip install jsonschema pyyaml
   python3 scripts/validate.py
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
