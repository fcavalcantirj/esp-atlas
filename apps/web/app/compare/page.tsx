"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { listParts, type PartRecord } from "@/lib/api";

const SPEC_ROWS: Array<[string, keyof PartRecord]> = [
  ["Type", "type"],
  ["Vendor / brand", "vendor_or_brand"],
  ["Wi-Fi standard", "wifi_standard"],
  ["Wi-Fi bands (GHz)", "wifi_bands"],
  ["Bluetooth LE", "ble_version"],
  ["Bluetooth Classic", "bt_classic"],
  ["802.15.4", "ieee802154"],
  ["802.15.4 protocols", "ieee802154_protocols"],
  ["Form factor", "form_factor"],
  ["Native USB", "usb_native"],
];

function renderValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

export default function ComparePage() {
  const [parts, setParts] = useState<PartRecord[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  useEffect(() => {
    listParts()
      .then((r) => setParts(r.results))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)))
      .finally(() => setLoading(false));
  }, []);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  const selectedParts = (parts ?? []).filter((p) => selected.has(p.id));

  return (
    <main className="container">
      <p>
        <Link href="/">&larr; back</Link>
      </p>
      <h1>Compare</h1>

      {loading && <p>Loading…</p>}
      {error && <p className="error">{error}</p>}

      {parts && (
        <fieldset className="compare-picker">
          <legend>Pick parts to compare</legend>
          {parts.map((p) => (
            <label key={p.id} className="checkbox-label">
              <input type="checkbox" checked={selected.has(p.id)} onChange={() => toggle(p.id)} />
              {p.name} [{p.type}]
            </label>
          ))}
        </fieldset>
      )}

      {selectedParts.length > 0 && (
        <table className="spec-table compare-table">
          <thead>
            <tr>
              <th>Spec</th>
              {selectedParts.map((p) => (
                <th key={p.id}>{p.name}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {SPEC_ROWS.map(([label, key]) => (
              <tr key={key}>
                <th>{label}</th>
                {selectedParts.map((p) => (
                  <td key={p.id}>{renderValue(p[key])}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </main>
  );
}
