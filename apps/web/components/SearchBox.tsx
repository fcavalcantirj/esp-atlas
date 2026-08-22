"use client";

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
        <span className="label-row">Keywords</span>
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
          <span className="label-row">Type</span>
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
          <span className="label-row">Form factor</span>
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
          <span className="label-row">Wi-Fi</span>
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
          <span className="label-row">Band (GHz)</span>
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
          <span className="label-row">802.15.4 protocol</span>
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
