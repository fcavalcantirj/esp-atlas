# SPEC — Flashable recipe catalog (turn handoffs into in-browser flashes)

> **Status:** DRAFT (2026-08-30). Authority for the flash *UI/pipeline* remains
> [`SPEC-wizard.md`](./SPEC-wizard.md); authority for the *data model* is
> [`schema/recipe.schema.json`](./schema/recipe.schema.json). This spec governs
> **how we populate `flash` on recipes** so that firmwares people actually search
> for (Bruce, Marauder, Nemo…) flash in the browser instead of punting to a handoff.

---

## 1. Goal

Convert `flash.method: web-flasher` / `m5burner` recipes (handoffs) into real
**in-browser flashes** — `esp-web-tools` (project manifest) or `release-bin`
(project GitHub bin, proxied) — **only where a cited, allowlist-compatible
artifact provably exists**. Where none exists, the handoff is *correct* and stays
(cite-or-omit). Net effect: the wizard's Install button appears for the firmwares
in the top GSC demand cluster (bruce, marauder, launcher, nemo).

**North-star metric:** in-browser-flashable edges rise from **13/67** today toward
covering every recipe whose firmware+board pair has a proxiable binary or a
CORS-served manifest.

## 2. Verified current state (2026-08-30, [REAL] — read from repo + live)

- Recipes: **67 edges · 30 boards · 18 firmwares.** Methods: **42 web-flasher · 13
  release-bin · 4 m5burner** · rest none. **`manifest_url` count: 0.**
- `build_manifest()` (`apps/core/.../flash.py`) builds a manifest **only for
  `release-bin`**; `esp-web-tools` recipes use their own `manifest_url`; everything
  else is a handoff.
- The bin proxy (`/api/flash-bin`) allowlist is **exactly**: `github.com`,
  `objects.githubusercontent.com`, `release-assets.githubusercontent.com`.
  **`m5burner-cdn.m5stack.com` is NOT allowlisted.**
- Chip families that can flash: `esp32, -s2, -s3, -c2, -c3, -c5, -c6, -c61, -h2,
  -p4` (effectively all ESP32) — chip family is **not** the limiting factor.
- Live proof the pipeline works: `GET /api/manifest/m5stick-s3__launcher.json` →
  `200` with a valid ESP Web Tools manifest; `..__bruce.json` → `404` (web-flasher).

## 3. Non-goals (explicitly rejected — this is the double-checked correction)

1. **Do NOT bulk-ingest `api.launcherhub.net/giveMeTheList`.** [REAL] It is the
   **M5Burner community app store**: 2,668 entries / 2,420 names, chip-family-tagged
   (`esp:"32"`), **not board-mapped**, mostly junk (`"12345"`, `"2222"`, WIP games),
   bins on **m5burner-cdn (not proxiable)**. Ingesting it would destroy the
   "every fact cited to an official source" contract. It may serve later as a
   *popularity signal only*, never as a data source.
2. **Do NOT join on `api.launcherhub.net/devices`.** [REAL] It returns **61
   category aggregates** (`{category, source, firmware_count,…}`), not devices.
3. **Do NOT auto-import bmorcelli `manifest.json` device ids.** [REAL] It is 85
   curated Launcher devices, but its ids **do not match** esp-atlas board ids
   (overlap = 0: `m5stack-cplus2` vs `m5stick-cplus2`, CYD-* absent, etc.). Adding
   those boards is a **separate, datasheet-cited board-authoring effort** (Jr's
   board lane) with an explicit id-mapping table — out of scope here.
4. **Do NOT add boards or firmwares** in this spec. Recipes only reference boards
   in `data/boards/**` and firmwares in `data/firmware/` that already exist.
5. **Do NOT rehost binaries.** The proxy transits, never stores (SPEC-wizard).

## 4. Data sources (the only sanctioned ones)

Per recipe, `flash` is populated from the **firmware project's own official
artifacts**, in this precedence:

| Source | Yields | Method to set |
|---|---|---|
| Project GitHub **release** asset (`.bin`, per board) on an allowlisted host | proxiable binary | `release-bin` + `bin_url` (+ `offset`) |
| Project-published **ESP Web Tools `manifest.json`** on a **CORS-enabled** host | direct manifest | `esp-web-tools` + `manifest_url` |
| Project ships only its own flasher / M5Burner-only | nothing proxiable | keep `web-flasher` / `m5burner` (handoff) |

The firmware record already tells you what to expect: e.g. `data/firmware/bruce`
declares `distribution: [releases, web-flasher, esp-web-tools, m5burner]` and
`url: https://github.com/pr3y/Bruce` — so Bruce is a **prime conversion target**.

> **Harvester gotcha ([REAL], 2026-08-30):** the firmware repo (`pr3y/Bruce`) and
> the **release-asset repo can differ**. Bruce's binaries are published under
> **`BruceDevices/firmware`** releases (tag `1.16.1`, 61 `.bin` assets), *not*
> `pr3y/Bruce/releases` (0 assets). The harvester must resolve the actual releases
> location, and Bruce's own `bruce.computer/manifest.json` is **404** — so for Bruce
> the path is `release-bin`, not `esp-web-tools`.

## 5. Method decision ladder (per board×firmware edge)

```
1. Does the firmware project publish a per-board .bin in a GitHub release
   on an allowlisted host, for this board's chip_family?
      → YES: method=release-bin, bin_url=<release asset>, offset (default 0x0),
             cite bin_url to the release URL. Verify /api/manifest/<id>.json → 200.
2. Else, does the project publish an ESP Web Tools manifest.json served with
   CORS (Access-Control-Allow-Origin) for this board?
      → YES: method=esp-web-tools, manifest_url=<manifest>, cite it.
             Verify the manifest fetches cross-origin from esp-atlas.com.
3. Else → keep handoff (web-flasher / m5burner). Record WHY in `notes`. This is
   a correct outcome, not a failure.
```

