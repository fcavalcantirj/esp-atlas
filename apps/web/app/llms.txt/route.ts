import { readFile } from "node:fs/promises";
import path from "node:path";

// Serves the repository's llms.txt on the domain. `force-static` makes Next run
// this once at build time — when ../../llms.txt is reachable (the vercel-build
// step already copies ../../data from the same parent) — and ship the result as
// a static file, so production never reads the filesystem at request time.
export const dynamic = "force-static";

export async function GET() {
  const file = path.resolve(process.cwd(), "../../llms.txt");
  const text = await readFile(file, "utf8");
  return new Response(text, {
    headers: { "content-type": "text/plain; charset=utf-8" },
  });
}
