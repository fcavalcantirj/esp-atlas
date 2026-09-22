import Link from "next/link";
import PopularityGlance from "@/components/PopularityGlance";
import type { Firmware } from "@/lib/api";
import { boardsLabel, firmwareCategoryLabel } from "@/lib/format";

// Same card idiom as PartResultCard (badge + brand-style meta line + spec
// chips), applied to a firmware record instead of a part. `hidden` is the
// SPEC-firmware-popularity.md §5 reveal cap: the card still renders into the
// server HTML (crawlable), just visually capped until "Show more" lifts it.
export default function FirmwareCard({ firmware, hidden = false }: { firmware: Firmware; hidden?: boolean }) {
  const chips = [...firmware.capabilities, ...firmware.socs];
  const boards = boardsLabel(firmware.boards);
  return (
    <li className={hidden ? "part-card is-hidden" : "part-card"}>
      <div className="part-card-head">
        <h3 className="part-card-title">
          <Link href={`/firmware/${encodeURIComponent(firmware.id)}`}>{firmware.name}</Link>
        </h3>
        <p className="part-card-meta">
          <span className="badge">{firmwareCategoryLabel(firmware.category)}</span>
          {firmware.maintainer && <span className="part-card-brand">{firmware.maintainer}</span>}
          <PopularityGlance popularity={firmware.popularity} />
          {boards && <span className="part-card-boards">{boards}</span>}
        </p>
      </div>
      {chips.length > 0 && (
        <div className="spec-chips">
          {firmware.capabilities.map((c) => (
            <span key={c} className="spec-chip spec-chip--on">
              {c}
            </span>
          ))}
          {firmware.socs.map((s) => (
            <span key={s} className="spec-chip">
              {s}
            </span>
          ))}
        </div>
      )}
    </li>
  );
}
