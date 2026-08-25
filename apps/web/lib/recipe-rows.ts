import type { RecipeRow } from "@/components/RecipeGroupList";
import type { Firmware, PartRecord, Recipe } from "@/lib/api";
import { brandLabel } from "@/lib/brand";
import { handoffFor } from "@/lib/esp-web-tools";

// A board page's "Firmware for this board" rows: recipes name their firmware
// only by id, so the display name/category and the handoff links come from a
// join against GET /firmware (small dataset). Shared by the server-rendered
// page and the client fallback so the flash action renders on both paths.
export function boardFirmwareRows(
  recipes: Recipe[],
  firmware: Firmware[],
  boardName: string,
  usbConnector: string | null,
): RecipeRow[] {
  const firmwareById = new Map(firmware.map((fw) => [fw.id, fw]));
  return recipes.map((recipe) => {
    const fw = firmwareById.get(recipe.firmware);
    const firmwareName = fw?.name || recipe.firmware;
    return {
      recipe,
      href: `/firmware/${encodeURIComponent(recipe.firmware)}`,
      name: firmwareName,
      meta: fw?.category ?? null,
      boardName,
      firmwareName,
      handoff: handoffFor(fw),
      usbConnector,
    };
  });
}

/** A firmware page's "Runs on these boards" rows — the same edge from the other side. */
export function firmwareBoardRows(recipes: Recipe[], parts: PartRecord[], firmware: Firmware): RecipeRow[] {
  const boardById = new Map(parts.map((part) => [part.id, part]));
  const handoff = handoffFor(firmware);
  return recipes.map((recipe) => {
    const board = boardById.get(recipe.board);
    const boardName = board?.name || recipe.board;
    return {
      recipe,
      href: `/parts/${encodeURIComponent(recipe.board)}`,
      name: boardName,
      meta: board ? brandLabel(board) : null,
      boardName,
      firmwareName: firmware.name,
      handoff,
    };
  });
}
