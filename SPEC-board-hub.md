# SPEC — "Plug my board" board hub (the interactive spine)

> **Status: DRAFT (2026-08-30).** The product thesis, not yet built. Turns esp-atlas
> from a *static reference you read* into a *workbench you plug into*. This is the
> unifying spine that gives purpose to the flash, verify, pin, project, and learning
> features — they stop being scattered pages and become **sections of one board hub**.
>
> Note on "web3": read as **modern, interactive, hands-on** — an app-like feel driven
> by the board in your hand — **not** blockchain. Nothing here is on-chain.

---

## 1. The vision (Felipe, 2026-08-30)

One loud, unmissable action on (almost) every page — **🔌 Plug my board**, fixed in
the header. You plug an ESP32 over USB, click it, and the page becomes *yours*: it
detects what you have and shows **everything for that board in one place** — live
debug, the firmwares that actually run on it (flashable right there), its pinout,
its specs, nice projects to try, and the learning to understand it. Flash, poke,
understand — all at one page, hands-on.

The current site answers "*which ESP32 for what?*" well but is read-only and inert.
This makes the board the **cursor of the whole site**.

## 2. The loud CTA

- **Fixed header button on all content pages: `🔌 Plug my board`.** High-contrast,
  the single loudest control. On a board page it reads `🔌 Verify this board`.
- **No passive detection is possible** (Web Serial exposes no port until a user
  gesture, and no plug-in event). The button **is** the connect action — clicking
  it calls `navigator.serial.requestPort()` (the device picker). Never render a
  "waiting for board…" state that implies passive sensing; there is none.
- **Chrome/Edge desktop only** (Web Serial). Everywhere else the button degrades to
  **"🔍 Find my board"** → the existing board search/wizard (type the name). Same
  destination (a board hub), different door.

## 3. Detection → disambiguation → confirm (the crux)

**A chip signature is not a board.** `detectChip()` (already built, `lib/verify-serial.ts`)
returns only `{ chipFamily, flashMb, psram, mac }`. An `esp32-s3 / 8MB / PSRAM`
signature matches a StickC-S3, a Cardputer, a CoreS3, and a bare DevKit alike.

The flow (reuses the built `/debug` "Read my board" + the pure `matchBoard()` boundary):

```
1. Connect (Web Serial gesture) → detectChip() → signature {chipFamily, flashMb, psram, mac}
2. matchBoard(signature) → CANDIDATE boards, narrowed by:
     - soc == chipFamily            (hard filter)
     - flash_mb / psram_mb match    (narrow)
     - MAC OUI → vendor hint        (e.g. Espressif / M5Stack / Seeed prefixes → rank)
3. Present candidates:
     - exactly 1 confident  → auto-open its hub, with a "not your board? change" link
     - several              → "Which one? [cards]" — user taps the real board
     - none                 → chip-family fallback hub (see §5) + "help us add this board"
4. Chosen board id is remembered for the session (a "your board" ribbon site-wide).
```

**Honesty rule:** never claim the exact board from the chip alone. The user always
confirms; auto-open only when candidates collapse to one.

## 4. Privacy & trust

- Detection is **100% local** — Web Serial in the browser, no backend, nothing
  (chip, MAC, flash contents) ever leaves the machine. State this in the UI.
- The MAC is used only client-side for the OUI vendor hint; it is never sent or logged.

## 5. The board hub (the payoff)

Once a board is known, its page (`/parts/[id]`) **is** the hub — a single page with
these sections, each a function of the cited repo, each **degrading gracefully** and
carrying a **contribute** affordance when data is thin:

| Section | Source (status today) | Empty-state |
|---|---|---|
| **⚡ Flash** — firmwares verified to run, flashable in-browser where possible | recipes + `SPEC-flash-catalog.md` (13/67 in-browser) | "these run, flash via their tools" (handoff) |
| **🔌 Live / Debug** — connect, read chip, serial monitor | `/debug` `VerifyBoard` (built) | Chrome-only note |
| **📌 Pins** — pinout + (later) a wiring/power planner | `board.io.gpio_pins` (15 devkits) + pin-planner (unbuilt) | "pinout not mapped yet — contribute" |
| **📋 Specs** — the cited datasheet facts | board record (built) | per-field cite-or-omit |
| **🚀 Projects** — nice things people built on THIS board | **new — content gap** (discovery lane) | "no projects yet — add one" |
| **📚 Learn** — what this chip/board is, how to start | **new — content gap** | short cited primer |

