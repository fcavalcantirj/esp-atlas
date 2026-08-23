# esp-atlas — Flash Wizard + Recipes spec

> Extends `SPEC.md`. Distinct from the existing **Wizard** (interface view #1, the
> "which ESP for X?" board picker). This is the **Flash Wizard**: pick a board →
> see what firmware is verified to run on it → flash it in the browser, with a
> disclaimer. Same core principle — the site is a pure function of a cited repo.

## Thesis
Every ESP32 firmware answers *"what runs on what"* differently and scattered:
`#define` board flags (NEMO), PlatformIO envs + per-board `User_Setup` headers
(Marauder, Crystal), board-named `.bin`s (Launcher `Launcher-<Device>.bin`),
M5Burner store entries, project-specific web flashers (Infiltra). None is
board-aware *at flash time* — ESP Web Tools detects the **chip**, never the
**board**. esp-atlas already owns the cited **board** layer. Add **firmware** and
**recipes** and it becomes the board-aware front door the ecosystem lacks.

Prior art proves the demand and the shape: **bmorcelli/Launcher** (MIT) is a
firmware app-store/loader spanning ~60 boards (M5Stack, LilyGO, CYD, Marauder,
misc) that already federates the **M5Burner API** + device lists into a catalog.
esp-atlas does not start from zero — Launcher's catalog and M5Burner are harvest
*sources*. esp-atlas's differentiation: an **open, cited recipe graph with trust
tiers**, not locked to one launcher or one store.

## Two new content types
Both are first-class entities like `brand` — **never** indexed into the queryable
parts table, never a `/search` or board-`/wizard` result.

### firmware — `data/firmware/<slug>/firmware.md`
A flashable project.
```yaml
id: esp32marauder
type: firmware
name: ESP32 Marauder
url: https://github.com/justcallmekoko/ESP32Marauder   # repo
category: pentest        # pentest | mesh | badusb | display | home | multi
maintainer: justcallmekoko
license: (SPDX)
distribution: [releases, web-flasher]   # m5burner | releases | web-flasher | esp-web-tools
manifest_url: https://.../manifest.json # optional — present iff it ships one
capabilities: [wifi, ble, sub-ghz, on-device-web-ui]
socs: [esp32, esp32-s2, esp32-s3]       # chip families the project builds for
sources: [...]                          # repo/wiki/release proving the above
```

### recipe — `data/recipes/<board>__<firmware>.md`
The **edge** — one board × one firmware, the atomic "what runs on what". This is
the collaborative, oracle-loopable unit.
```yaml
id: m5stick-cplus2__esp32marauder
type: recipe
board: m5stick-cplus2        # → data/boards/**  (must resolve)
firmware: esp32marauder      # → data/firmware/  (must resolve)
status: known-good           # known-good | reported | unverified | broken
chip_family: esp32           # must equal the board's soc family
firmware_version: v0.x.y     # the version this recipe was verified against
flash:
  method: esp-web-tools      # esp-web-tools | release-bin | m5burner | web-flasher
  manifest_url: ...          # for esp-web-tools
  bin_url: ...               # for release-bin (offset + chip_family → generated manifest)
  offset: 0x0
  env: ...                   # PlatformIO env / #define / User_Setup, for provenance
  partition: ...
verified_by: felipe
verified_at: 2026-08-23
notes: ...
sources: [...]               # issue / release notes / video / maintainer list proving it
```

## Trust tiers (the honesty layer)
- **`known-good`** — maintainer/official lists it, or esp-atlas verified on real hardware.
- **`reported`** — community-submitted, **cited** to a real source, not independently verified.
- **`unverified`** — oracle-bot-harvested (an env / flag / named `.bin` exists); plausible, no human cite yet.
- **`broken`** — known incompatible or regressed at a version.

The CI citation-audit proves a recipe is **valid + consistent + cited + live**
(board & firmware refs resolve; `chip_family == board.soc`; `sources` non-empty
and reachable) — **not** that it truly flashes or works. Same line `SPEC.md`
already draws for parts ("cited+live, not number-right"). The Flash Wizard always
renders the tier so the human judges. `firmware_version` makes version drift a
first-class field, never a surprise.

