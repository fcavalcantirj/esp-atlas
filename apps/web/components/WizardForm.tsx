"use client";

import type { Facet, Facets, PartType, WizardNeeds } from "@/lib/api";
import { track } from "@/lib/analytics";
import HelpTip from "@/components/HelpTip";

// Shown until /facets answers, so the form is usable on a cold API.
const FALLBACK_FORM_FACTORS: Facet[] = [
  { value: "devkit", count: 0 },
  { value: "xiao", count: 0 },
  { value: "feather", count: 0 },
  { value: "m5-core", count: 0 },
];
const BUDGET_ORDER = ["cheap", "medium", "expensive"];
const TYPE_ORDER: PartType[] = ["board", "module", "soc"];
const COMMON_FORM_FACTOR_MIN_COUNT = 3;

interface WizardFormProps {
  facets: Facets | null;
  value: WizardNeeds;
  onChange: (needs: WizardNeeds) => void;
  onSubmit: () => void;
  loading: boolean;
}

function withField<K extends keyof WizardNeeds>(needs: WizardNeeds, key: K, value: WizardNeeds[K] | "" | false) {
  const next = { ...needs };
  if (value === "" || value === false || value === undefined) delete next[key];
  else next[key] = value;
  return next;
}

export default function WizardForm({ facets, value, onChange, onSubmit, loading }: WizardFormProps) {
  const formFactors = facets?.form_factor.length ? facets.form_factor : FALLBACK_FORM_FACTORS;
  const commonForms = formFactors.filter((f) => f.count >= COMMON_FORM_FACTOR_MIN_COUNT || f.count === 0);
  const otherForms = formFactors.filter((f) => f.count > 0 && f.count < COMMON_FORM_FACTOR_MIN_COUNT);
  const budgets = facets
    ? BUDGET_ORDER.filter((tier) => facets.price_tier.some((f) => f.value === tier))
    : BUDGET_ORDER;
  const radios = facets ? facets.wifi_standard.map((f) => f.value).sort() : ["wifi-4", "wifi-6"];
  const bands = facets
    ? facets.wifi_bands.map((f) => f.value).sort((a, b) => parseFloat(a) - parseFloat(b))
    : ["2.4", "5"];
  const types = facets ? TYPE_ORDER.filter((t) => facets.type.some((f) => f.value === t)) : TYPE_ORDER;

  const formOption = (f: Facet) => (
    <option key={f.value} value={f.value}>
      {f.count > 0 ? `${f.value} (${f.count})` : f.value}
    </option>
  );

  return (
    <form
      className="panel-form"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <div className="form-grid">
        <label className="field">
          <span className="label-row">
            Form factor
            <HelpTip
              field="form"
              text="The board's physical shape and pinout family. xiao = thumbnail-size, feather = Adafruit ecosystem, devkit = the chip maker's reference board, m5-core = M5Stack modular. Counts are how many parts in the atlas have that shape."
            />
          </span>
          <select value={value.form ?? ""} onChange={(e) => onChange(withField(value, "form", e.target.value))}>
            <option value="">any</option>
            {otherForms.length > 0 ? (
              <>
                <optgroup label="Common">{commonForms.map(formOption)}</optgroup>
                <optgroup label="Other">{otherForms.map(formOption)}</optgroup>
              </>
            ) : (
              commonForms.map(formOption)
            )}
          </select>
        </label>
        <label className="field">
          <span className="label-row">
            Budget
            <HelpTip
              field="budget"
              text="Approximate street-price tier — an editorial estimate, not a datasheet spec. cheap ≈ under $15, medium ≈ $15–50, expensive ≈ $50+. Filters as a spending ceiling: medium shows cheap and medium."
            />
          </span>
          <select value={value.budget ?? ""} onChange={(e) => onChange(withField(value, "budget", e.target.value))}>
            <option value="">any</option>
            {budgets.map((tier) => (
              <option key={tier} value={tier}>
                {tier}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="checkbox-stack">
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={Boolean(value.ieee802154)}
            onChange={(e) => onChange(withField(value, "ieee802154", e.target.checked))}
          />
          <span className="checkbox-text">
            Smart-home mesh (Thread / Zigbee / Matter)
            <HelpTip
              field="ieee802154"
              text="Tick this only if your device must join a low-power smart-home mesh — a Thread or Zigbee sensor, or a Matter device over Thread (the kind that pairs with Apple Home, Google Home or Alexa). That needs an ESP32-C6, C5 or H2. If you are just using Wi-Fi or Bluetooth, leave it unchecked."
            />
          </span>
        </label>
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={Boolean(value.usb_native)}
            onChange={(e) => onChange(withField(value, "usb_native", e.target.checked))}
          />
          <span className="checkbox-text">
            Acts as a USB device (keyboard, mouse, drive)
            <HelpTip
              field="usb_native"
              text="Tick this if your project needs the board to ACT AS a USB device — a keyboard, mouse, or flash drive — or to be flashed without a separate USB-to-serial bridge chip. The classic ESP32 has no built-in USB; the S2, S3, C3, C6 and H2 do."
            />
          </span>
        </label>
      </div>

      <details
        className="wizard-advanced"
        onToggle={(e) => track("advanced_filters_toggle", { panel: "wizard", open: e.currentTarget.open })}
      >
        <summary>Advanced filters</summary>
        <div className="form-grid wizard-advanced-fields">
          <label className="field">
            <span className="label-row">
              Wi-Fi standard
              <HelpTip
                field="radio"
                text="wifi-4 (802.11n) is on every Wi-Fi ESP32. wifi-6 (802.11ax) is newer — better in crowded networks, lower power — only on ESP32-C5/C6/C61. Picking wifi-4 also includes wifi-6 parts (newer generations are backward compatible)."
              />
            </span>
            <select value={value.radio ?? ""} onChange={(e) => onChange(withField(value, "radio", e.target.value))}>
              <option value="">any</option>
              {radios.map((r) => (
                <option key={r} value={r}>
                  {r} or newer
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="label-row">
              Wi-Fi band (GHz)
              <HelpTip
                field="band"
                text="2.4 GHz reaches farther and every Wi-Fi chip has it. 5 GHz is faster and less crowded but only the newest chips (ESP32-C5) support it."
              />
            </span>
            <select
              value={value.band !== undefined ? String(value.band) : ""}
              onChange={(e) => onChange(withField(value, "band", e.target.value === "" ? "" : Number(e.target.value)))}
            >
              <option value="">any</option>
              {bands.map((b) => (
                <option key={b} value={b}>
                  {b}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="label-row">
              Type
              <HelpTip
                field="type"
                text="board = a ready-to-use dev board with USB and a power regulator. module = chip + antenna + shielding (e.g. a WROOM). soc = the bare chip."
              />
            </span>
            <select
              value={value.type ?? ""}
              onChange={(e) => onChange(withField(value, "type", e.target.value as PartType | ""))}
            >
              <option value="">any</option>
              {types.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
          </label>
        </div>
      </details>

      <button type="submit" className="btn btn--primary btn--block" disabled={loading}>
        {loading ? "Searching…" : "Find parts"}
      </button>
    </form>
  );
}
