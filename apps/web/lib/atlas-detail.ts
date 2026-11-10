import type { SourceEntry } from "./api.ts";

interface ParentRecord { id: string; name: string }
export interface AtlasPartDetail {
  id: string;
  body: string;
  sources: SourceEntry[];
  chain: { soc: ParentRecord | null; module: ParentRecord | null };
}
function object(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function parent(value: unknown): value is ParentRecord | null {
  return value === null || object(value) && typeof value.id === "string" && value.id.length > 0 && typeof value.name === "string" && value.name.length > 0;
}
/** Validate every detail field the inspector renders before replacing its
 * recoverable request state. Malformed 200s are not successful source records. */
export function atlasPartDetail(value: unknown, expectedId: string): AtlasPartDetail | null {
  if (!object(value) || value.id !== expectedId || typeof value.body !== "string"
    || !object(value.chain) || !parent(value.chain.soc) || !parent(value.chain.module)
    || !Array.isArray(value.sources) || !value.sources.every(source => object(source)
      && typeof source.field === "string" && typeof source.url === "string" && typeof source.verified === "string")) return null;
  return value as unknown as AtlasPartDetail;
}
