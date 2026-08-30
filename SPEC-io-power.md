# SPEC — I/O exposure & power delivery: the two axes esp-atlas is blind to

> Status: **SHIPPED (2026-08-30)** — the schema fields, the data, and the `io_heavy`
> ranking are live; the §9 "open questions" below are historical. Extends `SPEC.md`
> (entity model, source-or-omit), `SPEC-data-population.md` / `SPEC-espatlas-jr.md`
> (how EspAtlas Jr. authors + cites these fields), and feeds `SPEC-build-guide.md` §2,
> `SPEC-clarify.md`, and the `/ask` grounding (`INTERFACE-SPEC.md`). **Built & shipped.**
> Every field carries a source; `price_tier` stays the ONLY editorial exemption.
>
> **This spec was spiked against real sources before writing (§3).** The spike
> changed the design: one field I assumed was easy (`gpio_free`) is only
> *partially* machine-sourceable, and one I assumed hard (`rail_ma_max`) is
> published by some vendors. The feasibility tiers in §4 come from observation,
> not theory.

## 1. Problem — a real question esp-atlas answers wrong

r/esp32, verbatim:

> *"Does anyone know of any ESP board that has the ability for 4 LED strips and
> 4 fans? with GPIOs for sensors, also need uart data going in and out."*

Prod today (`POST /build`) returns the right **firmware** (ESPHome) and is honest
it doesn't catalog the strips/fans. Then it recommends **AtomS3-Lite** and
**NanoC6** — two of the most pin-*poor* boards we have — because `_board_score`
ranks on exactly three axes: `wifi_standard`, `battery_connector`,
`price_tier == cheap`. It is blind to the two axes this question is *about*:

1. **Usable GPIO count.** 4 strips + 4 fans + sensors + UART in/out ≈ 11 signal
   lines. AtomS3-Lite breaks out **6** (verified §3); NanoC6 fewer. Disqualified
   on pins — and esp-atlas can't see it.
2. **Drive capability.** The top human reply went straight here: *"which fans and
   LEDs? what voltage? how many amps?"* — because **no ESP GPIO sources motor/
   strip current.** A GPIO is a logic signal (tens of mA, configurable, abs-max);
   fans + WS2812 strips pull amps from an external rail through a MOSFET/driver.
   The right answer *leads* with that.

## 2. Two axes, two owners — the one design call not to get wrong

GPIO **count** and drive **current** live at different entity levels with
different authoritative sources. Conflating them is the trap.

| Axis | Entity | Authoritative source | Why there |
|---|---|---|---|
| Per-pad **drive current** (silicon electrical limit) | `soc` | **Espressif datasheet** — *DC Characteristics* table | The die defines it; every board on that SoC inherits it. |
| **Usable exposed GPIO count** (pads reaching a header, minus strapping/input-only/consumed) | `board` | **Vendor** spec page / pinout | The chip has ~40 pads; the *board* decides how many are broken out and free. Espressif cannot know this. |
| **Rail current to external loads** | `board` | **Vendor** spec page (port/rail rating) | A board-integration fact (regulator + connector), vendor-published or absent. |

The schema forces each field to the right owner via `sources[].field`; a board
record physically cannot cite Espressif for its pin count, nor vice-versa.

## 3. Spike — what real sources actually publish (verified 2026-08-26)

Checked before speccing, so the schema matches what can be *cited*, not wished.

**`soc.drive` — Espressif ESP32-S3 datasheet.** DC-Characteristics table gives
per-pad source/sink current. Real figures: default drive strength of GPIO19~20 ≈
**40 mA**, all other pads ≈ **20 mA**, each pad configurable across 4 levels
(`gpio_drive_cap_t` CAP_0..3). Source of truth is the **datasheet PDF** —
`https://documentation.espressif.com/esp32-s3_datasheet_en.pdf`. Note: the
ESP-IDF `gpio.html` API page names the enum levels but **states no mA values**, so
the datasheet PDF is the only citable source for the numbers. → *Feasible,
finite (~dozen SoCs), rarely drifts, PDF-extracted or hand-seeded once.*

