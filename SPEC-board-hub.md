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

The flow reuses the built `/debug` "Read my board" (`detectChip()`) and the built
verify comparison (`lib/verify-board.ts`, detected-vs-one-known-board — for the
post-confirm reassurance badge). **The signature→candidates finder is NEW** — no
`matchBoard()` exists today; only the one-board verifier does.

```
1. Connect (Web Serial gesture) → detectChip() → signature {chipFamily, flashMb, psram, mac}
2. findCandidates(signature) [NEW — server-side, §12] → CANDIDATE boards, narrowed by:
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
  the client only owns the Web Serial glue (`detectChip`) + OUI hint + rendering.
- **Cite-or-omit** holds for projects and learn content exactly as for specs.
- **Chrome-only is a first-class degraded path**, never a dead end (→ Find my board).
- TDD, 80%+. The candidate finder is **new**; the verify comparison
  (`verify-board.ts`) is already pure & unit-tested and is reused for the
  post-confirm reassurance badge.

## 9. Phases

- **P1 — the spine.** Header `🔌 Plug my board` on all pages → detect → candidate
  disambiguation → confirm → deep-link to the existing board page. + "your board"
  ribbon. Detailed build spec in **§12**. *(Reuses detectChip + verify-board + board
  page; adds the candidate finder, OUI hint, detect-flow UI, session context.)*
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

---

## 12. P1 — detailed build spec (spec only, not built)

> Scope: the **spine** — header CTA → detect → disambiguate → confirm → deep-link to
> the existing `/parts/[id]` page + a session "your board" ribbon. **No hub
> restructuring** (P2), no pins/projects/learn. This section is API-first and
> build-ready; it defines contracts, states, edge cases, and tests — no code.

### 12.1 Reused vs new (grounded in the repo, 2026-08-30)
- **Reused (built):** `detectChip()` + `DetectedChip` (`lib/verify-serial.ts`); the
  verify comparison `verify-board.ts` (detected-vs-one-known → `VerifyResult`, for the
  post-confirm badge); board data `GET /parts` + `GET /parts/{id}`; `SiteHeader.tsx`;
  GA via `lib/analytics.ts`.
- **New:** (1) candidate-finder endpoint; (2) MAC-OUI vendor map; (3) the detect-flow
  UI (modal/drawer + state machine); (4) session "your board" context + header ribbon;
  (5) the CTA button in `SiteHeader`.

### 12.2 API-first — new endpoint `GET /boards/match`
Server owns the matching (smart API, dumb client).

- **Request (query params):**
  - `soc` **(required)** — lowercased chip family from `detectChip()` (e.g. `esp32-s3`).
  - `flash_mb` (optional int) — may be absent when the flash read failed.
  - `psram_mb` (optional int) — `0` means "read and absent"; omit means "unknown".
  - `vendor` (optional string) — brand slug the client resolved from the MAC OUI; a
    **ranking hint only**.
- **Behaviour:**
  - Hard filter: `board.soc == soc`.
  - Score each surviving board: `+2` exact `flash_mb` match, `+2` `psram_mb` match
    (presence *and* size), `+1` `vendor`/brand match. Ties broken by name.
  - Never invent; candidates come only from cited board records.
- **Response `200`:**
  ```
  { "soc": "esp32-s3", "soc_known": true,
    "candidates": [ { "id":"m5stick-s3","name":"M5StickC-S3","brand":"m5stack",
                      "flash_mb":8,"psram_mb":8,"form_factor":"stick",
                      "score":5,"matched":["soc","flash_mb","vendor"] }, ... ] }
  ```
  - `soc_known=false` when `soc` matches no SoC record → client shows the unknown-chip
    fallback (§12.4 state `nomatch`). Empty `candidates` with `soc_known=true` = SoC
    exists but no board records for it yet (contribute path).
- **Errors:** `400` if `soc` missing/blank.
- **Determinism/tests:** pure over the index; unit-tested (§12.7).

### 12.3 MAC-OUI vendor hint (new client-side data)
- Static table `oui-prefix → brand-slug` (Espressif, M5Stack, Seeed, LilyGO, Heltec…).
- Client resolves `detected.mac` → vendor → passes as `?vendor=`. **Never logged, never
  stored, never sent anywhere but this one ranking param.**
- Unknown/unread MAC → omit `vendor`; rank on flash/psram only.
- **Honesty:** OUI is a hint (resellers/clones exist) — it only *ranks*, never
  auto-confirms.

### 12.4 Detect→confirm state machine (client)
States and transitions (each async result carries a generation id; stale results are
dropped — same guard `FlashAction` already uses):

| State | Enter on | Shows | Next |
|---|---|---|---|
| `idle` | default | CTA `🔌 Plug my board` | click → `requesting` |
| `requesting` | click | native port picker | port → `detecting`; cancel → `idle` |
| `detecting` | port granted | "reading chip…" | ok → `matching`; throw → `error` |
| `matching` | got signature | spinner | `/boards/match` returns → `candidates`/`nomatch` |
| `candidates` | ≥1 candidate | 1 → pre-selected w/ "not it? change"; N → "Which one?" cards | pick → `confirmed` |
| `nomatch` | 0 candidates or `soc_known=false` | chip-family info + "help us add this board" (contribute link) | close / Find my board |
| `confirmed` | user picks board | run `verify-board` badge (chip match/mismatch/unknown), set session context | navigate `/parts/<id>` |
| `error` | detect threw / unsupported | actionable msg (hold BOOT, cable, Chrome-only) + "Find my board" | retry → `requesting`; close → `idle` |

- **Auto-advance rule:** only when candidates collapse to exactly one *confident* hit
  (unique max score above threshold); otherwise always show the chooser (matches §3
  honesty rule).

### 12.5 Browser gating & the degraded door
- Feature-detect `navigator.serial`. **Absent (Firefox/Safari/mobile)** → the CTA
  renders as **`🔍 Find my board`** → routes to the existing board search/index. Never a
  disabled "plug" button, never a dead end.

### 12.6 Session "your board" context + routing
- On `confirmed`: store `{id, name}` in a React context backed by `sessionStorage`
  (**no cookie, no backend, MAC never stored** — repo-is-truth).
- `SiteHeader` shows a ribbon on every page: `Working on: <name> · open hub ▸` with a
  clear/change control. Persists per browser session only.
- `confirmed` → `router.push("/parts/<id>")`. (Rendering the verify badge *inside* the
  board page is P2; P1 shows it in the confirm step only.)
- **Analytics:** `plug_click`, `detect_success{soc}`, `detect_fail{reason}`,
  `candidates_shown{n}`, `board_confirmed{id}`, `find_my_board_fallback`,
  `unknown_board{soc,flash_mb,psram_mb}` — the last one is the **"boards to add"
  backlog signal**.

### 12.7 Tests (TDD, 80%+ floor)
- **API `/boards/match`:** soc hard-filter; flash/psram scoring; vendor boost; ranking
  order; `soc_known=false`; empty-but-known; `400` on missing soc. Fixtures use real
  ESP32 boards (e.g. `esp32-s3` → {m5stick-s3, m5cardputer, m5stack-cores3,
  esp32-s3-devkitc-1}).
- **OUI resolver (pure):** known prefix → brand; unknown → none; malformed mac → none.
- **State machine (pure reducer):** every transition incl. cancel, error paths,
  generation-guard drops a stale result, auto-advance only on unique-confident.
- **Feature-detect fallback:** no `navigator.serial` → CTA = Find my board.

### 12.8 Acceptance ([REAL] gate, P1 only)
Chrome desktop, real hardware:
1. Click **Plug my board** → picker → plug **M5StickC-S3** → detect `esp32-s3`.
2. `/boards/match?soc=esp32-s3&flash_mb=8&psram_mb=8&vendor=m5stack` returns candidates
   with M5 boards ranked top by the OUI boost.
3. Tap **M5StickC-S3** → chip-match badge → ribbon reads `Working on: M5StickC-S3` →
   page navigates to `/parts/m5stick-s3`.
4. Firefox: CTA reads **Find my board** → search works.
5. Plug a board absent from the catalog → `nomatch` → contribute link; a
   `unknown_board` event fires.
Label the run [REAL].

### 12.9 Out of scope (P1)
Hub section restructuring (P2), pins/planner (P3), projects/learn (P4), any
`SPEC-flash-catalog` recipe conversion. P1 changes **no** board/recipe data.

### 12.10 Open questions for Felipe
1. **Detect UI shape:** a centered modal, or a right-side drawer (so the page stays
   visible behind it)? Default proposed: **modal** for P1 simplicity.
2. **Auto-advance threshold:** auto-open the board when a single candidate scores ≥ 4
   *and* is unique — OK, or always show the chooser even for one hit?
3. **Ribbon persistence:** session-only (proposed) or remember the last board across
   visits (localStorage)?
