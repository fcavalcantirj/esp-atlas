import Link from "next/link";
import type { PartRecord, WizardRecord } from "@/lib/api";

function specLine(part: PartRecord): string {
  const specs: string[] = [];
  if (part.wifi_standard) {
    specs.push(`wifi=${part.wifi_standard}${part.wifi_bands ? ` (${part.wifi_bands} GHz)` : ""}`);
  }
  if (part.ble_version) specs.push(`ble=${part.ble_version}`);
  if (part.ieee802154) specs.push(`802.15.4=${part.ieee802154_protocols || "yes"}`);
  if (part.form_factor) specs.push(`form=${part.form_factor}`);
  if (part.usb_native) specs.push("usb=native");
  return specs.join(" · ");
}

export default function PartResultCard({ part }: { part: PartRecord | WizardRecord }) {
  const wizardPart = "score" in part ? (part as WizardRecord) : null;
  return (
    <li className="part-card">
      <Link href={`/parts/${encodeURIComponent(part.id)}`}>
        <strong>{part.name}</strong> <span className="part-type">[{part.type}]</span>
      </Link>
      {wizardPart && <span className="part-score"> score {wizardPart.score}</span>}
      <div className="part-specs">{specLine(part)}</div>
      {wizardPart && wizardPart.reasons.length > 0 && (
        <ul className="part-reasons">
          {wizardPart.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}
    </li>
  );
}