**`board.io.gpio_exposed` — vendor spec page, INCONSISTENT.**
- AtomS3-Lite: page states **"IO Interface ×6"**, pins **G5/G6/G7/G8/G38/G39**,
  *"six GPIO female headers routed out"* → a clean, citable count.
  (`https://docs.m5stack.com/en/core/AtomS3%20Lite`)
- NanoC6: page shows only a *function pinmap image* + a Grove (G1/G2). **No stated
  exposed-GPIO count.** (`https://docs.m5stack.com/en/core/M5NanoC6`)
- → *Partially* machine-sourceable: present when the vendor prints "IO ×N + pin
  list", **absent (image-only) otherwise.** This is the field that breaks the
  naive "the data agent just scrapes it" assumption (§4, §5).

**`board.io.power_out.rail_ma_max` — vendor spec page, SPARSE.**
- NanoC6: **"Grove Maximum Output Current: DC 5V@600mA (depends on USB supply)"** →
  citable, with the USB-shared caveat.
- AtomS3-Lite: **no max-output-current stated** → omit.
- → Present where published, hard-omit otherwise (settles §9 Q3: no editorial
  fallback for power claims).

**Killer confirmation:** AtomS3-Lite exposes **6** GPIOs (cited) vs the ~11 the
Reddit goal needs — so the exclusion rule (§6) fires on a *real, cited* number,
not a guess. The fix is provably grounded for at least this board.

## 4. Feasibility tiers — build in this order, not all at once

The spike splits the work into three honesty tiers. **Tier A is cheap and high-
value; ship it first. Tier C is the hard part — spec it, don't pretend the daily
catalog agent already does it.**

| Tier | Fields | Source reality | Population lane |
|---|---|---|---|
| **A** | `soc.drive` | Datasheet, finite set, real numbers in hand | One-time seed / low-volume agent pass, datasheet-cited (§5.1) |
| **B** | `board.io.power_out`, `board.io.gpio_exposed` **where the vendor prints "IO ×N + pin list"** | Quoted spec text → cite-or-omit as usual | Normal EspAtlas Jr. authoring, existing gate (§5.2) |
| **C** | `board.io.gpio_free` for **image-only** boards | Split: the *subtraction rules* (strapping/input-only) are **official + machine-readable per-SoC** (§3a); only the *exposed-pad count* is derived | `soc.reserved_pins` auto-cited from Espressif design guidelines; board exposed-count vision-extracted **against the official reference schematic**, human-verified (§5.3) |

Tiers A+B alone fix the Reddit case (AtomS3-Lite is a Tier-B board with a cited
count). Tier C is the long-tail completeness push. **Felipe's refinement
(2026-08-26): the hard half of Tier C is not a guess — it's official data.**

### 3a. Spike addendum — the gpio_free subtraction is officially sourced

The ESP **Hardware Design Guidelines** *Schematic Checklist* page has a per-SoC
selector (dropdown) and states the reserved pins as **machine-readable text**,
verified 2026-08-26 on ESP32-H2: *"GPIO8, GPIO9, and GPIO25 are strapping pins,"*
plus an *"IO MUX Pin Functions"* table with per-pin restriction notes.
(`https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/`)

So `gpio_free` decomposes into an official half and a board half:

- **Which pads don't count** (strapping / input-only / USB-flash-tied) = a
  **SoC-level, official, auto-cited** fact → new field `soc.reserved_pins`
  (§3 addition). ~A dozen records; independently useful for `/ask`
  ("is GPIO9 safe? No — strapping pin").
- **How many pads reach a header** = the only genuinely board-level number. Quoted
  where the vendor prints "IO ×N + pin list"; for image-only boards, vision counts
  **against the official reference schematic**, not a blind read.

