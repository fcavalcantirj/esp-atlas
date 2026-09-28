"use client";

import { boardFlashCtaLabel, boardFlashCtaParams, shouldShowBoardFlashCta } from "@/lib/board-flash-cta";
import { track } from "@/lib/analytics";
import type { RecipeRow } from "@/components/RecipeGroupList";

// Above-the-fold board-page CTA: one click from the top of the page to
// #board-firmware, which otherwise sits dead last after header, image, spec
// groups, chip chain, and body prose (page_view -> flash_open conversion was
// ~0). A real anchor so it works with no JS; the click handler additionally
// moves keyboard focus to the section for users who tab/click through it.
export default function BoardFlashCta({
  partType,
  partId,
  rows,
}: {
  partType: string;
  partId: string;
  rows: RecipeRow[] | null;
}) {
  if (!shouldShowBoardFlashCta(partType, rows) || rows === null) return null;

  return (
    <a
      href="#board-firmware"
      className="btn btn--primary btn--block board-flash-cta"
      onClick={() => {
        track("board_flash_cta_click", boardFlashCtaParams(partId, rows));
        document.getElementById("board-firmware")?.focus();
      }}
    >
      Flash this board — {boardFlashCtaLabel(rows)}
    </a>
  );
}
