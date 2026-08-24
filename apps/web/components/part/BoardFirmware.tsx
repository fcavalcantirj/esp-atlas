import RecipeGroupList, { type RecipeRow } from "@/components/RecipeGroupList";
import TrackedLink from "@/components/TrackedLink";
import { contributingUrl } from "@/lib/github";

// Board page section: every recipe targeting this board, grouped by trust
// tier, each with its Flash Wizard action (SPEC-wizard.md P2b).
export default function BoardFirmware({ rows }: { rows: RecipeRow[] }) {
  return (
    <section className="board-firmware" aria-labelledby="board-firmware">
      <h2 id="board-firmware">Firmware for this board</h2>
      {rows.length === 0 ? (
        <p className="muted">
          No firmware recipes yet —{" "}
          <TrackedLink href={contributingUrl()} linkType="contributing">
            help add one
          </TrackedLink>
          .
        </p>
      ) : (
        <RecipeGroupList rows={rows} />
      )}
    </section>
  );
}
