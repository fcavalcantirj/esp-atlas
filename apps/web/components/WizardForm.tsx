"use client";

import { useState } from "react";
import { runWizard, type WizardNeeds, type WizardRecord } from "@/lib/api";
import PartResultCard from "@/components/PartResultCard";

const PROTOCOLS = ["", "zigbee", "thread", "matter"];
const RADIOS = ["", "wifi-4", "wifi-6"];
const BANDS = ["", "2.4", "5"];
const FORM_TYPES = ["", "soc", "module", "board"];

export default function WizardForm() {
  const [protocol, setProtocol] = useState("");
  const [radio, setRadio] = useState("");
  const [band, setBand] = useState("");
  const [form, setForm] = useState("");
  const [type, setType] = useState("");
  const [usbNative, setUsbNative] = useState(false);
  const [budget, setBudget] = useState("");

  const [results, setResults] = useState<WizardRecord[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const needs: WizardNeeds = {};
    if (protocol) needs.protocol = protocol;
    if (radio) needs.radio = radio;
    if (band) needs.band = Number(band);
    if (form) needs.form = form;
    if (type) needs.type = type as WizardNeeds["type"];
    if (usbNative) needs.usb_native = true;
    if (budget) needs.budget = budget;

    try {
      const { results } = await runWizard(needs);
      setResults(results);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setResults(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section>
      <h2>Wizard</h2>
      <p>What are you building? Answer what matters, skip the rest.</p>
      <form onSubmit={handleSubmit} className="wizard-form">
        <label>
          802.15.4 protocol
          <select value={protocol} onChange={(e) => setProtocol(e.target.value)}>
            {PROTOCOLS.map((p) => (
              <option key={p} value={p}>
                {p || "any"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Wi-Fi standard
          <select value={radio} onChange={(e) => setRadio(e.target.value)}>
            {RADIOS.map((r) => (
              <option key={r} value={r}>
                {r || "any"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Wi-Fi band (GHz)
          <select value={band} onChange={(e) => setBand(e.target.value)}>
            {BANDS.map((b) => (
              <option key={b} value={b}>
                {b || "any"}
              </option>
            ))}
          </select>
        </label>
        <label>
          Form factor
          <input
            type="text"
            placeholder="e.g. xiao, devkit"
            value={form}
            onChange={(e) => setForm(e.target.value)}
          />
        </label>
        <label>
          Type
          <select value={type} onChange={(e) => setType(e.target.value)}>
            {FORM_TYPES.map((t) => (
              <option key={t} value={t}>
                {t || "any"}
              </option>
            ))}
          </select>
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={usbNative} onChange={(e) => setUsbNative(e.target.checked)} />
          Native USB required
        </label>
        <label>
          Budget
          <input
            type="text"
            placeholder="low / medium / high (not price-modeled yet)"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
          />
        </label>
        <button type="submit" disabled={loading}>
          {loading ? "Searching…" : "Find parts"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}
      {results && results.length === 0 && <p>No matches.</p>}
      {results && results.length > 0 && (
        <ul className="results-list">
          {results.map((part) => (
            <PartResultCard key={part.id} part={part} />
          ))}
        </ul>
      )}
    </section>
  );
}