Sections render in the order above; a board with only specs still shows a coherent
page, not a broken one.

## 6. Where it lives / IA

- The **board page becomes the hub** — no new page type; the header CTA's job is to
  *get you to the right board page* (detect→confirm→deep-link `/parts/<id>`).
- A lightweight **"your board" session context** lets any page show a ribbon
  ("Working on: M5StickC-S3 · open hub") once detected — this is what makes the whole
  site feel like it's about the board in your hand.
- No new detection backend: the hub is still a static function of the repo + the
  local Web Serial read.

## 7. Data this vision requires (honest gaps)

1. **Projects entity** — "cool things on this board," cited. This is exactly the
   `SPEC-discovery` lane's `example`/`prompt-recipe` idea, **reborn as a hub section**
   instead of a standalone cron.
2. **Learn primers** — a short, cited "what is this / where to start" per chip family
   and per board. New content type (or a `learn` block on soc/board records).
3. **Full `gpio_pins` coverage** — pins exist for 15 devkits only; the Pins section is
   thin until this and the pin-planner (`SPEC-pin-planner`) land. **This vision is the
   reason to revive pin-planner — as a hub section, not a standalone.**

## 8. Architecture invariants (golden-rules-bound)

- **Repo-is-truth.** Every hub section is a pure function of cited records; detection
  only *selects* which record to show. No hub content is invented at runtime.
- **Smart API, dumb client.** Board/recipe/pin/project data comes from the API
  (`/parts`, `/manifest`, a new aggregate `/board/<id>/hub` if one query is cleaner);
  the client only owns the Web Serial glue (`detectChip`, `matchBoard`) and rendering.
- **Cite-or-omit** holds for projects and learn content exactly as for specs.
- **Chrome-only is a first-class degraded path**, never a dead end (→ Find my board).
- TDD, 80%+; `matchBoard` disambiguation is pure and unit-tested (it already is).

## 9. Phases

- **P1 — the spine.** Header `🔌 Plug my board` on all pages → detect → candidate
  disambiguation → confirm → deep-link to the existing board page. + "your board"
  ribbon. *(Composes only already-built pieces: detectChip, matchBoard, board page.)*
- **P2 — unify the hub.** Restructure `/parts/[id]` into the sectioned hub above,
  pulling Flash + Live/Debug + Specs together on one page (all already exist, just
  scattered).
- **P3 — Pins.** gpio_pins coverage + the pin/power planner section.
- **P4 — Projects + Learn.** The two new content types, board-scoped.

## 10. Acceptance (P1+P2, [REAL] gate)

On Chrome desktop: click **Plug my board** → pick the StickC-S3 → detection returns
`esp32-s3` → candidates narrow (MAC OUI = M5Stack) → confirm **M5StickC-S3** →
land on its hub showing: cited specs, the firmwares that run (Bruce/Launcher/… with
in-browser flash where `SPEC-flash-catalog` has landed it), and the live Debug
section — all on one page. Verified on real hardware, labelled [REAL].

## 11. Relationship to the other specs (this reshapes the consolidation)

This hub is the **spine** the fragmented specs were all part of:
- `SPEC-flash-catalog` / `SPEC-verify` → the **Flash** and **Live** sections.
- `SPEC-pin-planner` → the **Pins** section (revived as a component, not standalone).
- `SPEC-discovery` → the **Projects** section (reborn as board-scoped content).
- `SPEC-io-power` → the data behind **Pins/Specs**.

So the clean end-state is fewer, purpose-driven specs: **SPEC.md** (what it is),
**INTERFACE-SPEC.md** (how it runs), **SPEC-board-hub.md** (this — the interactive
product), **SPEC-flash.md** (the flash/verify/catalog detail the hub consumes),
**SPEC-espatlas-jr.md** (the agent that keeps it all cited & fresh).
