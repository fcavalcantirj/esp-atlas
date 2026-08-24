// The in-browser flash rail (SPEC-wizard P2b): ESP Web Tools' <esp-web-install-button>
// driven by a manifest our API generates from the recipe (GET /manifest/<id>.json,
// P3) or, for `esp-web-tools` recipes, the project's own manifest.
//
// Verified against esp-web-tools 10.4.0 source (tag `10.4.0`): the button spawns
// its own <ewt-install-dialog>, which fetches the manifest, prompts before an
// erase (`new_install_prompt_erase`), flashes and shows progress + the device's
// error text. The button emits no DOM events for that flow, so progress stays
// inside the dialog. The dialog also never checks `resp.ok` on the manifest
// fetch — any JSON body becomes "the manifest" (observed on real hardware as an
// "Install undefined" button) — which is why the UI preflights the URL itself
// and only mounts the button once it holds a real manifest.
import type { Firmware, Recipe } from "@/lib/api";
import { API_BASE } from "@/lib/api";

// Exact pin, not a floating `@10`: code that writes firmware to hardware must not
// change behaviour underneath us (10.3.0 added serialType, for one). Bump by PR.
export const ESP_WEB_TOOLS_VERSION = "10.4.0";
export const ESP_WEB_TOOLS_SRC = `https://unpkg.com/esp-web-tools@${ESP_WEB_TOOLS_VERSION}/dist/web/install-button.js?module`;

/** The subset of the ESP Web Tools manifest (src/const.ts) the UI reads. */
export interface Manifest {
  name: string;
  version: string;
  new_install_prompt_erase?: boolean;
  builds: { chipFamily: string; parts: { path: string; offset: number }[] }[];
}

export function isManifest(value: unknown): value is Manifest {
  if (!value || typeof value !== "object") return false;
  const m = value as Record<string, unknown>;
  return (
    typeof m.name === "string" &&
    typeof m.version === "string" &&
    Array.isArray(m.builds) &&
    m.builds.length > 0 &&
    m.builds.every((b) => b && typeof b === "object" && typeof (b as Manifest["builds"][number]).chipFamily === "string")
  );
}

/** Where the button's manifest comes from, or null when the recipe has no in-browser rail. */
export function manifestUrlFor(recipe: Recipe): string | null {
  const method = recipe.flash?.method;
  if (method === "esp-web-tools") return recipe.flash?.manifest_url ?? null;
  if (method === "release-bin") return `${API_BASE}/manifest/${encodeURIComponent(recipe.id)}.json`;
  return null;
}

/** Everything the guided handoff may link to — only URLs the firmware record cites. */
export interface FlashHandoff {
  repoUrl: string | null;
  /** `sources[].field == "distribution"` entries: the project's own flasher / installer pages. */
  flasherUrls: string[];
}

export function handoffFor(firmware: Firmware | null | undefined): FlashHandoff {
  if (!firmware) return { repoUrl: null, flasherUrls: [] };
  const urls = firmware.sources.filter((s) => s.field === "distribution").map((s) => s.url);
  return { repoUrl: firmware.url || null, flasherUrls: Array.from(new Set(urls)) };
}

let loading: Promise<void> | null = null;

/** Load the custom element once, on demand — only pages that open a flash panel pay for it. */
export function ensureEspWebTools(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("esp-web-tools needs a browser"));
  if (customElements.get("esp-web-install-button")) return Promise.resolve();
  if (!loading) {
    loading = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.type = "module";
      script.src = ESP_WEB_TOOLS_SRC;
      script.onload = () => customElements.whenDefined("esp-web-install-button").then(() => resolve());
      script.onerror = () => {
        loading = null;
        script.remove();
        reject(new Error("esp-web-tools failed to load"));
      };
      document.head.appendChild(script);
    });
  }
  return loading;
}

// React 19 keeps JSX typings under the `react` module, so the custom element is
// declared by module augmentation; the namespace form is the only one that works.
declare module "react" {
  // eslint-disable-next-line @typescript-eslint/no-namespace
  namespace JSX {
    interface IntrinsicElements {
      "esp-web-install-button": DetailedHTMLProps<HTMLAttributes<HTMLElement>, HTMLElement> & { manifest?: string };
    }
  }
}
