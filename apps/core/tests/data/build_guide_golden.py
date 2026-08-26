"""The GOLDEN QUERY MATRIX for real-Groq build_guide inference (SPEC-build-guide.md §7).

Every fast unit test around build_guide (test_build_guide.py) injects a fake/
dead LLM -- it proves OUR plumbing (grounding validation, deterministic board
retrieval, honest add-ons/notes) never breaks, but it cannot catch Groq itself
being inconsistent about WHICH firmware fits a goal worded differently than
the exact stub payload a unit test hands it.

This file pins the project->firmware intuition taught to Groq as few-shot in
`esp_atlas_core.build_guide.SYSTEM_PROMPT` -- the same table SPEC-build-guide.md
§3 documents. `scripts/build_guide_oracle.py` and
`apps/core/tests/test_build_guide_golden_live.py` both run this matrix against
REAL inference (a live HTTP endpoint or a real GroqClient).

Each entry:
    query            -- the plain-language build goal, verbatim as a maker
                         would type it
    expect_firmware  -- the required firmware id, a tuple of acceptable ids
                         (either is honest, e.g. bruce/esp32marauder both fit
                         "a wifi deauther"), or None when nothing in the
                         catalog should fit
"""

GOLDEN = [
    dict(
        id="plant_health_monitor",
        query="build a plant health monitor",
        expect_firmware="esphome",
    ),
    dict(
        id="led_sign",
        query="a scrolling LED sign",
        expect_firmware="wled",
    ),
    dict(
        id="offgrid_messaging",
        query="off-grid text messaging with a group in the backcountry",
        expect_firmware="meshtastic",
    ),
    dict(
        id="wifi_deauther",
        query="a wifi deauther",
        expect_firmware=("bruce", "esp32marauder"),
    ),
    dict(
        id="mechanical_robot",
        query="a line-following robot with motor control, no networking",
        expect_firmware=None,
    ),
]