The pinout-vision step is therefore *last-resort and anchored to first-party
data* — it never auto-merges a derived number as if quoted (§7.4).

## 5. Data-agent population — how each field is actually authored & cited

Inherits `SPEC-data-population.md` §3 (discover → fan-out → author → **PR → CI
`schema`+`sources-live`+oracle → human merge**). Additions per tier:

**5.1 `soc.drive` (Tier A).** The SoC set is ~finite and rarely changes. A single
low-volume agent pass (or hand-seed) reads each SoC datasheet's DC-Characteristics
table, writes `drive.gpio_source_ma_max` / `gpio_sink_ma_max` with a
`sources[].field: drive.gpio_source_ma_max` → datasheet-PDF URL + `verified` date.
Because drive strength is *per-pad configurable*, the field is the **abs-max**;
per-pin defaults (e.g. S3 GPIO19/20=40, rest=20) go in `notes`, not the scalar.

**5.2 `board.io.gpio_exposed` + `power_out` (Tier B).** Folds into the existing
per-board authoring agent — no new capability. When the vendor page states an "IO
×N" count / explicit pin list / port current rating, the agent quotes it and cites
the spec-page URL. When the page has **only a pinout image**, the agent **omits**
these fields (source-or-omit, unchanged). Expected field-fill is therefore
**partial**, and that is correct — §7.3 makes absence neutral.

**5.3 `soc.reserved_pins` (official) + `board.io.gpio_free` derivation (Tier C).**
Two sub-steps, only the second is a judgment:
- **`soc.reserved_pins` — official, auto-cited (like `soc.drive`).** A low-volume
  SoC pass reads the ESP Hardware Design Guidelines schematic-checklist (per-SoC
  dropdown) + datasheet and records `strapping`, `input_only`, `usb_flash_tied`
  pin lists, each `sources[].field`-cited to the guidelines URL. Machine-readable
  text (§3a), ~a dozen records, rarely drifts.
