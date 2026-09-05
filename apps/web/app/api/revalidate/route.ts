// POST /api/revalidate — purge the "catalog" entries of the Next Data Cache on demand.
//
// Every server-side fetch in lib/api-server.ts is cached with
// `next: { revalidate: 3600, tags: ["catalog"] }`. When a catalog record is deleted, the
// hourly revalidation fetch 404s and Next keeps serving the stale entry: that is how
// /firmware/make-ap and /firmware/cardradio outlived their records ("ghost pages").
// `cache: "no-store"` was tried (0c8ce8c) and reverted (9a3a614) because it sent every
// render to a cold Python function that rebuilds its SQLite index at import, and the site
// crawled. So the cache stays, and whoever changes the catalog (EspAtlas Jr's publisher,
// after a merge) calls this route with the shared secret.
//
// `{ expire: 0 }`, not "max": "max" is stale-while-revalidate, which would serve the ghost
// once more and then hit the same 404-keeps-stale path. Immediate expiry makes the next
// request fetch, receive the 404, and render notFound().
//
// Inert (503) until REVALIDATE_SECRET is set in the deployment.
import { revalidateTag } from "next/cache";
import { CATALOG_TAG } from "@/lib/api-server";
import { authorizeRevalidate } from "@/lib/revalidate-auth";

export async function POST(request: Request) {
  const verdict = authorizeRevalidate(request.headers.get("authorization"), process.env.REVALIDATE_SECRET);
  if (verdict === "unconfigured") {
    return Response.json({ error: "revalidation not configured" }, { status: 503 });
  }
  if (verdict === "unauthorized") {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  revalidateTag(CATALOG_TAG, { expire: 0 });
  return Response.json({ revalidated: true, tag: CATALOG_TAG, now: Date.now() });
}
