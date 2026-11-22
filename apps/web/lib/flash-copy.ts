import type { Recipe, RecipeClaim } from "./api.ts";

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

/** The build-target line is owner-approved copy (2026-11-22). It names the commit and env only from the
 * record's own claim and never says "runs on": the fact is configuration, not a build or a hardware test. */
function buildTargetClaim(board: string, claim?: Pick<RecipeClaim, "sha" | "env"> | null): string {
  const where = claim?.sha && claim?.env
    ? ` at commit ${claim.sha.slice(0, 7)} selects this board's definition (env ${claim.env}).`
    : " selects this board's definition.";
  return `Build target for ${board}: the project's PlatformIO config${where} Configuration only: not built or tested on hardware.`;
}

export function tierClaim(status: string, board: string, claim?: Pick<RecipeClaim, "sha" | "env"> | null): string {
  if (status === "build-target") return buildTargetClaim(board, claim);
  return (TIER_CLAIM[status] ?? ((b: string) => `${status} on ${b}.`))(board);
}

/** The recipe's own caveat (its cited `notes`), shown at the flash action; null when it has none. */
export function recipeCaveat(recipe: Pick<Recipe, "notes">): string | null {
  const notes = recipe.notes?.trim();
  return notes ? notes : null;
}
