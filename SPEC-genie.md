# SPEC — esp-atlas Genie (intent-driven flash agent · vision + contract)

> Status: **VISION / DRAFT — NOT BUILT (2026-09-14, Felipe + agent co-design).**
> Living document, to be revised before any code. Defers to `SPEC-INDEX.md` on every
> ownership/vocabulary conflict. This is the north-star product doc: what the Genie is,
> why it wins, how the experience feels, the tool/endpoint contract, and the explicit
> build-order guardrails (especially "grounded-first, custom-model-later") so no future
> session over-builds a fine-tune before the data earns it.

---

## 0. Why this spec exists — the pivot that produced it

esp-atlas spent months building a **census/SEO** play (map the whole ESP32 universe,
rank on Google). On 2026-09-14 the telemetry and the competitive map killed it:

- **Organic search is a minor channel.** Real traffic is **Direct + Reddit**; organic
  Google is a single-digit-per-day tail. The "1,000,000 users by Nov 27" SEO goal is
  detached from the instrument by ~5 orders of magnitude on every channel.
- **Every catalog lane is already owned:** `espboards.dev` owns the ESP32 content hub
  (80+ tutorials, sensors, ESPHome UI Designer); `esp32pins.com` owns interactive
  pinouts; `pamfinds.com` owns datasheet-cited buying/comparison **with a JSON API +
  llms.txt for AI agents** — which is esp-atlas's own stated identity, but broader and
  already shipping.
- **Exactly one quadrant is unowned:** the **firmware↔board compatibility + flashing**
  axis. None of the three do "what firmware runs on my board, will it fit, flash it."
  esp-atlas already built the data for it (compat engine, recipes, flash rail, verify
  rail). That is the wedge.

**The reframe:** esp-atlas is not a site people visit. It is a **live, agent-callable
Genie** — you bring a board and an *intention*; it does the rest. This doc is that
product.

## 1. The thesis (one paragraph)

> The user never says "Bruce." They say *"I want to spoof my garage remote."* They own
> the **intent**; the Genie owns the **how**. The Genie collects two things — **your
> board** and **what you're trying to do** — identifies the hardware (camera-first,
> cable-second), tells you the honest truth about what's physically possible, resolves
> your intent to the right firmware (existing now, generated later), verifies the silicon
> before it writes, flashes it, checks whether it actually worked, and **gets more
> assertive every time** because every outcome becomes cited data. A genie in a bottle,
> not a search box. Art and techy merged into one living entity.

## 2. Positioning / market fit

| Site | Owns | esp-atlas here? |
|---|---|---|
| espboards.dev | ESP32 content hub: tutorials, sensors, troubleshooting, ESPHome UI Designer | No — their strength |
| esp32pins.com | Interactive pinout explorer (deep, single-purpose) | No day-one (our pinout coverage ~14%); a *v2 superset capability* of the Genie, not a competing site |
| pamfinds.com | Datasheet-cited buying/comparison across all hardware; JSON API + llms.txt for agents | Barely — they ship *passive* data; we ship *active tools an agent calls*. Different category. |
| **esp-atlas Genie** | **Intent → firmware → fit-checked → flashed, for any ESP32/M5 board** | **The unowned quadrant.** |

Audience: the ESP32/M5 "make it *do* something" crowd — **all firmware, not pentest-only**
(ESPHome, Tasmota, Meshtastic, WLED, Bruce, Marauder, Nemo, …). Proven demand: the
top organic page was `/firmware/launcher`; the warm referral vein is the Cardputer /
Claude-Code / r/esp32 community — Felipe's native domain.

## 3. The experience — two modes

- **Boardless** — roughly today's explore UI. Fine as-is.
- **Board detected** — a different world: a **conversational, animated agent-face**
  greets you; the screen **paints your actual board**, matrix-style, with every firmware
  that runs on it; you say what you want to do; it filters, tells the truth, and flashes.
  **Pure art** — animations, a living entity, "not a website."

The agent-face + credits + model all live *behind* the face. The user only ever meets
the Genie.

## 4. The core loop (identify → matrix → verify → flash)

Camera-first, cable-second — the cable appears exactly where it's unavoidable (flashing),
and doubles as a safety gate.

1. **Identify — cable-free** `[NEW]`: send a photo or use the webcam → vision
   (claude-code-eyes) → *"this is a Cardputer."* Paint the matrix. No wires to explore.
