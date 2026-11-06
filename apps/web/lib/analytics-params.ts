type ParamValue = string | number | boolean | undefined | null;
export type EventParams = Record<string, ParamValue>;

const MAX_PARAM_LENGTH = 100;
const PRIVATE_KEYS = new Set(["q", "query", "needs", "extra", "url", "href", "path", "prompt", "text"]);

// Only a small set of public hardware model formats may travel through the
// existing registered GA4 customEvent:q dimension. The full search query never
// leaves the browser: a phrase, URL, email, or key-like string cannot match.
// Extend this list only with a documented public model family and a regression
// for private lookalikes. GSC remains the source for unconstrained query text.
const PUBLIC_MODEL_TOKEN = /^(?:FNK\d{4}[A-Z]|ES3[CN]\d{2}P|ESP32(?:-[CSHP]\d{1,2})?|M5CARDPUTER)$/;

export function eligibleModelToken(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const token = value.trim().toUpperCase();
  return PUBLIC_MODEL_TOKEN.test(token) ? token : null;
}

export function cleanEventParams(params: EventParams): Record<string, string | number | boolean> {
  const out: Record<string, string | number | boolean> = {};
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (PRIVATE_KEYS.has(key)) {
      if (typeof value === "string") out[`${key}_length`] = value.length;
      continue;
    }
    out[key] = typeof value === "string" ? value.slice(0, MAX_PARAM_LENGTH) : value;
  }
  return out;
}

/** Build the exact GA payload; only search events may expose a known public model token. */
export function trackedEventParams(name: string, params: EventParams): Record<string, string | number | boolean> {
  const clean = cleanEventParams(params);
  if ((name === "search_submit" || name === "search_empty") && typeof params.q === "string") {
    const modelToken = eligibleModelToken(params.q);
    if (modelToken) clean.q = modelToken;
  }
  return clean;
}
