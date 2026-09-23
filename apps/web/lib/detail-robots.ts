// The two entity detail routes (parts/[id], firmware/[id]) fall back to a
// client-rendered shell keyed only by the raw id whenever fetchPartDetail /
// fetchFirmware doesn't return "ok" -- see api-server.ts's ApiResult. A
// not_found id should stay noindexed exactly as today. An errored/cold API
// must ALSO noindex: without this, a transient API outage would otherwise
// serve Google an indexable, canonical-less, title-is-the-raw-id page.
// Mirrors the hub pages' own cold-API guard (lib/firmware-sort.ts's firmwareRobots).

export type DetailStatus = "ok" | "not_found" | "error";

export function detailRobots(status: DetailStatus): { index: false; follow?: true } | undefined {
  if (status === "ok") return undefined;
  if (status === "not_found") return { index: false };
  return { index: false, follow: true };
}
