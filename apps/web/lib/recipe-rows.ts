import type { RecipeRow } from "@/components/RecipeGroupList";
import type { Firmware, Recipe } from "@/lib/api";
import { handoffFor } from "@/lib/esp-web-tools";

// A board page's "Firmware for this board" rows: recipes name their firmware
// only by id, so the display name/category and the handoff links come from a
// join against GET /firmware (small dataset). Shared by the server-rendered
// page and the client fallback so the flash action renders on both paths.
export function boardFirmwareRows(recipes: Recipe[], firmware: Firmware[], usbConnector: string | null): RecipeRow[] {
  const firmwareById = new Map(firmware.map((fw) => [fw.id, fw]));
  return recipes.map((recipe) => {
    const fw = firmwareById.get(recipe.firmware);
    return {
      recipe,
      href: `/firmware/${encodeURIComponent(recipe.firmware)}`,
      name: fw?.name || recipe.firmware,
      meta: fw?.category ?? null,
      handoff: handoffFor(fw),
      usbConnector,
    };
  });
}