- **`board.io.gpio_free` — derived, human-gated.** Input: the board's exposed-pad
  set (Tier-B quoted "IO ×N + pin list" where available, else vision over the
  vendor pinout **cross-checked against the SoC reference schematic**). Subtract
  `soc.reserved_pins` that are exposed + pins hard-consumed by onboard
  display/PSRAM → `gpio_free`. Record the math in `notes` ("14 header − 2 strapping
  − 0 input-only = 12 free"), cite the pinout URL, tag provenance `method: derived`
  (§9 Q2). **Human-verified before merge, always** — a derived number never lands
  on the same trust footing as a quoted one.

Because the subtraction inputs are now official SoC data, Tier C's *only* residual
judgment is the exposed-pad count for image-only boards — the rest is cited.

**Coverage report (per `SPEC-data-population.md` §4)** gains three field-fill
lines: `soc.drive` %, `board.io.gpio_exposed` % (quoted vs derived), `power_out` %
— measured-not-claimed, so we always know how much of the catalog the new ranking
can actually reason over.

## 6. Ranking change — `SPEC-build-guide.md` §2 stays deterministic

Model still never picks a board. One code-computed trait, one score term, one
exclusion — the LLM only sets a boolean, exactly as for `wifi`/`battery`/`cheap`.

- **New trait `io_heavy`** (`build_guide.py` `_DEFAULT_TRAITS`): `true` when the
  goal names multiple independent outputs/channels/strips/motors/relays. Default
  `false`.
- **Hard exclusion, not soft demotion:** when `io_heavy` and a board's **known**
  `io.gpio_free` (or `gpio_exposed` when free is absent) is below the goal's
  channel count, **drop it from the list.** Recommending a board that physically
  can't wire the project is today's bug; ranking it #4 doesn't fix it.
- **Absence is neutral:** a board with no `io` is never excluded and never
  invented a count (§7.3). It just can't win the `io_heavy` term.
- **`why`** appends `"{gpio_free} usable GPIO"` when present — the reason a board
  is chosen stays grounded in its own cited column.

### 6.1 Addendum (2026-08-26) — the hard exclusion alone still stranded the answer

**The bug, verified on a fresh index with real Groq.** `_boards_for_firmware`
draws its candidates ONLY from the matched firmware's own recipe graph
(`recipes_for_firmware`). For *"4 LED strips + 4 fans + sensors + UART"* Groq
correctly matches `esphome` — but esphome's recipe graph carried no
full-header devkit, only pin-poor m5 display/tiny boards. §6's hard exclusion
correctly dropped `m5atoms3-lite` (cited `gpio_exposed: 6` < the goal's ~11
channels), but the *remaining* recipe boards (`m5nanoc6`, `m5stack-core2`,
`m5stack-cores3`, `m5dial`) had no cited `io` at all — so §6's own "absence is
neutral" rule correctly kept them, and **no board in the pool could ever be
adequate**, because the adequate boards simply weren't recipe members. `/build`
recommended four boards that physically cannot drive the project, and the
shipped golden test never caught it: it stubbed a firmware (`wled`) whose
recipe graph happens to already carry two full-header devkits, so it exercised
ranking-among-adequate-boards, never the fallback machinery — the real,
`esphome`-shaped prod path had zero coverage.

**Two independent fixes, both real, neither a workaround:**

1. **Data — the recipe graph itself was incomplete.** ESPHome's `esp32:`
   component targets a standard Espressif devkit per chip variant by default
   (`esphome.io/components/esp32.html`: *"If `variant` alone is specified …
   the board configuration will be automatically filled using a standard
   Espressif devkit board"*) — so `esp32-devkitc-v4`, `esp32-s3-devkitc-1`,
   and `esp32-c6-devkitc-1` are genuine, standard `esphome` targets that were
   simply missing recipes. Added, schema-valid, cited. Once a firmware's own
   recipe graph legitimately includes an adequate board, no supplement is
   needed at all — this is the normal, preferred path.
2. **Code — a firmware's recipe graph can still be legitimately pin-poor.**
   Not every firmware has (or should have) a devkit recipe — a firmware built
   for a specific enclosure/display unit may never fit a bare devkit. For
   that case, `_boards_for_firmware` now checks whether the filtered recipe
   pool contains at least one board **CONFIRMED** adequate (`known gpio_free`/
   `gpio_exposed >= channel_count`) — not merely neutral (no cited count, kept
   by §6's absence rule but never proven to fit). If none is confirmed, the
   pool is supplemented with confirmed-adequate boards from the SAME
   deterministic `wizard()` pool `_boards_fallback` already draws from when no
   firmware fits at all — filtered by the same `wifi`/`battery`/`cheap`
   traits, never by a model. Groq still only ever sets the `io_heavy`
   boolean; which board wins is 100% deterministic.
3. **Ranking follows.** For an `io_heavy` goal, the combined pool (recipe +
   any supplement) ranks by each board's own known `gpio_free`/`gpio_exposed`
   **first** — higher wins — before the existing wifi/battery/cheap score, so
   a supplemented devkit actually surfaces instead of losing to a neutral
   board on the old three-axis score alone. A board with no cited `io` still
   sorts as if it had none: never excluded, never favored — absence stays
   neutral on both ends of §6, exclusion and ranking alike.
4. **Data — the pin-poor recipe boards themselves gained cited counts.**
   `m5nanoc6`, `m5stack-core2`, `m5stack-cores3`, and `m5dial` had no `io` at
   all, so they rode on §6's "absence is neutral" rule rather than being
   provably excluded. Each vendor pinout page states the board's *dedicated*
   Grove/Port expansion pins as an explicit pin list (Tier B: `M5NanoC6`'s
   HY2.0-4P Grove `G1`/`G2`; `Core2`'s `PORT-A/B/C`; `CoreS3`'s
   `PORT.A/B/C`; `Dial`'s `PORT.A/B`) — distinct from the shared 40-pin M-Bus
   header, which re-exposes pins already hard-consumed by the same board's
   onboard LCD/SD/camera/mic and so is **not** free for independent use and
   is excluded from the count. Subtracting each SoC's `reserved_pins`
   (strapping/input-only/usb-flash-tied) that land on those dedicated pins
   gives a derived `gpio_free` (Tier C, §5.3), math shown in `notes`, cited to
   the vendor pinout URL: NanoC6 `2 - 0 = 2`, Core2 `6 - 1 = 5` (G36 is
   `input_only`), CoreS3 `6 - 0 = 6`, Dial `4 - 0 = 4`. All four are honestly,
   provably below the ~11-channel goal — §6 now excludes them on a real
   number instead of merely tolerating their absence.

**Coverage.** `apps/core/tests/test_build_guide.py`'s io_heavy goldens now
drive the REAL recipe path: `firmware_id: "esphome"` (the id Groq actually
returns for this query), asserting `m5atoms3-lite` and the four newly-cited
pin-poor boards are excluded AND a full-header devkit surfaces with its
`gpio_free` in the `why`. A second golden (`firmware_id: "launcher"`, whose
recipe graph has no devkit recipe at all) drives the general
supplement-from-fallback mechanism directly, independent of the esphome-
specific recipe fix, so both fixes have real, isolated coverage.

### 6.2 Addendum (2026-08-26) — `io_heavy` is deterministic-first (BIBLE-PLAN.md A1)

Everything in §6 already assumed a correct `io_heavy` boolean; it didn't say
where that boolean had to come from, and until now it came solely from Groq.
That is a reliability gap on its own: Groq unreliably returns `io_heavy: false`
for goals that obviously need it — the exact symptom behind the §6.1 prod bug.
A boolean that the exclusion depends on for correctness should not depend on
an LLM's mood for a goal as explicit as *"4 LED strips and 4 fans."*

`build_guide.py` now computes `io_heavy` deterministic-first: `_deterministic_io_heavy(query)`
reuses `_CHANNEL_NOUN_RE` (the same regex `_channel_count` sums) to look at
each matched output group individually rather than only their total. It is
`True` when the goal names **>=2 independent multi-count output groups**
(e.g. "4 LED strips" AND "4 fans" — two groups, each counted >1) or **a
single explicit group of >=4 channels** ("4 fans" alone). `build_guide()` ORs
this onto Groq's own `io_heavy` boolean — `traits["io_heavy"] = traits.get("io_heavy",
False) or _deterministic_io_heavy(query)` — so Groq can still flag `io_heavy`
True for phrasings the regex misses (a tiebreak), but can never pull a
deterministically io_heavy goal back to `False`. The model still only ever
proposes a boolean; it is never the sole source of one.

A single-peripheral goal ("a plant monitor", "1 LED strip") stays `False`
under this predicate — one group, count of 1, doesn't cross either
threshold — so this changes nothing for the common non-io_heavy case, only
closes the reliability gap for goals that were always supposed to be
io_heavy.

## 7. The whole experience — this steps up all three lanes, not just /build

**7.1 `/ask` (the Groq answer steps up).** Today Groq can't answer "can an
AtomS3-Lite drive 4 fans?" with grounding. With `soc.drive` + `board.io` in
retrieval it can, *cited*: *"No — the AtomS3-Lite breaks out 6 GPIOs (M5 docs),
and any ESP32-S3 GPIO sources ~tens of mA abs-max (Espressif datasheet). 4 fans +
4 strips draw amps from an external 5–12 V supply through MOSFETs; the board only
sends the PWM/data pin."* Real, teaching, sourced — the esp-atlas voice.

**7.2 `/build` (the honesty note becomes load-aware).** When `io_heavy` and the
goal implies driven loads, `note` gains a grounded sentence from `soc.drive` +
`power_out`: *"An ESP GPIO switches, it doesn't power (~tens of mA). This board's
5 V rail is rated 600 mA, USB-dependent (vendor) — nowhere near 4 fans + 4 strips.
Budget external power + drivers, not a bigger board."* That is the top human
reply, now grounded in cited fields.

**7.3 `/clarify` (stop asking the generic triple).** We saw `confidence: 0.0 →`
the fixed `target/power/environment/interaction/budget` default order for this
query. The clarify catalog's governing rule is *every dimension maps to a real
filterable board column* (`power→battery_connector`, `target→wifi_standard`,
`budget→price_tier`, …). A 6th dimension earns its place only because `io.gpio_free`
now **is** such a column:

> **`channels`** — prompt *"One output, a few, or many?"*; `needs` delta
> `{gpio_min: N}` → `wizard()` filters `io.gpio_free >= N`. Same machinery as the
> existing five; Groq still only picks/orders the id.

This is the single dimension that most changes the board answer, and it lets
clarify anchor `io_heavy`/`gpio_min` up front instead of defaulting to the triple.
Flagged as a `SPEC-clarify.md` catalog change (§9 Q1), not assumed — but it is the
*same* `io.gpio_free` field the `/build` exclusion and the `/ask` grounding read,
so the three lanes stay one coherent axis.

## 8. Non-negotiables (inherit `SPEC.md` + population + build-guide)

1. **Source-or-omit, per field, right owner.** Every `drive.*` cites an Espressif
   datasheet; every `io.*` cites the vendor page. `sources[].field` names the
   subfield. No number ships uncited. **No number in this spec is "verified"** —
   the §3 figures are illustrative until a `sources` entry backs the record.
2. **`drive` MUST NOT appear on a board; `io` MUST NOT appear on a soc.** `esp-atlas
   validate` enforces both (new schema rule + a validate test).
3. **Absence is neutral, never inventive.** No `io` → not ranked below zero, never
   fabricated a count; excluded only on a *known* too-small number.
4. **Derived ≠ quoted (Tier C).** A pinout-derived `gpio_free` is human-verified,
   provenance-tagged, and auditable in `notes` — never merged as a plain quote.
5. **Model picks no board.** `io_heavy` is one boolean; all exclusion/ranking is
   deterministic code over real columns.
6. **TDD, oracle-first, UI last** (esp-atlas house rule): a `build_guide` golden
   for the 4-strip/4-fan query asserting (a) pin-poor boards excluded on cited
   counts, (b) load-aware note fires — **before** any code.

## 9. Open questions for Felipe

- **Q1 — clarify dimension.** Make channel/scale-count the 6th fixed
  `SPEC-clarify.md` dimension? (Fixes the `0.0 → default triple` fallback for
  these goals.) I lean yes.
- **Q2 — provenance for derived fields.** Tier C needs a `sources` kind for
  *derived-from-pinout* (vs. quoted). Extend `sources[]` with an optional
  `method: quoted|derived`, or keep quoted-only and push Tier C to `notes`-only
  until the schema grows? I lean: add `method`, so derived numbers are honest.
- **Q3 — Tier scope now.** Ship Tier A+B first (fixes the Reddit case, all quoted/
  cited), and schedule Tier C (pinout vision) as a separate phase? I lean yes —
  don't block the cheap grounded win on the hard long-tail.

## 10. Seed sources (added to `seeds.json`)

Per Felipe — the sources this spec relies on are wired into the data agent's
watch list so population/freshness can actually pull them (§10 entries added to
`seeds.json` `board_catalogs`): the M5Stack **docs** spec pages
(`docs.m5stack.com`, board `io`/`power_out` source) and the Espressif per-SoC
**datasheet PDFs** (`documentation.espressif.com`, `soc.drive` source). Both are
official + first-party; no ToS-violating scraping.

## 11. Not in scope

A driver-part catalog (MOSFETs, level shifters, PSUs). esp-atlas stays a
board/firmware atlas; §7.2's note points *at* those parts, it doesn't catalog
them — same boundary as sensors today.