2. **Intent** `[NEW]`: user states what they want to do (or browses all firmware).
3. **Resolve + gate** `[NEW brain over BUILT data]`: intent → capability → does the
   board *physically* support it → the honest, filtered set of firmware.
4. **Verify — plug in** `[BUILT: SPEC-verify.md]`: Web Serial + esptool-js read-only
   `detectChip()` reports **chip family / flash size / PSRAM**; matched against the cited
   board record (match / mismatch / unknown). This is the **pre-flash guardrail**: photo
   said Cardputer → silicon must confirm ESP32-S3 / 8MB / 8MB PSRAM before flash unlocks.
   Catches "photographed a Cardputer, plugged a plain ESP32" *before* writing the wrong
   firmware.
5. **Flash** `[BUILT: SPEC-wizard.md / esp-web-tools P2b]`: write the chosen `.bin`.
6. **Outcome** `[NEW]`: did it work? Log it (see §7).

**Honest boundaries of verify:** silicon can only report chip/flash/PSRAM — *not* pins,
radios, or dimensions (those stay datasheet facts). Serial identifies the **chip**, not
the **board**; board identity comes from the photo, the chip confirms what's underneath.

## 5. The Genie's brain — intent → capability → hardware → firmware `[NEW — the one genuinely new data/logic layer]`

The compat engine knows *firmware × board*. The Genie needs
**intent × capability × physical-hardware × firmware**:

- **Capability / use-case metadata** on each firmware — "what can this *do*"
  (sub-GHz replay, BLE spam, IR, WiFi tools, home-automation, LED control, …). New,
  cited, gated the same way every esp-atlas field is (cite-or-omit).
- **Physical-capability gating (the RF-honesty rule — first-class):** an ESP32 is
  **2.4 GHz only.** "Garage remote" is **315/433 MHz sub-GHz** — impossible without a
  **CC1101 / sub-GHz module**, and if the door is rolling-code (KeeLoq) it *cannot be
  replayed at all.* The Genie's first magic is **knowing you can't**, and saying so:
  *"Your Cardputer can't transmit 433 MHz as-is — you'd need the M5 RF433 unit or a
  CC1101; and post-2010 doors are usually rolling-code, which can't be replayed."*
  A genie that flashes junk is a toy; a genie that gates on physical reality and tells
  the truth is the moat. Never fabricate a capability the hardware doesn't have.

## 6. Now vs future — same pipe, swappable firmware source

- **Now** `[flash-existing]`: intent → *pick an existing firmware* that does it → flash.
  Free tier. Near-zero marginal cost (retrieval + browser flash).
- **Future** `[generate-on-the-fly]`: intent → *generate firmware* → compile → flash.
  Paid tier. Real cost (LLM inference + compile toolchain per request).

Architect the loop so "where the `.bin` comes from" is a swappable source — the future
slots in without a rewrite.

## 7. Model decision — GROUNDED-FIRST, custom-model-LATER (build-order guardrail)

**Do not build a fine-tune or RL model to ship the Genie.** The moat is the **cited
data** (hardware + firmware-capability + outcome feedback), not custom weights.

- **Day 1:** a **grounded frontier model + RAG** over esp-atlas's cited data. Shippable
  now — no training loop, no eval drift, no dataset we don't yet have. Grounding, not
  baking. (Consistent with esp-atlas's whole creed: quote-and-cite or derive, never from
  memory/weights.)
- **From day 1:** log every **intent → firmware → did-it-actually-work** outcome. This is
  both the "gets more assertive" loop *and* the corpus that could one day fund a model.
- **v3+, only if the data justifies it:** fine-tune / RL-from-flash-outcomes on the
  accumulated corpus. This is the long-term research moat — *unlocked by shipping the
  grounded version*, not a prerequisite for it.

**Rule:** never gate the product on a model that needs data we don't have. Collect the
data by shipping the grounded version.

## 8. The compounding loop ("more assertive every time")

Jr's soul applied to intent: every outcome (§4.6) is a **cited data point** — did this
firmware, on this board, achieve this intent? Confidence compounds from *outcomes*, never
from assertion. Same discipline as the catalog: accumulate verified truth, surface
uncertainty honestly.

## 9. Business model — freemium on the cost line

The free/paid split falls exactly on the **compute cost** line:

