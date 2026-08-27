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
4. From the evidence, decide ONLY TWO things (this is all the judgment you make):
   a. `category` — from the firmware_category enum.
   b. `boards` — the list of catalogued board_ids the repo/README names it runs on. "M5StickC
      Plus2" → `m5stick-cplus2`; "Cardputer" → `m5cardputer`; "AtomS3" → `m5atoms3`; "Core2" →
      `m5stack-core2`. Include EVERY catalogued board it supports (coverage). Only board_ids from
      schema_enums are valid; ignore boards not catalogued.
   You do NOT choose socs or chips — those are DERIVED from the board records. NEVER pass a chip.
   A candidate is un-citable only if repo AND README give no board evidence → skip to the next.
   Only after ALL 5 candidates fail do you report "needs human Issue".
5. author_firmware_and_recipes(firmware_id, name, url, category, boards=[...], body, ...).
   `firmware_id` = ONE clean lowercase-hyphen slug of the tool/repo name (e.g. `m5stick-shark`,
   `porkchop`) — ONE record per firmware, NEVER per-version or with dates (`shark-2024-08-1` is wrong).
   capabilities=[...] — ONLY simple tokens from schema_enums['capabilities'] (e.g. wifi, ble, ir,
   display, gps); map README features to those tokens ("WiFi deauth"→wifi, "BLE spam"→ble); OMIT
   anything with no matching token — NEVER freeform phrases. maintainer=<repo owner>). This ONE call writes
   the firmware (socs derived from the boards), a recipe per board (chip derived), and the coverage
   run-case — all consistent by construction. If it returns {"error": ...}, that candidate had no
   usable catalogued board — move to the next candidate.
6. triple_validate(firmware_id, recipe_id=the first recipe id it returned). If a gate fails, READ
   it, fix, retry (≤3). Report the verdict + firmware_id + recipe_id. Be terse."""

def make_jr(session_id: str = "jr-firmware") -> Agent:
    """Fresh agent — batch draining passes a unique session_id per firmware so each authoring
    starts with clean context (no history bloat / cross-contamination across the batch)."""
    return Agent(
        name="EspAtlasJr",
        model=Groq(id="openai/gpt-oss-120b"),
        db=SqliteDb(db_file=str(Path(__file__).parent / "jr_memory.db")),
        session_id=session_id,
        tools=[tools.schema_enums, tools.uncatalogued_with_code, tools.fetch_github_repo,
               tools.fetch_github_readme, tools.author_firmware_and_recipes,
               tools.run_guard, tools.triple_validate],
        instructions=INSTRUCTIONS,
        markdown=False,
    )


jr = make_jr()

if __name__ == "__main__":
    r = jr.run("Add the single top genuinely-new firmware and its recipe. Cite-or-omit, guard, "
               "then triple_validate and report the firmware_id, recipe_id, and the gates.")
    print("\n=== Jr says ===\n", (r.content or "").strip())
