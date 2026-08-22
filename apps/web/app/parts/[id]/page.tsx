"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getPart, type PartRecord } from "@/lib/api";

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
  ["SoC", "soc_ref"],
  ["Module", "module_ref"],
  ["Native USB", "usb_native"],
];

function renderValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "yes" : "no";
  return String(value);
}

export default function PartPage() {
  const params = useParams<{ id: string }>();
  // key forces a remount (fresh loading/error/part state) whenever the route id changes
  return <PartDetail key={params.id} id={params.id} />;
}

function PartDetail({ id }: { id: string }) {
  const [part, setPart] = useState<PartRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPart(id)
      .then((p) => {
        if (!cancelled) setPart(p);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  return (
    <main className="container">
      <p>
        <Link href="/">&larr; back</Link>
      </p>
      {loading && <p>Loading…</p>}
      {error && <p className="error">{error}</p>}
      {part && (
        <>
          <h1>
            {part.name} <span className="part-type">[{part.type}]</span>
          </h1>
          <table className="spec-table">
            <tbody>
              {SPEC_ROWS.map(([label, key]) => (
                <tr key={key}>
                  <th>{label}</th>
                  <td>{renderValue(part[key])}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <h2>Sources</h2>
          {part.sources.length === 0 ? (
            <p>No sources on record.</p>
          ) : (
            <ul>
              {part.sources.map((source) => (
                <li key={`${source.field}-${source.url}`}>
                  <strong>{source.field}</strong>:{" "}
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.url}
                  </a>{" "}
                  (verified {source.verified})
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </main>
  );
}
