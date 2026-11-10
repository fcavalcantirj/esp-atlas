import Link from "next/link";
import type { Firmware, PartDetail } from "@/lib/api";
import { firmwareCategoryLabel } from "@/lib/format";

// The SoC hub's firmware section (SPEC-serp-ctr.md §4): every firmware whose
// `socs` names the chip, already filtered server-side (lib/chip-firmware.ts)
// in the index's order. Renders nothing when no firmware names the chip.
export default function ChipFirmware({ part, firmware }: { part: PartDetail; firmware: Firmware[] }) {
  if (firmware.length === 0) return null;
  return (
    <section className="soc-hub" aria-labelledby="chip-firmware">
      <h2 id="chip-firmware">
        Firmware for {part.name} ({firmware.length})
      </h2>
      <ul className="aside-links">
        {firmware.map((fw) => (
          <li key={fw.id}>
            <Link href={`/firmware/${encodeURIComponent(fw.id)}`}>{fw.name}</Link>{" "}
            <span className="badge">{firmwareCategoryLabel(fw.category)}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
