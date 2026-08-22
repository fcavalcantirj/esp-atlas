"use client";

import { useState } from "react";
import { runWizard, type WizardNeeds, type WizardRecord } from "@/lib/api";
import PartResultCard from "@/components/PartResultCard";
import HelpTip from "@/components/HelpTip";

const RADIOS = ["", "wifi-4", "wifi-6"];
const BANDS = ["", "2.4", "5"];
const FORM_TYPES = ["", "soc", "module", "board"];
const FORM_FACTORS = ["", "devkit", "xiao", "feather", "m5-core"];
const BUDGETS = ["", "cheap", "medium", "expensive"];

export default function WizardForm() {
  const [radio, setRadio] = useState("");
  const [band, setBand] = useState("");
  const [form, setForm] = useState("");
  const [type, setType] = useState("");
  const [usbNative, setUsbNative] = useState(false);
  const [ieee802154, setIeee802154] = useState(false);
  const [budget, setBudget] = useState("");

  const [results, setResults] = useState<WizardRecord[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    const needs: WizardNeeds = {};
    if (radio) needs.radio = radio;
    if (band) needs.band = Number(band);
    if (form) needs.form = form;
    if (type) needs.type = type as WizardNeeds["type"];
    if (usbNative) needs.usb_native = true;
    if (ieee802154) needs.ieee802154 = true;
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
          <span className="label-row">
            Wi-Fi standard
            <HelpTip text="wifi-4 (802.11n) is on every ESP32. wifi-6 (802.11ax) is newer — better in crowded networks, lower power — only on ESP32-C5/C6." />
          </span>
          <select value={radio} onChange={(e) => setRadio(e.target.value)}>
            {RADIOS.map((r) => (
              <option key={r} value={r}>
                {r || "any"}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label-row">
            Wi-Fi band (GHz)
            <HelpTip text="2.4 GHz reaches farther and every chip has it. 5 GHz is faster and less crowded but only the newest chips (ESP32-C5) support it." />
          </span>
          <select value={band} onChange={(e) => setBand(e.target.value)}>
            {BANDS.map((b) => (
              <option key={b} value={b}>
                {b || "any"}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label-row">
            Form factor
            <HelpTip text="The board’s physical shape and pinout family. xiao = thumbnail-size, feather = Adafruit ecosystem, devkit = the chip maker’s reference board, m5-core = M5Stack modular." />
          </span>
          <select value={form} onChange={(e) => setForm(e.target.value)}>
            {FORM_FACTORS.map((f) => (
              <option key={f} value={f}>
                {f || "any"}
              </option>
            ))}
          </select>
        </label>
        <label>
          <span className="label-row">
            Type
            <HelpTip text="soc = the bare chip. module = chip + antenna + shielding (e.g. a WROOM). board = a ready-to-use dev board with USB and a power regulator." />
          </span>
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
          <HelpTip text="Tick this if your project needs the board to ACT AS a USB device — a keyboard, mouse, or flash drive — or to be flashed without a separate USB-to-serial bridge chip. The classic ESP32 has no built-in USB; the S2, S3, C3, C6 and H2 do." />
        </label>
        <label className="checkbox-label">
          <input type="checkbox" checked={ieee802154} onChange={(e) => setIeee802154(e.target.checked)} />
          Smart-home mesh (Thread / Zigbee / Matter)
          <HelpTip text="Tick this only if your device must join a low-power smart-home mesh — a Thread or Zigbee sensor, or a Matter device over Thread (the kind that pairs with Apple Home, Google Home or Alexa). That needs an ESP32-C6 or H2. If you are just using Wi-Fi or Bluetooth, leave it unchecked." />
        </label>
        <label>
          <span className="label-row">
            Budget
            <HelpTip text="Approximate street-price tier — an editorial estimate, not a datasheet spec. cheap ≈ under $15, medium ≈ $15–50, expensive ≈ $50+. Filters as a spending ceiling." />
          </span>
          <select value={budget} onChange={(e) => setBudget(e.target.value)}>
            {BUDGETS.map((b) => (
              <option key={b} value={b}>
                {b || "any"}
              </option>
            ))}
          </select>
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
