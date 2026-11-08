// Independent metrics publication does not need a deployment or catalog purge.
import { revalidateTag } from "next/cache";
import { POPULARITY_TAG } from "@/lib/api-server";
import { authorizeRevalidate } from "@/lib/revalidate-auth";

export async function POST(request: Request) {
  const verdict = authorizeRevalidate(request.headers.get("authorization"), process.env.POPULARITY_REVALIDATE_SECRET);
  if (verdict === "unconfigured") {
    return Response.json({ error: "popularity revalidation not configured" }, { status: 503 });
  }
  if (verdict === "unauthorized") {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  revalidateTag(POPULARITY_TAG, { expire: 0 });
  return Response.json({ revalidated: true, tag: POPULARITY_TAG, now: Date.now() });
}
