"use client";

import FirmwareCard from "@/components/FirmwareCard";
import type { Firmware } from "@/lib/api";
import { track } from "@/lib/analytics";
import { firmwareRevealParams } from "@/lib/firmware-tracking";
import { revealCountLabel } from "@/lib/reveal";
import { useReveal } from "@/lib/use-reveal";

// SPEC-firmware-popularity.md §1/§5: the primary ranked browse. `firmware` is
// already popularity-ordered by the API (D1) -- this only caps how many of
// the (fully server-rendered) cards are visible.
export default function FirmwareBrowseList({ firmware }: { firmware: Firmware[] }) {
  const { revealed, hasMore, showMore } = useReveal(firmware.length);

  function handleShowMore() {
    track("reveal_more", firmwareRevealParams(revealed, firmware.length));
    showMore();
  }

  return (
    <>
      <ul className="results-list">
        {firmware.map((fw, i) => (
          <FirmwareCard key={fw.id} firmware={fw} hidden={i >= revealed} />
        ))}
      </ul>
      <div className="reveal-footer">
        <p className="reveal-count">{revealCountLabel(revealed, firmware.length)}</p>
        {hasMore && (
          <button type="button" className="btn" onClick={handleShowMore}>
            Show more
          </button>
        )}
      </div>
    </>
  );
}
