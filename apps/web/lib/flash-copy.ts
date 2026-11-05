import type { Recipe } from "./api.ts";

// What each trust tier actually asserts (SPEC-wizard "Trust tiers") — the flash
// panel says this in words so "validated" never means more than the record does.
// The unverified line stays source-neutral: that tier covers build-file harvests
// and third-party discovery leads alike, and the recipe's own caveat says which.
const TIER_CLAIM: Record<string, (board: string) => string> = {
  "known-good": (board) =>
    `Known-good on ${board} — cited to a source for this exact board (usually the firmware project listing it); flashed on real hardware only where its notes say so.`,
  reported: (board) => `Reported on ${board} — community-submitted and cited, not independently verified.`,
  declared: (board) => `Declared on ${board} — the project's own build files or board list name it; no flashable build confirmed yet.`,
  unverified: (board) => `Unverified on ${board} — listed as a plausible pairing from its cited source, not confirmed for this board.`,
  broken: (board) => `Broken on ${board} — known incompatible, or regressed at a version.`,
};

export function tierClaim(status: string, board: string): string {
  return (TIER_CLAIM[status] ?? ((b: string) => `${status} on ${b}.`))(board);
}

/** The recipe's own caveat (its cited `notes`), shown at the flash action; null when it has none. */
export function recipeCaveat(recipe: Pick<Recipe, "notes">): string | null {
  const notes = recipe.notes?.trim();
  return notes ? notes : null;
}
