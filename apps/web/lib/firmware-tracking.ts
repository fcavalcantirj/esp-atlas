import type { EventParams } from "@/lib/analytics";

/** part_view params for the firmware detail page -- same shape PartViewTracker uses for other part types. */
export function firmwareViewParams(id: string, maintainer: string | null, primarySoc: string | null): EventParams {
  return { part_id: id, part_type: "firmware", brand: maintainer, soc_ref: primarySoc };
}

/** result_click params for a FirmwareCard on the /firmware browse surface -- origin is always "browse" here. */
export function firmwareBrowseClickParams(id: string): EventParams {
  return { part_id: id, part_type: "firmware", origin: "browse" };
}

/** firmware_sort params for the /firmware sort control -- the mode being picked and the mode it replaces. */
export function firmwareSortParams(target: string, from: string): EventParams {
  return { sort: target, from };
}

/** reveal_more params for the /firmware "Show more" button -- how many cards were showing before this click. */
export function firmwareRevealParams(revealed: number, total: number): EventParams {
  return { surface: "firmware", revealed, total };
}
