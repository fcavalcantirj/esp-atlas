// Shared shapes for the home explorer (HomeView owns the state; ResultsPanel renders it).
import type { PartRecord, SearchFilters, WizardNeeds, WizardRecord } from "@/lib/api";

export type LastQuery = { kind: "wizard"; needs: WizardNeeds } | { kind: "search"; filters: SearchFilters };

export interface ExplorerState {
  results: (PartRecord | WizardRecord)[] | null;
  loading: boolean;
  error: string | null;
  lastQuery: LastQuery | null;
}

export interface Preset {
  id: string;
  label: string;
  needs: WizardNeeds;
}

// One-click starting points shown before the first query. Each is just a wizard
// request — the backend decides what matches.
export const PRESETS: Preset[] = [
  { id: "mesh_board", label: "Smart-home mesh board", needs: { ieee802154: true, type: "board" } },
  { id: "cheap_native_usb", label: "Cheap board with native USB", needs: { usb_native: true, budget: "cheap", type: "board" } },
  { id: "wifi6", label: "Wi-Fi 6", needs: { radio: "wifi-6" } },
  { id: "band_5ghz", label: "5 GHz Wi-Fi", needs: { band: 5 } },
  { id: "xiao", label: "XIAO-sized", needs: { form: "xiao" } },
];
