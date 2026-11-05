// Public trust copy must match how the system works: Jr proposes, automated
// checks gate, and only some changes (new firmware, recipes, flashing claims)
// wait for a human maintainer. A blanket "humans review it" overstates that, so
// these phrases may only appear in a sentence that names what is held for review.
const HUMAN_REVIEW_PHRASES = ["checked by humans", "humans review it", "a human decides"];
const REVIEW_SCOPE_MARKERS = ["new firmware", "recipe", "flashing"];

/** Every sentence (or ;-clause) in `text` that claims human review without scoping it. */
export function unscopedHumanReviewClaims(text: string): string[] {
  return text
    .replace(/\s+/g, " ")
    .split(/[.;!?]/)
    .map((s) => s.trim())
    .filter((s) => {
      const lower = s.toLowerCase();
      return (
        HUMAN_REVIEW_PHRASES.some((p) => lower.includes(p)) && !REVIEW_SCOPE_MARKERS.some((m) => lower.includes(m))
      );
    });
}
