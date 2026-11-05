import { serverApiBase } from "./api-server.ts";
import { loadAtlasCatalog, type AtlasCatalogResult } from "./atlas-load.ts";

export type { AtlasCatalogResult } from "./atlas-load.ts";

/** Server entry point. Uses the same API resolution and tagged cache as the
 * existing catalog pages, without their empty-array failure fallback. */
export function fetchAtlasCatalog(): Promise<AtlasCatalogResult> {
  return loadAtlasCatalog(serverApiBase());
}