- **Free:** retrieve an existing firmware + flash it. Near-zero marginal cost. Give it away.
- **Paid (credits):** generate custom firmware on the fly — the expensive unit
  (metered LLM + compile per request). **X credits/day, buy more.** Credits *must* cover
  COGS: the product's generation calls burn esp-atlas's **own metered key** (never a
  personal / Hermes-infra key, per estate rules).

## 10. Contract surface (API-first — the tools an agent/the face calls)

Each tool is cite-or-omit and returns provenance where it asserts a fact. `[BUILT]` =
data/logic exists today; `[NEW]` = to build; `[FUTURE]` = paid/later.

| Tool | Purpose | Key inputs → outputs | Status |
|---|---|---|---|
| `identify_board(image \| description)` | Name the board cable-free | photo/webcam or text → board id + confidence | `[NEW]` (claude-code-eyes) |
| `verify_board()` | Confirm silicon before flash | Web Serial → {chip, flashMb, psram} vs cited → match/mismatch/unknown | `[BUILT]` (SPEC-verify) |
| `what_runs_on(board)` | Every firmware that runs on a board | board id → cited firmware list | `[BUILT]` (compat engine) |
| `resolve_intent(intent, board)` | Intent → capability → honest firmware set | NL intent + board → ranked firmware + physical-gating verdict + caveats | `[NEW]` (the brain, §5) |
| `fit_check(board, firmware)` | Will it fit / physically work | board+fw → fits? (flash size, chip, **required radios/modules**) + reason | `[BUILT]` extended with capability gating |
| `flash_recipe(board, firmware)` | The flashable recipe / one-click | board+fw → recipe + esp-web-tools handoff | `[BUILT]` (SPEC-wizard) |
| `record_outcome(...)` | Log did-it-work for the compounding loop | board+fw+intent+result → cited outcome | `[NEW]` (§8) |
| `generate_firmware(intent, board)` | Custom firmware on the fly | intent+board → compiled `.bin` | `[FUTURE]` (paid, §6) |

The same contract is exposed three ways off one source of truth: **MCP tools**
(agent-native, the differentiator vs pamfinds), **REST**, and **llms.txt**.

## 11. Built vs new (grounded in the real repo)

- **Built:** firmware→board compat engine (82 firmware, cited `signals.json`); recipes;
  flash wizard (esp-web-tools, P2b); verify/debug rail (chip/flash/PSRAM); clarify/
  build-guide; JSON API + llms.txt.
- **New:** `identify_board` (camera/vision), the intent→capability→hardware brain
  (`resolve_intent` + capability metadata + physical gating), `record_outcome`, the
  agent-face experience + the living matrix UI, credits/freemium.
- **Future:** `generate_firmware` (generate-on-the-fly, paid).

## 12. Non-goals / honest boundaries

- Not the general hardware catalog (pamfinds) or the pinout specialist (esp32pins) or the
  tutorial hub (espboards) — the Genie *may* absorb pinout as a v2 capability, but does
  not fight those sites as a site.
- Never fabricate a firmware capability or a hardware capability the source can't back
  (§5 RF-honesty rule).
- No fine-tune/RL before the outcome data justifies it (§7).
- Jr's law still holds: bot proposes, humans dispose; deterministic guard sovereign; auto
  = unverified; no ToS-violating scraping; official APIs rate-limited.

## 13. Open questions (to revise next)

- Exact schema for capability/use-case metadata and its cited sources.
- `identify_board` mechanism: on-device vision vs a hosted model; accuracy/confidence
  thresholds; fallback to one-tap board pick.
- Credits: pricing, daily free allotment, payment rail, abuse limits.
- Which surface ships first — MCP server, REST, or the web experience — and the first
  vertical slice (candidate: intent-first mock on the Cardputer, then wire to built data).
- How `resolve_intent` ranks and how the physical-gating verdict is presented in the UI.

## 14. References

Internal: `SPEC-INDEX.md` (arbiter) · `SPEC-verify.md` (verify rail) ·
`SPEC-firmware-boards.md` (compat engine) · `SPEC-wizard.md` / flash catalog (flash rail) ·
`SPEC-demand-steering.md` (Jr allocation) · `JR.md` / `SPEC-espatlas-jr.md` (the maintainer,
crons, guard, PR pipeline) · `SPEC.md` (entity model).

External context: espboards.dev · esp32pins.com · pamfinds.com · bmorcelli Launcher ·
esp-web-tools / esptool-js (Web Serial flashing).
