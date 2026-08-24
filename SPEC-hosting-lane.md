# SPEC — hosting-lane memory filter (wizard Step 2)

## Goal
Filter boards by memory capability to surface ones that can host a web server / run heavier apps, using the populated psram_mb / flash_mb fields.

## Data (verified 2026-08-24)
psram_mb populated 77/78; flash_mb 72/78. PSRAM tiers present: 0MB=42, 2MB=12, 4MB=1, 8MB=22 (>=2MB = 35 boards; >=8MB = 22).

## New wizard filters (needs)
- psram_min (int MB): return boards with psram_mb >= psram_min.
- flash_min (int MB): return boards with flash_mb >= flash_min.
- Both are MINIMUM-CAPABILITY filters -> subject to superset monotonicity: psram_min=2 result must be a superset of psram_min=4, which is a superset of psram_min=8 (same for flash_min).
- UNKNOWN HANDLING (critical): a board whose psram_mb is null/absent is EXCLUDED from any psram_min query with value > 0 (we cannot prove it meets the floor). Same for flash_min/flash_mb. A _min of 0 or unset imposes no filter (all boards included, even unknown). NEVER treat unknown as a matching 0; NEVER silently include unproven boards.
- Each active _min filter appends a reason line, consistent with existing _HARD_NEEDS, e.g. "psram_min=8: PSRAM >= 8 MB (headroom to host a web app); boards without PSRAM data excluded".

## UI (apps/web, Next.js)
- Toggle labeled "Runs a web server / heavy app" -> sets psram_min = 2. (Rationale: 2MB dedicated PSRAM is the has-headroom line vs the 42 zero-PSRAM boards; heavy workloads use the Advanced 8MB tier.)
- Advanced (collapsible) block with two dropdowns:
  - "PSRAM minimum": options [Any, 2 MB, 4 MB, 8 MB] -> psram_min
  - "Flash minimum": options [Any, 4 MB, 8 MB, 16 MB] -> flash_min
  - Dropdown options MUST be derived from the index facets (only offer tiers that actually exist in data) so there are no dead options.
- Active-filter chip: show "Can host a web server" when the toggle is on (psram_min>=2). Advanced selections render as "PSRAM >= N MB" / "Flash >= N MB" chips.

## Facets / index
Index psram_mb and flash_mb as facetable numeric fields and expose the available _min tiers via the facets path so the UI only offers non-empty options.

## API / CLI
API search and CLI both gain psram_min / flash_min params with identical semantics.

## Oracle invariants (extend apps/core/tests/test_wizard_oracle.py)
1. Superset monotonicity: for the psram tiers present in data, for a<b: wizard({"psram_min": a}) is a superset of wizard({"psram_min": b}). Same for flash_min. (Mirror the existing radio/band superset tests.)
2. Subset monotonicity: add psram_min/flash_min to the candidate_filters set so adding either to any base query never grows results.
3. No dead options: every _min tier the UI offers returns >= 1 board.
4. Unknown-exclusion: for any psram_min>0, no returned board has null psram_mb; likewise flash_min.
Also add psram_min/flash_min to scripts/wizard_dead_ends.py enumeration.

## Out of scope
Ethernet lane (0 boards have data - dropped). No change to SPEC-wizard.md (flash wizard) or freshness.

## Citation cleanup (fold in)
Tighten the psram_mb source URL for two boards from the generic ESP32-S3 datasheet to the M5Stack product docs (values stay 0 - already verified correct):
- m5dial psram_mb source -> https://docs.m5stack.com/en/core/M5Dial
- m5stamp-s3 psram_mb source -> https://docs.m5stack.com/en/core/StampS3
