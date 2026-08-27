"""EspAtlas Jr — the agent (Agno body on free Groq gpt-oss-120b).

Wires the deterministic tools (tools.py) to an Agno agent with persistent SqliteDb memory.
Jr proposes; humans dispose. Run:  python agent.py            # author + guard, NO PR (debut gate)
                                   JR_OPEN_PR=1 python agent.py  # also open the cited PR
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

OPEN_PR = os.environ.get("JR_OPEN_PR") == "1"

INSTRUCTIONS = """You are EspAtlas Jr — the autonomous data-keeper for esp-atlas.
Your creed: quote-and-cite, or omit. NEVER invent a value. New firmware is authored `unverified`.
You propose via PR; a human merges. You never write `main`.

To add ONE new firmware this run:
1. Call uncatalogued_with_code to get the top candidate not yet in the atlas.
2. Call fetch_github_repo on its `github` url — this is your citable ground truth.
3. Author a record with author_firmware_record. CITE-OR-OMIT per field:
   - Set `license`, `category`, `capabilities` only from the repo metadata/description.
   - `socs` (required): include a chip ONLY if the repo/description names it; if you cannot
     cite the supported chips, DO NOT guess — stop and report that this one needs a human Issue.
   - `sources`: every entry = {field, url, verified:"2026-08-27"} pointing at the github url.
   - Write a short factual body describing what the firmware does + how it was discovered.
4. Call run_guard. If ok=False, fix the record and retry. If ok=True, you are done.
Report: the firmware id, the guard result, and (if asked) the PR url. Be terse."""

agent_tools = [tools.uncatalogued_with_code, tools.fetch_github_repo,
               tools.author_firmware_record, tools.run_guard]
if OPEN_PR:
    agent_tools.append(tools.open_pr)

jr = Agent(
    name="EspAtlasJr",
    model=Groq(id="openai/gpt-oss-120b"),
    db=SqliteDb(db_file=str(Path(__file__).parent / "jr_memory.db")),
    session_id="jr-firmware",
    tools=agent_tools,
    instructions=INSTRUCTIONS,
    markdown=False,
)

if __name__ == "__main__":
    task = "Add the single top uncatalogued firmware to the atlas. Author it, cite-or-omit, and run the guard."
    if OPEN_PR:
        task += " If the guard is green, open the cited PR and report its url."
    r = jr.run(task)
    print("\n=== Jr says ===\n", (r.content or "").strip())
