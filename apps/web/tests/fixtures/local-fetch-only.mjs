// Imported only by the local Playwright Next server. No upstream GitHub,
// inference or analytics calls are needed to render synthetic fixture pages.
const original = globalThis.fetch;
globalThis.fetch = (input, init) => {
  const url = new URL(input instanceof Request ? input.url : input);
  if (["localhost", "127.0.0.1", "::1"].includes(url.hostname)) return original(input, init);
  if (url.hostname === "raw.githubusercontent.com") return Promise.resolve(new Response(null, { status: 404 }));
  return Promise.reject(new Error(`External fetch blocked by browser fixtures: ${url.hostname}`));
};
