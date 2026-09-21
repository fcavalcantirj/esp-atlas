import type { EventParams } from "@/lib/analytics";

/** part_view params for the firmware detail page -- same shape PartViewTracker uses for other part types. */
export function firmwareViewParams(id: string, maintainer: string | null, primarySoc: string | null): EventParams {
  return { part_id: id, part_type: "firmware", brand: maintainer, soc_ref: primarySoc };
}
