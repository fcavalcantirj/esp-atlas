// Thin client over the esp-atlas API. No ranking/filtering logic lives here —
// this module only shapes requests/responses; the backend (esp_atlas_core) decides.
//
// Same-origin in production (the API is deployed as a Vercel function under
// /api, routed by apps/web/vercel.json) unless NEXT_PUBLIC_API_URL overrides
// it; local dev talks to the standalone uvicorn server on :8000.
export const API_BASE =
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
  brand_name: string;
  brand_url: string | null;
  wifi_standard: string | null;
  wifi_bands: string | null;
  ble_version: string | null;
  bt_classic: boolean | null;
  ieee802154: boolean | null;
  ieee802154_protocols: string | null;
  form_factor: string | null;
  price_tier: string | null;
  soc_ref: string | null;
  module_ref: string | null;
  usb_native: boolean | null;
  flash_mb: number | null;
  psram_mb: number | null;
  _path: string;
  sources: SourceEntry[];
}

export interface WizardRecord extends PartRecord {
  score: number;
  reasons: string[];
}

export interface Chain {
  soc: PartRecord | null;
  module: PartRecord | null;
}

/** GET /parts/{id}: the flat record plus its own frontmatter, prose, parents and siblings. */
export interface PartDetail extends PartRecord {
  frontmatter: Record<string, unknown>;
  body: string;
  chain: Chain;
  related: PartRecord[];
}

export interface Facet {
  value: string;
  count: number;
}

/** A vendor_or_brand facet entry: `display_name` (and `url` when known) resolved
 * server-side from data/brands/<value>/brand.md, falling back to the slug. */
export interface BrandFacet extends Facet {
  display_name: string;
  url: string | null;
}

/** A minimum-capability tier (psram_min/flash_min): `count` is how many parts
 * clear that floor, not how many equal it. Only non-empty tiers are returned,
 * so the UI never offers a dead option. */
export interface NumericFacet {
  value: number;
  count: number;
}

export interface Facets {
  type: Facet[];
  vendor_or_brand: BrandFacet[];
  form_factor: Facet[];
  wifi_standard: Facet[];
  price_tier: Facet[];
  soc_ref: Facet[];
  wifi_bands: Facet[];
  ieee802154_protocols: Facet[];
  psram_min: NumericFacet[];
  flash_min: NumericFacet[];
}

export interface Brand {
  slug: string;
  name: string;
  url: string | null;
}

/** GET /brands/{slug}: the brand's own identity plus every part from it. */
export interface BrandPage {
  brand: Brand;
  results: PartRecord[];
}

/** GET /firmware, GET /firmware/{id}: a flashable project. First-class like a
 * brand — never in /search, /wizard, or the parts index. */
export interface Firmware {
  id: string;
  type: string;
  name: string;
  url: string;
  category: string;
  maintainer: string | null;
  license: string | null;
  distribution: string[];
  manifest_url: string | null;
  capabilities: string[];
  socs: string[];
  sources: SourceEntry[];
}

export type RecipeStatus = "known-good" | "reported" | "unverified" | "broken";

export interface RecipeFlash {
  method: string | null;
  manifest_url: string | null;
  bin_url: string | null;
  offset: string | null;
  env: string | null;
  partition: string | null;
}

/** GET /recipes?board=&firmware=: one board × one firmware edge, the atomic
 * "what runs on what". `status` is a trust tier, see RecipeStatus. */
export interface Recipe {
  id: string;
  type: string;
  board: string;
  firmware: string;
  status: RecipeStatus | string;
  chip_family: string;
  firmware_version: string | null;
  flash: RecipeFlash | null;
  verified_by: string | null;
  verified_at: string | null;
  notes: string | null;
  sources: SourceEntry[];
}

export type PartType = "soc" | "module" | "board";

export interface SearchFilters {
  q?: string;
  type?: PartType;
  radio?: string;
  band?: number;
  form?: string;
  protocol?: string;
  soc?: string;
  module?: string;
  brand?: string;
  ieee802154?: boolean;
  ble?: boolean;
  bt_classic?: boolean;
  usb_native?: boolean;
}

export interface WizardNeeds {
  protocol?: string;
  radio?: string;
  band?: number;
  battery?: boolean;
  ble?: boolean;
  bt_classic?: boolean;
  usb_native?: boolean;
  ieee802154?: boolean;
  form?: string;
  type?: PartType;
  budget?: string;
  psram_min?: number;
  flash_min?: number;
}

/** GET /examples: generated one-click starting points — a computed projection of
 * recipes + parts fields (SPEC-home-explorer §3b), regenerated with the data so
 * it can never go stale. Every entry resolves to >= 1 result (the G7 oracle).
 * kind "firmware" links to that firmware's page (the boards it runs on); kind
 * "needs" replays a saved wizard query. */
export type ExampleGroup = "run-firmware" | "build-project" | "just-show-me";

export interface FirmwareExample {
  id: string;
  label: string;
  kind: "firmware";
  group: ExampleGroup;
  /** What the firmware is, derived server-side from its category + capabilities. */
  description?: string;
  firmware: string;
  count: number;
}

export interface NeedsExample {
  id: string;
  label: string;
  kind: "needs";
  group: ExampleGroup;
  needs: WizardNeeds;
  count: number;
}

export type Example = FirmwareExample | NeedsExample;

/** Why one board runs a firmware -- the recipe's own cited justification,
 * parallel to IntentParse.boards. Never invented: status/chip_family/sources
 * come straight off the recipe frontmatter, `reason` off its markdown body. */
