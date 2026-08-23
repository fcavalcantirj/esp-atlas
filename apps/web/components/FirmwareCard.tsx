import Link from "next/link";
import type { Firmware } from "@/lib/api";
import { firmwareCategoryLabel } from "@/lib/format";

// Same card idiom as PartResultCard (badge + brand-style meta line + spec
// chips), applied to a firmware record instead of a part.
export default function FirmwareCard({ firmware }: { firmware: Firmware }) {
  const chips = [...firmware.capabilities, ...firmware.socs];
  return (
    <li className="part-card">
      <div className="part-card-head">
        <h3 className="part-card-title">
          <Link href={`/firmware/${encodeURIComponent(firmware.id)}`}>{firmware.name}</Link>
        </h3>
        <p className="part-card-meta">
          <span className="badge">{firmwareCategoryLabel(firmware.category)}</span>
          {firmware.maintainer && <span className="part-card-brand">{firmware.maintainer}</span>}
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
