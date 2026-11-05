type ParamValue = string | number | boolean | undefined | null;
export type EventParams = Record<string, ParamValue>;

const MAX_PARAM_LENGTH = 100;
const PRIVATE_KEYS = new Set(["q", "query", "needs", "extra", "url", "href", "path", "prompt", "text"]);

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
