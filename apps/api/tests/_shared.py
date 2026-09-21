"""Plain (non-fixture) test helpers shared across the apps/api tests.

Kept OUT of conftest.py on purpose: when CI runs `pytest apps/core/tests apps/api/tests
apps/cli/tests` together, a bare `from conftest import ...` resolves to whichever same-named
`conftest` module got imported first (apps/cli/tests/conftest.py), so the api tests failed to
import BOARD_PATH/client_with_llm. A uniquely-named module has no such collision. Fixtures
(built_db_path, client) stay in conftest.py — pytest auto-discovers those per-directory."""
import json

from fastapi.testclient import TestClient

from esp_atlas_core.firmware import get_firmware, recipes_for_firmware
from esp_atlas_core.paths import REPO_ROOT

from esp_atlas_api.main import create_app

SOC_PATH = REPO_ROOT / "data" / "socs" / "esp32-c6" / "chip.md"
BOARD_PATH = REPO_ROOT / "data" / "boards" / "espressif" / "esp32-c6-devkitc-1" / "board.md"


class StubLLM:
    """A fake GroqClient for /run tests -- no test here may reach real Groq."""

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete(self, system_prompt, user_prompt, temperature=0):
        self.calls.append(user_prompt)
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def client_with_llm(built_db_path, payload):
    app = create_app(db_path=built_db_path, llm_client=StubLLM(payload))
    return TestClient(app)


# Marauder's recipe set grows as Jr adds cited recipes: expectations are computed, never pinned.
def marauder_recipe_boards():
    return {r["board"] for r in recipes_for_firmware("esp32marauder")}


def marauder_boards_with_chip(chip):
    return {r["board"] for r in recipes_for_firmware("esp32marauder") if r.get("chip_family") == chip}


def marauder_recipe_citations():
    urls = {get_firmware("esp32marauder")["url"]}
    for r in recipes_for_firmware("esp32marauder"):
        urls |= {s["url"] for s in r.get("sources", []) if s.get("url")}
    return urls
