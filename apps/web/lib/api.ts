// Thin client over the esp-atlas API. No ranking/filtering logic lives here —
// this module only shapes requests/responses; the backend (esp_atlas_core) decides.
//
// Same-origin in production (the API is deployed as a Vercel function under
// /api, routed by the root vercel.json) unless NEXT_PUBLIC_API_URL overrides
// it; local dev talks to the standalone uvicorn server on :8000.
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || (process.env.NODE_ENV === "production" ? "/api" : "http://localhost:8000");

export interface SourceEntry {
  field: string;
  url: string;
  verified: string;
}

export interface PartRecord {
  id: string;
  type: string;
  name: string;
  vendor_or_brand: string;
  wifi_standard: string | null;
  wifi_bands: string | null;
  ble_version: string | null;
  bt_classic: boolean | null;
  ieee802154: boolean | null;
  ieee802154_protocols: string | null;
  form_factor: string | null;
  soc_ref: string | null;
  module_ref: string | null;
  usb_native: boolean | null;
  _path: string;
  sources: SourceEntry[];
}

export interface WizardRecord extends PartRecord {
  score: number;
  reasons: string[];
}

export type PartType = "soc" | "module" | "board";

export interface SearchFilters {
  q?: string;
  type?: PartType;
  radio?: string;
  band?: number;
  form?: string;
  protocol?: string;
  ieee802154?: boolean;
  ble?: boolean;
  bt_classic?: boolean;
  usb_native?: boolean;
}

export interface WizardNeeds {
  protocol?: string;
  radio?: string;
  band?: number;
  ble?: boolean;
  bt_classic?: boolean;
  usb_native?: boolean;
  ieee802154?: boolean;
  form?: string;
  type?: PartType;
  budget?: string;
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ? JSON.stringify(body.detail) : detail;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new Error(`esp-atlas API ${res.status}: ${detail}`);
  }
  return res.json() as Promise<T>;
}

function buildQuery(filters: object): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `?${qs}` : "";
}

export function searchParts(filters: SearchFilters): Promise<{ results: PartRecord[] }> {
  return apiFetch(`/search${buildQuery(filters)}`);
}

export function runWizard(needs: WizardNeeds): Promise<{ results: WizardRecord[] }> {
  return apiFetch(`/wizard`, { method: "POST", body: JSON.stringify({ needs }) });
}

export function listParts(): Promise<{ results: PartRecord[] }> {
  return apiFetch(`/parts`);
}

export function getPart(id: string): Promise<PartRecord> {
  return apiFetch(`/parts/${encodeURIComponent(id)}`);
}
