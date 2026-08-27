"""EspAtlas Jr — the agent (Agno body on free Groq gpt-oss-120b).

Wires the deterministic tools (tools.py) to an Agno agent with persistent SqliteDb memory.
Jr proposes; humans dispose. It authors a firmware+recipe pair, self-guards, and reports a
triple-validation. The PR is opened OUT of band, only after triple_validate passes (Felipe's
hard rule: never propose an unvalidated record).

    python agent.py         # discover -> author firmware+recipe -> guard/retry -> triple_validate
"""
import os
from pathlib import Path
from agno.agent import Agent
from agno.models.groq import Groq
from agno.db.sqlite import SqliteDb

import tools

# --- keys (box-local, mode 600, never in the repo) ---
for line in Path.home().joinpath(".config/jr/keys.env").read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1); os.environ.setdefault(k, v)

INSTRUCTIONS = """You are EspAtlas Jr — the autonomous data-keeper for esp-atlas.
Creed: quote-and-cite, or OMIT. NEVER invent a value. New records are `unverified`; you
propose via PR, a human merges, you never write `main`.

Add ONE genuinely-new firmware + its recipe this run:
1. schema_enums() → the ONLY valid values you may use (firmware_category, firmware_distribution,
   recipe_status, soc_ids, board_ids). Using anything else is forbidden.
2. uncatalogued_with_code(limit=5) → up to FIVE genuinely-new candidates. You author the FIRST
   one you can cite. DO NOT stop after candidate #1 — if one is un-citable, move to the next.
   (There are thousands uncatalogued; "nothing to propose" is almost never true — keep going.)
3. For each candidate until one works, read BOTH fetch_github_repo(github) AND
   **fetch_github_readme(github)** — the README is your richest source (API description/topics are
   often EMPTY, e.g. CatHack). Also use the candidate's own launcher name/description/category.
4. From that evidence determine: `category` (firmware_category enum), `socs` (the chips the repo
   names — most M5 Cardputer/AtomS3/StickC tools run esp32-s3; a "Cardputer" tool → board
   `m5cardputer`/esp32-s3, "StickC Plus2" → `m5stick-cplus2`), and the catalogued board_id(s) it
   supports. A candidate is only un-citable if BOTH repo AND README give no usable evidence — then
   skip to the next. Only after ALL 5 candidates fail do you report "needs human Issue".
5. author_firmware_record(): category from firmware_category enum ONLY; socs from soc_ids ONLY
   and only chips the repo names; license from the repo. Also POPULATE these when the repo
   evidences them (cite-or-omit — omit if unsure, never guess): `maintainer` (the repo owner),
   `capabilities` (from the description, e.g. wifi/ble/rf), `distribution` (from
   firmware_distribution enum — `releases` if the repo has GitHub releases, `web-flasher` if it
   has a web installer). sources = [{field,url,verified:"2026-08-27"}] per cited field, pointing
   at the github url; a short factual body.
6. author_recipe() for EVERY catalogued board this firmware supports — FIRMWARE COVERAGE, don't
   stop at one. For each board_id the repo evidences support for: recipe_id = f"{board}__{firmware_id}",
   board = the catalogued board_id, firmware = the firmware id, chip_family = that board's soc_id,
   status = "unverified", cite the source. Omit boards not in board_ids (cite-or-omit).
7. author_run_case(firmware_id) — register the firmware's coverage RUN case so the CI invariant
   `test_every_firmware_has_a_run_case` stays green (the gap that once red main).
8. run_guard(). If ok=False, READ the error, fix the record(s), and retry (up to 3 times).
8. triple_validate(firmware_id, recipe_id) and report its result verbatim, plus the firmware_id
   and recipe_id. Be terse."""

jr = Agent(
    name="EspAtlasJr",
    model=Groq(id="openai/gpt-oss-120b"),
    db=SqliteDb(db_file=str(Path(__file__).parent / "jr_memory.db")),
    session_id="jr-firmware",
    tools=[tools.schema_enums, tools.uncatalogued_with_code, tools.fetch_github_repo,
           tools.fetch_github_readme, tools.author_firmware_record, tools.author_recipe,
           tools.author_run_case, tools.run_guard, tools.triple_validate],
    instructions=INSTRUCTIONS,
    markdown=False,
)

if __name__ == "__main__":
    r = jr.run("Add the single top genuinely-new firmware and its recipe. Cite-or-omit, guard, "
               "then triple_validate and report the firmware_id, recipe_id, and the gates.")
    print("\n=== Jr says ===\n", (r.content or "").strip())
