// Shared shapes for the home explorer (HomeView owns the state; ResultsPanel renders it).
import type { PartRecord, SearchFilters, WizardNeeds, WizardRecord } from "@/lib/api";

export type LastQuery = { kind: "wizard"; needs: WizardNeeds } | { kind: "search"; filters: SearchFilters };

export interface ExplorerState {
  results: (PartRecord | WizardRecord)[] | null;
  loading: boolean;
  error: string | null;
  lastQuery: LastQuery | null;
}