**Trust tier** follows the evidence, unchanged from SPEC-wizard: `known-good` only
if the project's own device table lists the board OR it was flashed on real
hardware; else `reported`; auto-harvested-without-human = `unverified`.

## 6. Recipe authoring rules (schema-bound, [REAL] against recipe.schema.json)

- `flash.method ∈ {esp-web-tools, release-bin, m5burner, web-flasher}`.
- `release-bin` requires `bin_url`; `esp-web-tools` requires `manifest_url`.
- `chip_family` **must equal** the referenced board's `soc`.
- `board` must exist in `data/boards/**`; `firmware` in `data/firmware/`.
- `sources`: ≥1, each `{field, url, verified: <date>}`. The `bin_url`/`manifest_url`
  gets its own `field`-scoped source; compatibility gets a `field: '*'` source
  pointing at the project's supported-devices list.
- **Cite-or-omit per field.** No `bin_url` you did not resolve from an official
  release. No invented offsets.

## 7. API surface (API-first — already exists, no new endpoints)

- `GET /api/manifest/{recipe_id}.json` — 200 manifest for a flashable `release-bin`
  recipe, 404 otherwise. **Unchanged.** New recipes must make it return 200.
- `GET /api/flash-bin?recipe=<id>` — same-origin proxy, allowlist-gated. **Unchanged.**
- If any target firmware needs a host beyond the three allowlisted GitHub hosts,
  that is a **deliberate, reviewed** addition to `ALLOWED_BIN_HOSTS` with an SSRF
  re-check — call it out in the PR, do not widen silently.

## 8. UX companion (Felipe's point #2 — separate PR, references SPEC-wizard)

- The `<esp-web-install-button>` for a flashable recipe should be **always
  rendered**, not hidden inside a collapsed `<details>`. Clicking it is the
  WebSerial entry point (`navigator.serial.requestPort()` — the device picker).
- **There is no passive board detection** (WebSerial exposes no un-granted port
  and no plug-in event). "Disabled until board connected" is **not
  implementable**; the button *is* the connect action. The only pre-click gate is
  the brick-risk consent, which should be a one-time disclaimer, not a per-recipe
  hidden checkbox.
- On a board page, surface which recipes are in-browser-flashable vs handoff so a
  StickC-S3 owner sees "Launcher, Bruce → flash here; others → their tools" at a
  glance.

## 9. Scope & phases

- **Phase 1 (this spec's acceptance):** the top GSC-demand firmwares — **bruce,
  launcher, esp32marauder, m5stick-nemo** — across the boards we already hold,
  converted where §5 yields a citable artifact.
- **Phase 2:** remaining 14 firmwares, same ladder.
- **Phase 3 (separate spec):** expand the board catalog (bmorcelli's 85 devices,
  datasheet-cited, id-mapped) — Jr's board lane, not here.

## 10. Acceptance criteria ([REAL] gates, not [UNVERIFIED])

1. **StickC-S3 × Bruce flashes in-browser.** [REAL-GROUNDED] The artifact exists:
   `Bruce-m5stack-sticks3.bin` at
   `github.com/BruceDevices/firmware/releases/download/1.16.1/…` (allowlisted host,
   302→GitHub asset host which is also allowlisted). So `m5stick-s3__bruce` becomes
   `method: release-bin`, `bin_url` = that asset, cited to the release. Gate: on a
   deployed build `GET /api/manifest/m5stick-s3__bruce.json` → **200**, and on Chrome
   desktop with a real S3 the Install button appears and the port picker opens.
   Label the flashed result [REAL].
   - *Fallback (only if a future upstream change removes the bin):* prove the
     conversion on `esp32marauder`/`launcher` and document Bruce's blocker in
     `notes`. Never fake a flash.
2. At least the four Phase-1 firmwares re-audited; every converted recipe passes
   `validate.py` + `check_sources_live.py` + returns a valid manifest/CORS fetch.
3. No recipe references a non-allowlisted bin host without a reviewed
   `ALLOWED_BIN_HOSTS` change.
4. Count of in-browser-flashable edges reported before/after in the PR body.

## 11. Engineering rules (golden-rules-bound)

- **TDD, 80%+ floor.** Tests: manifest built for each new `release-bin` recipe;
  404 preserved for genuine handoffs; allowlist rejects off-list hosts; schema
  validates every new/edited recipe. Fixtures use ESP32 boards/firmwares (domain
  examples), never lorem/animals.
- **Cite-or-omit is guard-enforced** (schema + sources-live + oracle). A recipe
  with an unresolvable `bin_url` must fail the guard, not ship.
- File ceiling ~900 lines; recipes are data, harvester code obeys it.
- **Bot proposes, humans dispose** — harvested recipes land as PRs, `unverified`
  until a human promotes the tier.
- No metered API keys; GitHub release reads use unauthenticated REST or the
  existing tooling.

## 12. Open questions for Felipe (genuine no-default decisions)

1. **Harvester owner:** one-shot delegate pass, or wire it as a proper **Jr lane**
   (recurring, cited, PR-only)? The Jr lane is more work but is the durable answer
   and reuses the guard.
2. **esp-web-tools vs release-bin preference** when a project offers both: release-bin
   is proxied (no CORS dependency, survives upstream CORS changes) but re-fetches
   through us; esp-web-tools is lighter but depends on the project's CORS. Default
   proposed: **prefer release-bin** for resilience. OK?
3. Phase-1 firmware set confirmed as {bruce, launcher, esp32marauder, m5stick-nemo}?