export interface BoardReason {
  board: string;
  status: RecipeStatus | string;
  chip_family: string;
  sources: SourceEntry[];
  reason?: string;
}

/** POST /intent: a plain-language goal mapped onto the wizard's own filters.
 * kind "firmware" means the query named one (answered from the recipe graph);
 * "filters" mapped onto at least one real field; "unmapped" means Groq
 * understood the goal but the atlas has no board field for it (say so, offer
 * clarifiers); "unreadable" means the model returned nothing at all -- say so
 * plainly rather than dumping a keyword search. */
export interface IntentParse {
  kind: "firmware" | "filters" | "unmapped" | "unreadable";
  filters: WizardNeeds;
  understood: string[];
  unmapped: string[];
  firmware?: string;
  firmware_name?: string;
  /** What the firmware is, derived server-side -- data only, never generated prose. */
  firmware_description?: string;
  boards: string[];
  board_reasons: BoardReason[];
  cached: boolean;
}

/** One `requires` entry from data/firmware/<id>/firmware.md -- the author's own
 * verbatim rationale for why a firmware needs a capability. `board_signal` names
 * the structured board field esp_atlas_core.run_guide checks to state met/unmet
 * for a given board, or is null when the capability can't be proven or disproven
 * from any board's structured record (e.g. sub-GHz, NFC, IR). */
export interface FirmwareRequirement {
  capability: string;
  why?: string | null;
  board_signal?: string | null;
}

/** One `not_required` entry -- a capability the firmware explicitly does NOT
 * need, taught regardless of what any one board happens to carry. */
export interface FirmwareNotRequired {
  capability: string;
  why?: string | null;
}

/** run_guide's per-board fit (esp_atlas_core.run_guide._fit_for): hard
 * requirements gate it, benefits refine it once hardware is fully met. */
export type RunGuideFit = "ideal" | "works" | "partial" | "unconfirmed" | string;

/** One board's grounded, reasoned fit for a firmware -- see esp_atlas_core.run_guide.
 * `reasons`, `particularities`, `requires` and `not_required` are always deterministic,
 * computed straight from this board's own real record; `note` is the only field an
 * LLM ever contributes, and only after surviving the grounding validator (a
 * hallucinated board, spec, or source is rejected outright, never sanitized). */
export interface RunGuideBoard {
  board_id: string;
  board_name: string;
  fit: RunGuideFit;
  reasons: string[];
  particularities: string[];
  /** Grounded requirement-rationale teaching for THIS board -- each `requires`
   * entry stated met/unmet against its real record, or named unverifiable. */
  requires: string[];
  not_required: string[];
  status?: RecipeStatus | string | null;
  chip_family?: string | null;
  sources: SourceEntry[];
  note?: string | null;
}

export interface RunGuideFlashNext {
  board: string;
  recipe_id: string;
  manifest_url: string;
}

export interface RunGuideConstraint {
  chip: string;
}

export interface RunGuideExcludedBoard {
  board: string;
  reason: string;
}

/** GET /run/{firmware_id} -- the grounded "why does this firmware run on these
 * boards" answer. `grounded` is False only for an unknown/misspelled firmware
 * id, in which case `summary` is the honest not-found message and every list
 * is empty -- never a guess. */
export interface RunGuideResponse {
  firmware: string;
  firmware_name?: string | null;
  summary: string;
  requirements: string[];
  /** The firmware's own declared requirement-rationale, verbatim from
   * data/firmware/<id>/firmware.md. Per-board grounded teaching (met/unmet)
   * lives on each RunGuideBoard instead. */
  requires: FirmwareRequirement[];
  not_required: FirmwareNotRequired[];
  boards: RunGuideBoard[];
  flash_next: RunGuideFlashNext[];
  citations: string[];
  grounded: boolean;
  constraint?: RunGuideConstraint | null;
  excluded_boards?: RunGuideExcludedBoard[];
}

export class ApiError extends Error {
  status: number;
  endpoint: string;

  constructor(status: number, endpoint: string, detail: string) {
    super(`esp-atlas API ${status}: ${detail}`);
    this.name = "ApiError";
    this.status = status;
    this.endpoint = endpoint;
  }
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
    throw new ApiError(res.status, path.split("?")[0], detail);
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

export function getPart(id: string): Promise<PartDetail> {
  return apiFetch(`/parts/${encodeURIComponent(id)}`);
}

export function getFacets(): Promise<Facets> {
  return apiFetch(`/facets`);
}

export function listFirmware(): Promise<{ results: Firmware[] }> {
  return apiFetch(`/firmware`);
}

export function getRecipesForBoard(boardId: string): Promise<{ results: Recipe[] }> {
  return apiFetch(`/recipes?board=${encodeURIComponent(boardId)}`);
}

export function getFirmware(id: string): Promise<Firmware> {
  return apiFetch(`/firmware/${encodeURIComponent(id)}`);
}

export function getRecipesForFirmware(firmwareId: string): Promise<{ results: Recipe[] }> {
  return apiFetch(`/recipes?firmware=${encodeURIComponent(firmwareId)}`);
}

export function parseIntent(query: string): Promise<IntentParse> {
  return apiFetch(`/intent`, { method: "POST", body: JSON.stringify({ query }) });
}

export function runGuide(firmwareId: string, constraints?: string): Promise<RunGuideResponse> {
  const qs = constraints ? `?constraints=${encodeURIComponent(constraints)}` : "";
  return apiFetch(`/run/${encodeURIComponent(firmwareId)}${qs}`);
}
