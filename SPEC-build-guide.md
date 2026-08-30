# SPEC — build guide: a grounded answer for "build a plant health monitor"

> Status: DRAFT (living). Extends `SPEC-home-explorer.md` §2 (intent-first home)
> and mirrors `esp_atlas_core.ask` / `esp_atlas_core.run_guide`'s grounding
> discipline (`SPEC-INDEX.md` G4). No build until this is agreed.

## 1. Problem

`esp_atlas_core.intent.parse_intent` already tells the truth about a goal like
*"build a plant health monitor"*: the catalog has no board field for "plant
health monitor", so it correctly returns `kind="unmapped"` rather than guess a
filter. Today the home stops there — the maker gets "I can't narrow this — try
Battery / Wi-Fi / Cheap / Native USB" and nothing else. That is honest, but not
**helpful**: the maker asked a project question, not a spec question, and the
catalog *does* have an answer — a firmware, real boards, and a plain statement
of the one part (a sensor) it doesn't catalog.

`build_guide(query)` is that answer. It runs exactly when `parse_intent` would
say `unmapped`, and turns "I can't narrow this" into "here's what you need":

> **Needs:** a Wi-Fi ESP32 board + a soil-moisture/humidity sensor (an add-on
> part, not a board esp-atlas catalogs).
> **Firmware:** ESPHome — reads sensors and reports to Home Assistant over
> Wi-Fi, no code required.
> **Boards:** three real, cheap Wi-Fi boards from the recipe graph.
> **Honest note:** esp-atlas doesn't catalog the sensor itself.

## 2. Non-negotiables (same contract as `ask()`/`run_guide()`)

1. **Firmware is constrained to the real catalog.** Groq picks ONE firmware id
   from the actual `list_firmware()` list handed to it in the prompt, or
   `null`. A returned id outside that list is rejected outright (treated as
   `null`), never surfaced.
2. **Boards are never chosen by the model.** Board selection is 100%
   deterministic: either the firmware's own `recipes_for_firmware()` set
   (filtered/ranked by real board columns), or — when no firmware fits — cheap
   Wi-Fi boards from `wizard()`. The LLM cannot name a board, so it cannot
   invent one.
3. **Every board's stated reason is grounded in that board's real record**
   (Wi-Fi standard/bands, price tier, battery connector) — never LLM prose
   about a board.
4. **Add-ons are named honestly.** Whatever the goal needs that isn't a
   firmware or a board (a sensor, camera, motor, relay...) is listed as
   `add_ons` and the response says plainly it is "not a board esp-atlas
   catalogs" — never silently dropped, never invented as a catalog item.
5. **Groq unreachable, rate-limited, or garbage → deterministic fallback,
   never a 500, never invented.** A keyword → firmware-category matcher
   (mirroring the few-shot intuition below) plus cheap-Wi-Fi boards from the
   catalog stands in.

## 3. Mechanism

`build_guide(query, llm_client=None, db_path=None)`:

