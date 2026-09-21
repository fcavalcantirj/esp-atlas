// SPEC-firmware-popularity.md §5 (D2/D3): v1 renders every card server-side
// for crawlability, then reveals PAGE_SIZE at a time client-side -- a pure
// visibility cap, never a refetch. This module is the deterministic math
// behind that cap, kept separate from the React state that holds it.

export const PAGE_SIZE = 24;

/** How many items to show on first paint -- never more than exist. */
export function initialReveal(total: number, pageSize: number = PAGE_SIZE): number {
  return Math.min(pageSize, total);
}

/** "Show more" -> the next page, capped at total. */
export function revealMore(revealed: number, total: number, pageSize: number = PAGE_SIZE): number {
  return Math.min(revealed + pageSize, total);
}

/** "Showing N of M" */
export function revealCountLabel(revealed: number, total: number): string {
  return `Showing ${Math.min(revealed, total)} of ${total}`;
}
