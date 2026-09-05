// Authorization for the on-demand catalog purge route (app/api/revalidate/route.ts).
//
// A pure function, kept apart from the route handler so it runs under `node --test`
// without booting Next (the route imports next/cache, which only works inside a request).
// The secret is the REVALIDATE_SECRET environment variable. Unset means the route is
// inert, which is the safe default for a deployment that has not opted in.
import { createHash, timingSafeEqual } from "node:crypto";

export type RevalidateVerdict = "unconfigured" | "unauthorized" | "ok";

export function authorizeRevalidate(
  authorization: string | null,
  secret: string | undefined,
): RevalidateVerdict {
  if (!secret) return "unconfigured";
  const match = /^Bearer\s+(\S+)$/i.exec(authorization ?? "");
  if (!match) return "unauthorized";
  // Compare digests rather than the strings: the digests are equal length by construction,
  // so timingSafeEqual never throws and a wrong-length token reveals nothing through timing.
  const presented = createHash("sha256").update(match[1]).digest();
  const expected = createHash("sha256").update(secret).digest();
  return timingSafeEqual(presented, expected) ? "ok" : "unauthorized";
}