## Collaborative recipes
- Contribute a recipe by PR, or via a web form that opens the PR for you → lands as `reported`.
- CI runs the existing citation-audit gate.
- Maintainers promote `reported`/`unverified` → `known-good`.
- CODEOWNERS may extend to `data/firmware/<slug>` so project maintainers own their recipes.

## Oracle-loop (bot-maintained, humans merge)
Extends `SPEC.md`'s "oracle-loop bot opens PRs for missing/stale parts" to
recipes, with a **per-project adapter** because each declares support differently:

| Source | Declaration | Bot harvests → |
|---|---|---|
| NEMO | `#define STICK_C / CARDPUTER` | flags → boards |
| Marauder / Crystal | `platformio.ini` `[env:*]` + `User_Setup_*.h` | envs → boards |
| RogueDuck | single board + partition note | one recipe |
| Launcher | `platformio.ini` (one env per chip family) + `Launcher-<Device>.bin` releases | board-named bins → recipes **+ auto-manifest** |
| Launcher catalog / **M5Burner API** | aggregated firmware+device lists | cross-project `unverified` recipes (attributed) |
| any | release `.bin` asset names, README device lists | `unverified` recipes |

On each new firmware release the bot re-checks and opens "re-verify / version-bump"
PRs, flagging stale recipes — the maintenance answer to version drift.

## The Flash Wizard (interface view #4)
Board page → **Flash** → recipes for this board, grouped by trust tier → pick →
**consent gate** → engine branches on `flash.method`:
- **`esp-web-tools` + `manifest_url`** → embed `<esp-web-install-button>`; the
  browser does chip-detect + write. A chip/`chipFamily` mismatch is blocked by the
  tool itself — a hard safety net beneath our board-level assertion.
- **`release-bin`** (`bin_url` + `offset` + `chip_family`) → esp-atlas **generates
  the ESP Web Tools manifest on the fly**, pointing at the project's release asset
  (GitHub release assets are CORS-open) → one-click, **no rehosting**. The feature
  none of them have.
- **`m5burner` / `web-flasher`** → guided handoff: deep-link + per-board
  download-mode instructions (esp-atlas already models USB connector + form factor
  for exactly this).

Reverse view: a firmware page lists every board it runs on, by tier.

### Safety / disclaimer
Consent checkbox wired to the ESP Web Tools `activate` slot:
> esp-atlas asserts this board↔firmware link at the shown trust tier — it does not
> guarantee your specific unit or the current firmware version. Flashing can erase
> keys/config and can brick the device. At your own risk.

The `unsupported` slot covers non-Chrome/Edge (Web Serial is desktop Chromium
only; no iOS/mobile). Erase behavior via the manifest's `new_install_prompt_erase`.

## Not a recipe: libraries as capability signals
**ESPAsyncWebServer** (LGPL-3.0) is a *library*, not flashable firmware — never a
recipe target. It is a **capability signal**: firmware depending on it exposes an
on-device web UI. Model that as `capabilities: [on-device-web-ui]` on `firmware`,
not as a recipe.

## Phasing
- **P1** — `firmware` + `recipe` schemas; seed ~12 firmwares (Marauder, NEMO,
  Crystal, Infiltra, RogueDuck, Launcher, Bruce, MeshCore, Meshtastic, WLED,
  ESPHome, GhostESP) × their `known-good` boards, hand-cited. Render "runs on this
  board" on board/firmware pages. **No flashing yet** — pure data + schema, the
  brand-entity move again.
- **P2** — Flash Wizard button via ESP Web Tools for recipes that already carry a `manifest_url`; consent gate.
- **P3** — on-the-fly manifest generation from `release-bin` recipes.
- **P4** — oracle-loop harvesters (per-project adapters + Launcher/M5Burner sources) + the collaborative PR/form + tier-promotion workflow.

Recipe #1 is already `known-good` and self-cited: Marauder on an M5StickC S3, run
in Felipe's own lab.

## Anti-goals (extends SPEC.md)
- Never rehost binaries — link/cite the project's own releases (respects GPL-2.0,
  LGPL-3.0, and every upstream license; consistent with "cite, don't copy").
- Never claim an untested combo works — trust tiers enforce it.
- Not a firmware forum, not a store. The wizard flashes; it does not sell or host.
