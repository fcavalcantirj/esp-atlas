"use client";

import Link from "next/link";
import type { PartRecord } from "@/lib/api";
import { track } from "@/lib/analytics";
import { PRICE_TIER_NOTE, bandsLabel, protocolsLabel, typeLabel, wifiLabel, yesNo } from "@/lib/format";

interface SpecRow {
  label: string;
  value: (part: PartRecord) => string | null;
  title?: string;
}

const ROWS: SpecRow[] = [
  { label: "Type", value: (p) => typeLabel(p.type) },
  { label: "Vendor / brand", value: (p) => p.vendor_or_brand },
  { label: "SoC", value: (p) => p.soc_ref },
  { label: "Module", value: (p) => p.module_ref },
  { label: "Form factor", value: (p) => p.form_factor },
  { label: "Price tier", value: (p) => (p.price_tier ? `~${p.price_tier}` : null), title: PRICE_TIER_NOTE },
  { label: "Wi-Fi", value: (p) => (p.wifi_standard ? wifiLabel(p.wifi_standard) : "none") },
  { label: "Wi-Fi bands", value: (p) => bandsLabel(p.wifi_bands) },
  { label: "Bluetooth LE", value: (p) => (p.ble_version ? `BLE ${p.ble_version}` : "none") },
  { label: "Bluetooth Classic", value: (p) => yesNo(p.bt_classic) },
  { label: "802.15.4", value: (p) => yesNo(p.ieee802154) },
  { label: "802.15.4 protocols", value: (p) => protocolsLabel(p.ieee802154_protocols) },
  { label: "Native USB", value: (p) => yesNo(p.usb_native) },
];

interface CompareTableProps {
  parts: PartRecord[];
  onRemove: (id: string) => void;
  onClear: () => void;
}

export default function CompareTable({ parts, onRemove, onClear }: CompareTableProps) {
  return (
    <>
      <div className="results-header">
        <span className="results-count">
          {parts.length} part{parts.length === 1 ? "" : "s"}
        </span>
        {parts.length === 1 && <span className="results-origin">add at least one more to compare</span>}
        <div className="results-actions">
          <button type="button" className="btn btn--sm" onClick={onClear}>
            Clear
          </button>
        </div>
      </div>
      <div className="compare-table-wrap">
        <table className="spec-table">
          <thead>
            <tr>
              <th scope="col">Spec</th>
              {parts.map((part) => (
                <th key={part.id} scope="col">
                  <span className="compare-col-head">
                    <Link
                      href={`/parts/${encodeURIComponent(part.id)}`}
                      onClick={() => track("result_click", { part_id: part.id, part_type: part.type, origin: "compare" })}
                    >
                      {part.name}
                    </Link>
                    <button
                      type="button"
                      className="chip-remove"
                      aria-label={`Remove ${part.name} from comparison`}
                      onClick={() => onRemove(part.id)}
                    >
                      ×
                    </button>
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map((row) => {
              const values = parts.map((p) => row.value(p) ?? "—");
              const differs = parts.length > 1 && new Set(values).size > 1;
              return (
                <tr key={row.label} className={differs ? "row-diff" : undefined}>
                  <th scope="row" title={row.title}>
                    {row.label}
                  </th>
                  {values.map((value, index) => (
                    <td key={parts[index].id}>{value}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </>
  );
}
