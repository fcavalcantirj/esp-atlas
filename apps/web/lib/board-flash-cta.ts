// Above-the-fold board-page CTA (page_view -> flash_open conversion is ~0
// today because BoardFirmware/#board-firmware sits after header, image, spec
// groups, chip chain, and body prose). Pure decision/copy logic, testable
// under plain `node --test` -- see format.ts's header comment for why this
// stays free of the "@/" alias and of any component import.
import type { EventParams } from "@/lib/analytics";
import { RECIPE_TIER_LABEL, RECIPE_TIER_ORDER } from "./format.ts";

interface FlashCtaRow {
  recipe: { status: string };
}

/** The CTA only earns its above-the-fold slot when the board actually has
 * something to flash -- never for non-board parts, unfetched (null) rows,
 * or a board with zero firmware recipes. */
export function shouldShowBoardFlashCta(partType: string, rows: FlashCtaRow[] | null): boolean {
  return partType === "board" && rows !== null && rows.length > 0;
}

/** Most trusted tier present among rows, known-good > reported > unverified
 * > broken (SPEC-wizard.md "the honesty layer") -- null only for zero rows. */
export function highestTrustTier(rows: FlashCtaRow[]): string | null {
  for (const tier of RECIPE_TIER_ORDER) {
    if (rows.some((r) => r.recipe.status === tier)) return tier;
  }
  return null;
}

/** "N firmware option(s) · <tier label>" -- the CTA's own copy. */
export function boardFlashCtaLabel(rows: FlashCtaRow[]): string {
  const count = rows.length;
  const countLabel = `${count} firmware option${count === 1 ? "" : "s"}`;
  const tier = highestTrustTier(rows);
  return tier ? `${countLabel} · ${RECIPE_TIER_LABEL[tier] ?? tier}` : countLabel;
}

/** board_flash_cta_click params: the board plus what the CTA advertised. */
export function boardFlashCtaParams(partId: string, rows: FlashCtaRow[]): EventParams {
  return { part_id: partId, count: rows.length, tier: highestTrustTier(rows) };
}
