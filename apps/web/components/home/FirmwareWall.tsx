"use client";

import { useMemo, useState } from "react";
import FirmwareWallCard from "@/components/home/FirmwareWallCard";
import type { Firmware } from "@/lib/api";
import { track } from "@/lib/analytics";
import { countCapabilities, WALL_CAPABILITIES } from "@/lib/capability-facets";
import { revealCountLabel } from "@/lib/reveal";
import { useReveal } from "@/lib/use-reveal";

// SPEC-home rebuild §3: the scroll-native firmware wall. Every card renders
// into the server HTML regardless of filter/reveal state (same cap idiom as
// FirmwareBrowseList) so a crawler with no JS still sees the full catalog;
// the capability rail and "load more" are a client-only visibility layer on
// top of that, never the only way to reach a card.
export default function FirmwareWall({ firmware }: { firmware: Firmware[] }) {
  const [activeCap, setActiveCap] = useState<string | null>(null);
  const facets = useMemo(() => countCapabilities(firmware, WALL_CAPABILITIES), [firmware]);
  const filtered = useMemo(
    () => (activeCap ? firmware.filter((item) => item.capabilities.includes(activeCap)) : firmware),
    [firmware, activeCap],
  );
  const { revealed, hasMore, showMore } = useReveal(filtered.length);

  function pick(cap: string | null) {
    track("home_wall_filter", { capability: cap ?? "all" });
    setActiveCap(cap);
  }

  return (
    <section className="firmware-wall" id="wall" aria-labelledby="wall-title">
      <div className="sechead">
        <h2 id="wall-title">The whole catalog</h2>
        <span className="sechead-meta mono">{filtered.length} firmware</span>
      </div>
      <div className="filters" role="group" aria-label="Filter by capability">
        <button type="button" className={activeCap === null ? "fchip on" : "fchip"} onClick={() => pick(null)}>
          all <span className="fchip-n">{firmware.length}</span>
        </button>
        {facets.map((facet) => (
          <button
            type="button"
            key={facet.value}
            className={activeCap === facet.value ? "fchip on" : "fchip"}
            onClick={() => pick(facet.value)}
          >
            {facet.value} <span className="fchip-n">{facet.count}</span>
          </button>
        ))}
      </div>
      <ul className="wall-grid">
        {filtered.map((item, index) => (
          <FirmwareWallCard key={item.id} firmware={item} hidden={index >= revealed} />
        ))}
      </ul>
      <div className="reveal-footer">
        <p className="reveal-count mono">{revealCountLabel(revealed, filtered.length)}</p>
        {hasMore && (
          <button type="button" className="btn" onClick={showMore}>
            Load more firmware
          </button>
        )}
      </div>
    </section>
  );
}
