// Missing entity IDs are noindexed and return 404 from their page routes.
// Temporary API failures throw before a detail response is sent. Keep the
// error branch as a defensive guard if a caller later adds a fallback view.

export type DetailStatus = "ok" | "not_found" | "error";

export function detailRobots(status: DetailStatus): { index: false; follow?: true } | undefined {
  if (status === "ok") return undefined;
  if (status === "not_found") return { index: false };
  return { index: false, follow: true };
}
