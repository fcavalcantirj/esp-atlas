// Safe readers over a record's raw YAML frontmatter (PartDetail.frontmatter is
// `Record<string, unknown>`; the schema lives in schema/*.schema.json). These only
// narrow types — they never compute or infer a spec.

export type Frontmatter = Record<string, unknown>;

export function fmObject(fm: Frontmatter, key: string): Frontmatter | null {
  const value = fm[key];
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Frontmatter) : null;
}

export function asString(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

export function asNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function asBool(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

export function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === "string") : [];
}

export function asNumberArray(value: unknown): number[] {
  return Array.isArray(value) ? value.filter((v): v is number => typeof v === "number") : [];
}
