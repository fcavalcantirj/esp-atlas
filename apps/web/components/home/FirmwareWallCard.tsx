import Link from "next/link";
import PopularityGlance from "@/components/PopularityGlance";
import type { Firmware } from "@/lib/api";
import { track } from "@/lib/analytics";
import { firmwareCategoryLabel } from "@/lib/format";

// SPEC-home rebuild §3: one card of the whole-catalog wall -- name, summary,
// stars, category, a "cited" badge (the record's own source count, never
// fabricated) and capability tags. `hidden` is the same visibility-cap idiom
// as FirmwareCard's: the card still renders into the server HTML so crawlers
// see the full catalog with no JS, "Show more" just lifts the CSS cap.
function initials(name: string): string {
  const letters = name
    .replace(/[^A-Za-z0-9 ]/g, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0] ?? "")
    .join("")
    .toUpperCase();
  return letters || "FW";
}

export default function FirmwareWallCard({ firmware, hidden = false }: { firmware: Firmware; hidden?: boolean }) {
  const citedCount = firmware.sources.length;
  return (
    <li className={hidden ? "wall-card is-hidden" : "wall-card"}>
      <Link
        href={`/firmware/${encodeURIComponent(firmware.id)}`}
        className="wall-card-link"
        onClick={() => track("result_click", { part_id: firmware.id, part_type: "firmware", origin: "wall" })}
      >
        <div className="wall-card-top">
          <span className="wall-card-avatar" aria-hidden="true">
            {initials(firmware.name)}
          </span>
          <div className="wall-card-heading">
            <p className="wall-card-name">{firmware.name}</p>
            <p className="wall-card-cat mono">{firmwareCategoryLabel(firmware.category)}</p>
          </div>
          <PopularityGlance popularity={firmware.popularity} />
        </div>
        {firmware.summary && <p className="wall-card-summary">{firmware.summary}</p>}
        <div className="wall-card-foot">
          {citedCount > 0 && <span className="wall-card-cited mono">✓ {citedCount} cited</span>}
          {firmware.capabilities.slice(0, 3).map((capability) => (
            <span key={capability} className="spec-chip spec-chip--on">
              {capability}
            </span>
          ))}
          <span className="wall-card-go mono" aria-hidden="true">
            view →
          </span>
        </div>
      </Link>
    </li>
  );
}
