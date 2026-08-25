import type { Example, ExampleGroup } from "@/lib/api";

// Where the site's navigation leads. Every card, crumb and "see all" resolves
// here so a destination is never invented twice.

/** The typed index a part's breadcrumb points at ("Boards" → /boards). */
export function typeIndexPath(type: string): string | null {
  switch (type) {
    case "board":
      return "/boards";
    case "module":
      return "/modules";
    case "soc":
      return "/socs";
    default:
      return null;
  }
}

/** A home example as a real link: firmware → its hub, needs → the wizard with that query. */
export function exampleHref(example: Example): string {
  if (example.kind === "firmware") return `/firmware/${encodeURIComponent(example.firmware)}`;
  return `/wizard?example=${encodeURIComponent(example.id)}`;
}

/** The "see all" affordance of each home shelf. */
export const SHELF_SEE_ALL: Record<ExampleGroup, { href: string; label: string }> = {
  "run-firmware": { href: "/firmware", label: "All firmware" },
  "build-project": { href: "/wizard", label: "Open the spec wizard" },
  "just-show-me": { href: "/wizard", label: "Open the spec wizard" },
};
