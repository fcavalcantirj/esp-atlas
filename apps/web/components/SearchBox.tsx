"use client";

import HelpTip from "@/components/HelpTip";
import type { Facets, PartType, SearchFilters } from "@/lib/api";

const TYPE_ORDER: PartType[] = ["board", "module", "soc"];

interface SearchBoxProps {
  facets: Facets | null;
  value: SearchFilters;
  onChange: (filters: SearchFilters) => void;
  onSubmit: () => void;
  loading: boolean;
}

function withField<K extends keyof SearchFilters>(filters: SearchFilters, key: K, value: SearchFilters[K] | "") {
  const next = { ...filters };
  if (value === "" || value === undefined) {
    if (key === "q") next.q = "";
    else delete next[key];
  } else {
    next[key] = value;
  }
  return next;
}

/** "zigbee-3.0" / "thread-1.3" / "matter" -> "zigbee" / "thread" / "matter" (the API matches by substring). */
function protocolFamilies(facets: Facets | null): string[] {
  if (!facets) return ["zigbee", "thread", "matter"];
  const families = new Set<string>();
  for (const facet of facets.ieee802154_protocols) families.add(facet.value.split("-")[0]);
  return [...families].sort();
}

export default function SearchBox({ facets, value, onChange, onSubmit, loading }: SearchBoxProps) {
  const forms = facets ? facets.form_factor : [];
  const radios = facets ? facets.wifi_standard.map((f) => f.value).sort() : ["wifi-4", "wifi-6"];
  const bands = facets
    ? facets.wifi_bands.map((f) => f.value).sort((a, b) => parseFloat(a) - parseFloat(b))
    : ["2.4", "5"];
  const types = facets ? TYPE_ORDER.filter((t) => facets.type.some((f) => f.value === t)) : TYPE_ORDER;
  const protocols = protocolFamilies(facets);

  return (
    <form
      className="panel-form"
      role="search"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <label className="field">
        <span className="label-row">
            Keywords
            <HelpTip field="search_q" text="Free text over every record — part names, aka names, and the prose/notes on each page. Try a chip (esp32-s3), a board name (t-display), or something only mentioned in prose (lora, e-ink)." />
          </span>
        <input
          type="search"
          placeholder="e.g. zigbee, t-display, lora"
          value={value.q ?? ""}
          onChange={(e) => onChange(withField(value, "q", e.target.value))}
          autoComplete="off"
        />
      </label>
      <div className="form-grid">
        <label className="field">
          <span className="label-row">
            Type
            <HelpTip field="search_type" text="Which layer of the atlas to return. soc = the bare chip, module = a chip sealed in a can with flash/PSRAM/antenna, board = a module or chip on a finished board with USB, a regulator and headers. Most people want board." />
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
        <label className="field">
          <span className="label-row">
            Form factor
            <HelpTip field="search_form" text="The board's physical shape and pinout family. xiao = thumbnail-size, feather = the Adafruit ecosystem, devkit = the chip maker's own reference board, m5-core = M5Stack's modular blocks. Counts come from the data, so only shapes that actually exist are offered." />
          </span>
          <select value={value.form ?? ""} onChange={(e) => onChange(withField(value, "form", e.target.value))}>
            <option value="">any</option>
            {forms.map((f) => (
              <option key={f.value} value={f.value}>
                {f.value} ({f.count})
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="label-row">
            Wi-Fi
            <HelpTip field="search_radio" text="Minimum Wi-Fi generation, not an exact match — Wi-Fi generations are backward compatible, so asking for Wi-Fi 4 also returns Wi-Fi 6 parts. Parts with no Wi-Fi at all (the ESP32-H2) never match." />
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
            Band (GHz)
            <HelpTip field="search_band" text="Which Wi-Fi band the radio can use. 2.4 GHz reaches further and is on every Wi-Fi ESP32; 5 GHz is faster and far less crowded, but only the newest parts have it." />
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
            802.15.4 protocol
            <HelpTip field="search_protocol" text="The low-power smart-home mesh standards — Thread, Zigbee and Matter-over-Thread — that pair with Apple Home, Google Home or Alexa. They share one radio (802.15.4) found only on the ESP32-C6, C5 and H2. If you only need Wi-Fi or Bluetooth, leave this alone." />
          </span>
          <select
            value={value.protocol ?? ""}
            onChange={(e) => onChange(withField(value, "protocol", e.target.value))}
          >
            <option value="">any</option>
            {protocols.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button type="submit" className="btn btn--block" disabled={loading}>
        {loading ? "Searching…" : "Search"}
      </button>
    </form>
  );
}