1. **Firmware match, constrained.** Build a system prompt from the goal plus
   the real firmware catalog (`id`, `name`, `category`,
   `examples.describe_firmware()`'s one-liner). Groq replies JSON:
   `{"firmware_id": "<id or null>", "why": "<=1 sentence>", "traits":
   {"wifi": bool, "battery": bool, "cheap": bool}, "add_ons": ["..."]}`.
   - `firmware_id` is validated against `list_firmware()`; anything else
     becomes `null`.
   - `traits` default to `wifi=true, battery=false, cheap=true` when absent —
     matching the rule taught in the prompt: Wi-Fi is assumed for any
     reporting/IoT-shaped goal, battery only when the goal states or implies
     portable/wearable/outdoor, cheap unless a premium part is explicitly
     asked for.
   - `add_ons` are the physical, non-catalog things the goal needs (a sensor,
     camera, screen, motor...), sanitized (stripped, deduped, capped at 5).
2. **Board recommendation, deterministic.**
   - Firmware matched: `recipes_for_firmware(firmware_id)`, each board fetched
     via `search.get_part` (real columns), ranked by how well it fits the
     traits (battery connector present when `traits.battery`, `price_tier ==
     "cheap"` when `traits.cheap`, a Wi-Fi standard present when
     `traits.wifi`), capped at 4.
   - No firmware: `wizard({"type": "board", "radio": "wifi-4", ...})` (adding
     `battery`/`budget` needs per `traits`), same cap.
   - Each board's `why` is a short, deterministic sentence built from its own
     real fields — never generated prose.
3. **Add-ons / honest note.** `add_ons` from step 1 become the response's
   `add_ons`; `note` states plainly that esp-atlas catalogs firmware and
   boards, not those parts. When `firmware_id` is `null`, `note` also says so
   directly: "no ready-made firmware for this — you'd write your own on a
   Wi-Fi ESP32" — and boards are still recommended.

### Grounded project → firmware intuition (few-shot in the system prompt)

| Goal names... | → firmware |
|---|---|
| plant / sensor / monitor / environment / home / dashboard | ESPHome |
| LED strip / sign / lighting / matrix | WLED |
| off-grid messaging / long-range comms / GPS tracker | Meshtastic |
| Wi-Fi/BLE pentest, deauth, recon, wardriving | Bruce or ESP32 Marauder |
| BadUSB / keystroke injection | M5StickS3 RogueDuck |
| app-loader / multi-tool / firmware switcher | Launcher |
| nothing in the catalog fits (a robot, a synth, a purely mechanical build) | `null` |

### Deterministic fallback (Groq unreachable / garbage)

A keyword → firmware-id matcher applying the same table above by substring
match on the goal text (e.g. "led"/"strip"/"sign" → `wled`), used only when
the model call raises or its JSON is unusable. Boards still come from the same
deterministic path (recipe boards, or cheap-Wi-Fi `wizard()`), so the fallback
answer is exactly as grounded as the LLM-assisted one, just without a `why`
sentence or `add_ons` (a fallback can't invent what the goal's add-on nouns
are without reading the goal — it degrades to firmware+boards only, not to
guessing).

## 4. Response shape

```json
{
  "goal": "build a plant health monitor",
  "needs": [
    "A Wi-Fi ESP32 board to run ESPHome",
    "soil-moisture sensor -- not a board esp-atlas catalogs"
  ],
  "firmware": {"id": "esphome", "name": "ESPHome", "why": "Reads sensors and reports to Home Assistant over Wi-Fi, no code."},
  "boards": [
    {"board_id": "m5nanoc6", "board_name": "M5NanoC6", "why": "Wi-Fi wifi-6 (2.4, 5 GHz), cheap price tier"},
    {"board_id": "m5atoms3-lite", "board_name": "AtomS3 Lite", "why": "Wi-Fi wifi-4 (2.4 GHz), cheap price tier"}
  ],
  "add_ons": ["soil-moisture sensor"],
  "note": "esp-atlas catalogs firmware and boards, not soil-moisture sensor -- that's an add-on part you source and wire yourself."
}
```

`firmware` is `null` (never a fabricated id) when nothing in the catalog fits;
`boards` is still populated (cheap Wi-Fi boards) in that case.

## 5. API

`POST /build` — body `{"query": "<the goal, 1-500 chars>"}` (same shape as
`POST /intent`'s `IntentRequest`), response `BuildGuideResponse` (the shape
above). Always 200 — `build_guide()` never raises for a down/rate-limited/
garbage model, same contract as `GET /run/{firmware_id}`.

## 6. Web

Called from `HomeView` when `parseIntent()` returns `kind === "unmapped"`,
alongside (not instead of) the existing keyword-search fallback. Renders as
the **primary** answer — replacing the old "I can't narrow this" copy — via a
`BuildGuideAnswer` component that reuses `RunGuideAnswer`'s existing
`.run-guide*` CSS classes verbatim (no new visual system): the needs list, the
firmware line (linking to `/firmware/<id>`), the board cards (linking to
`/parts/<id>`), and the honest add-on note. The four spec clarifier chips
(Battery / Wi-Fi / Cheap / Native USB) move to a secondary "or narrow by spec"
row below the guide; the keyword matches stay collapsed under a `<details>`,
exactly as today.

## 7. Tests

- Unit (`apps/core/tests/test_build_guide.py`), fake LLM, no network:
  - "build a plant health monitor" → `firmware.id == "esphome"`, boards
    non-empty and all real (`get_part` resolves every `board_id`), `add_ons`
    include a sensor.
  - "a scrolling LED sign" → `wled`.
  - "off-grid text messaging" → `meshtastic`.
  - "a wifi deauther" → `bruce` or `esp32marauder`.
  - a `firmware_id: null` case → boards still non-empty, `note` states no
    ready-made firmware fits.
  - grounding validator: a fake LLM returning a non-existent `firmware_id` (or
    any board-naming field at all, since the module never reads one) never
    surfaces past validation.
- Golden inference matrix (`scripts/build_guide_oracle.py` /
  `apps/core/tests/data/build_guide_golden.py`): live-Groq,
  skip-gated the same way `test_intent_golden_live.py` is — not part of the
  blocking suite.
