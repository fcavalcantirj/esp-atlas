"""The GOLDEN QUERY MATRIX for real-Groq intent inference (SPEC-INDEX G4).

Every fast unit test around parse_intent (test_intent_oracle.py,
test_coverage_matrix.py) injects a fake/dead LLM -- they prove OUR plumbing
(validation, kind selection, firmware routing) never breaks, but they cannot
catch Groq itself being inconsistent about WHEN to infer a spec from a vague
noun. Measured on prod (2026-08-25): "cheap wearable" -> battery and
"esp32 with a camera" -> psram_min:2, but "waterproof gps tracker" -> nothing
and "build a plant monitoring system" -> nothing. Same rule, applied
unevenly.

This file pins the ONE consistent rule both the tightened SYSTEM_PROMPT
(esp_atlas_core.intent) and Groq's actual behavior must follow:

    Map a filter ONLY when a word explicitly names a spec (wifi, psram, a
    chip id, a form factor) OR the goal LITERALLY, unavoidably requires one
    (a camera needs a framebuffer -> PSRAM; something worn is portable ->
    battery; serving a web UI needs a network + memory -> Wi-Fi + PSRAM).
    A bare purpose noun -- monitor, tracker, system, gadget, detector,
    sensor -- names no board spec. It goes to `unmapped`, never a guessed
    filter.

Each entry:
    query          -- the plain-language goal, verbatim as a maker would type it
    expect_kind    -- the required parse_intent() "kind", or a tuple of
                      acceptable kinds when either is honest
    must_filters   -- filters that MUST be present with these exact values
                      (a subset -- the real parse may carry more)
    forbid_filters -- filter keys that must NOT appear (catches invention)
    must_unmapped  -- substrings (case-insensitive) that must each appear in
                      at least one `unmapped` entry
    filters_empty  -- when True, `filters` must be exactly {} (stronger than
                      forbid_filters, used for the unreadable/asdfqwer cases)

scripts/inference_oracle.py and apps/core/tests/test_intent_golden_live.py
both run this same matrix against REAL inference (live HTTP endpoint or a
real GroqClient) -- see either for how the checks below are applied.
"""

GOLDEN = [
    # --- firmware: never touches the model ----------------------------------
    dict(
        id="run_marauder",
        query="run marauder",
        expect_kind="firmware",
    ),
    dict(
        id="run_wled",
        query="run wled",
        expect_kind="firmware",
    ),

    # --- filters: explicit specs, and literal-requirement inferences -------
    dict(
        id="battery_wifi_psram_explicit",
        query="a battery board with wifi and 8mb psram",
        expect_kind="filters",
        must_filters={"battery": True, "radio": "wifi-4", "psram_min": 8},
    ),
    dict(
        id="wifi6_explicit",
        query="wifi 6 board",
        expect_kind="filters",
        must_filters={"radio": "wifi-6"},
    ),
    dict(
        id="soc_psram_explicit",
        query="esp32-s3 with 8mb psram",
        expect_kind="filters",
        must_filters={"soc": "esp32-s3", "psram_min": 8},
    ),
    dict(
        id="thread_zigbee_matter_explicit",
        query="thread zigbee matter smart-home mesh",
        expect_kind="filters",
        must_filters={"ieee802154": True},
    ),
    dict(
        id="web_dashboard_literal_wifi_psram",
        query="a board to host a web dashboard",
        expect_kind="filters",
        must_filters={"radio": "wifi-4", "psram_min": 2},
    ),
    dict(
        id="camera_literal_psram",
        query="esp32 with a camera",
        expect_kind="filters",
        must_filters={"psram_min": 2},
        must_unmapped=["camera"],
    ),
    dict(
        id="cheap_wearable_literal_battery",
        query="cheap wearable",
        expect_kind="filters",
        must_filters={"battery": True, "budget": "cheap"},
    ),
    dict(
        id="soc_usb_native_explicit",
        query="esp32-c6 with native usb",
        expect_kind="filters",
        must_filters={"soc": "esp32-c6", "usb_native": True},
    ),
    dict(
        id="ble_wearable_literal_battery",
        query="a bluetooth low energy wearable",
        expect_kind="filters",
        must_filters={"ble": True, "battery": True},
    ),
    dict(
        id="band_explicit",
        query="5ghz wifi board",
        expect_kind="filters",
        must_filters={"band": 5.0, "radio": "wifi-4"},
    ),
    dict(
        id="solar_literal_battery",
        query="a solar powered garden sensor",
        expect_kind="filters",
        must_filters={"battery": True},
        must_unmapped=["sensor"],
    ),
    dict(
        id="usb_keyboard_literal",
        query="a keyboard that types over usb",
        expect_kind="filters",
        must_filters={"usb_native": True},
    ),
    dict(
        id="doorbell_camera_wifi",
        query="a doorbell camera with wifi",
        expect_kind="filters",
        must_filters={"radio": "wifi-4", "psram_min": 2},
        must_unmapped=["camera"],
    ),

    # --- unmapped: a real goal, but nothing this catalogue can filter on ---
    dict(
        id="plant_monitor_no_invention",
        query="a plant health monitoring system",
        expect_kind="unmapped",
        forbid_filters=["battery", "radio"],
        must_unmapped=["plant"],
    ),
    dict(
        id="gps_tracker_no_invention",
        query="a gps tracker",
        expect_kind="unmapped",
        forbid_filters=["battery", "radio"],
        must_unmapped=["gps"],
    ),
    dict(
        id="water_plants_no_invention",
        query="something to water my plants",
        expect_kind="unmapped",
        forbid_filters=["battery", "radio"],
    ),
    dict(
        id="waterproof_unmapped",
        query="waterproof board",
        expect_kind="unmapped",
        must_unmapped=["waterproof"],
    ),
    dict(
        id="smart_plug_no_invention",
        query="a smart plug for the living room",
        expect_kind="unmapped",
        forbid_filters=["battery", "radio"],
        must_unmapped=["smart plug"],
    ),

    # --- unreadable: no signal at all to report -----------------------------
    dict(
        id="no_spec_named",
        query="a board for my project",
        expect_kind="unreadable",
        filters_empty=True,
    ),
    dict(
        id="gibberish",
        query="asdfqwer zzzz",
        expect_kind=("unreadable", "unmapped"),
        filters_empty=True,
    ),
]
