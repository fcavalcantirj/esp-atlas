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
2. uncatalogued_with_code() → the top genuinely-new candidate (dedup already removed ports).
3. fetch_github_repo(github) → your citable ground truth (license, description, topics, stars).
4. Decide the target board: pick the ONE board_id from schema_enums that this firmware clearly
   runs on, using the repo/description as evidence. If you CANNOT map it to a catalogued board_id
   with evidence, STOP and report "needs human Issue" — do NOT force a wrong board.
5. author_firmware_record(): category from firmware_category enum ONLY; socs from soc_ids ONLY
   and only chips the repo names; license from the repo; sources = [{field,url,verified:"2026-08-27"}]
   pointing at the github url; a short factual body.
6. author_recipe(): recipe_id = f"{board}__{firmware_id}", board = the catalogued board_id,
   firmware = the firmware id, chip_family = a soc_id, status = "unverified", cite the source.
7. run_guard(). If ok=False, READ the error, fix the record(s), and retry (up to 3 times).
8. triple_validate(firmware_id, recipe_id) and report its result verbatim, plus the firmware_id
   and recipe_id. Be terse."""

jr = Agent(
    name="EspAtlasJr",
    model=Groq(id="openai/gpt-oss-120b"),
    db=SqliteDb(db_file=str(Path(__file__).parent / "jr_memory.db")),
    session_id="jr-firmware",
    tools=[tools.schema_enums, tools.uncatalogued_with_code, tools.fetch_github_repo,
           tools.author_firmware_record, tools.author_recipe, tools.run_guard, tools.triple_validate],
    instructions=INSTRUCTIONS,
    markdown=False,
)

if __name__ == "__main__":
    r = jr.run("Add the single top genuinely-new firmware and its recipe. Cite-or-omit, guard, "
               "then triple_validate and report the firmware_id, recipe_id, and the gates.")
    print("\n=== Jr says ===\n", (r.content or "").strip())
