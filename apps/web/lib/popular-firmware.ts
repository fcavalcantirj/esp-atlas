// Home page "Popular firmware" shelf (above-the-fold, passive discovery for
// the 87.5%-bounce / 2.2%-scroll home visitor who never types into the
// search box). Pure ranking, no fetch/JSX -- page.tsx is glue over this, same
// idiom as firmware-sort.ts.
import type { Firmware } from "@/lib/api";

export const POPULAR_FIRMWARE_LIMIT = 8;

/** Cite-or-omit: a firmware with no cited stars and no boards signal has
 * nothing to rank it as "popular" on, so it never qualifies for the shelf. */
function hasPopularitySignal(firmware: Firmware): boolean {
  const stars = firmware.popularity?.stars;
  const boards = firmware.boards;
  return (stars != null && stars > 0) || (boards != null && boards > 0);
}

/** Ranks `firmware` for the home shelf: cited stars desc, then boards-count
 * (how many boards it's verified on) as a tiebreak, then name for stable
 * ordering, capped to `limit`. Firmware with neither signal is excluded
 * rather than fabricated a rank (see `hasPopularitySignal`). */
export function selectPopularFirmware(firmware: Firmware[], limit: number = POPULAR_FIRMWARE_LIMIT): Firmware[] {
  return firmware
    .filter(hasPopularitySignal)
    .slice()
    .sort((a, b) => {
      const starsDiff = (b.popularity?.stars ?? 0) - (a.popularity?.stars ?? 0);
      if (starsDiff !== 0) return starsDiff;
      const boardsDiff = (b.boards ?? 0) - (a.boards ?? 0);
      if (boardsDiff !== 0) return boardsDiff;
      return a.name.localeCompare(b.name);
    })
    .slice(0, limit);
}
