// GET /api/consent-region — does this visitor's region need an analytics consent banner (EEA, UK, CH)?
//
// Only the consent banner calls it, and only while no choice is stored. Reading the geo header here, not in
// the root layout, keeps every page static/ISR (a header read in the layout would make the whole site render
// per request). The country itself is not returned: the banner needs one bit.
import { consentRequired } from "@/lib/consent";

export const dynamic = "force-dynamic";

export function GET(request: Request): Response {
  const required = consentRequired(request.headers.get("x-vercel-ip-country"));
  return Response.json({ consent_required: required }, { headers: { "cache-control": "private, no-store" } });
}
