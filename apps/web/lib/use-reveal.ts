"use client";

// Thin React state wrapper over reveal.ts's pure math -- see there for the
// SPEC-firmware-popularity.md rationale.
import { useState } from "react";
import { PAGE_SIZE, initialReveal, revealMore } from "@/lib/reveal";

export function useReveal(total: number, pageSize: number = PAGE_SIZE) {
  const [revealed, setRevealed] = useState(() => initialReveal(total, pageSize));
  const hasMore = revealed < total;

  function showMore() {
    setRevealed((current) => revealMore(current, total, pageSize));
  }

  return { revealed, hasMore, showMore };
}
