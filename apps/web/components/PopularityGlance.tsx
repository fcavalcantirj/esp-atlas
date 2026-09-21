import { popularityGlance, type PopularityInput } from "@/lib/format";

// SPEC-firmware-popularity.md §2: the card's "at a glance" popularity line.
// Not a link -- the card itself already links to the firmware. Shared by
// FirmwareCard (Firmware.popularity) and ExamplesGrid (FirmwareExample's own
// stars/forks), which read from different shapes but land on the same input.
export default function PopularityGlance({ popularity }: { popularity: PopularityInput | null | undefined }) {
  const glance = popularityGlance(popularity);
  if (!glance) return null;

  return (
    <span className="popularity-glance" aria-label={glance.ariaLabel} title={glance.title}>
      {glance.stars && (
        <span className="popularity-glance-metric">
          <span aria-hidden="true">★ </span>
          {glance.stars}
        </span>
      )}
      {glance.stars && glance.forks && <span aria-hidden="true"> · </span>}
      {glance.forks && (
        <span className="popularity-glance-metric">
          <span aria-hidden="true">⑂ </span>
          {glance.forks}
        </span>
      )}
    </span>
  );
}
