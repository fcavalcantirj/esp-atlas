import { createServer } from "node:http";
import { firmware, orderedFirmware, board, guide, intent, build } from "./catalog.mjs";
const facets = Object.fromEntries(["type", "vendor_or_brand", "form_factor", "wifi_standard", "price_tier", "soc_ref", "wifi_bands", "ieee802154_protocols", "psram_min", "flash_min"].map(k => [k, []]));
createServer((req, res) => {
  const url = new URL(req.url, "http://127.0.0.1:8766");
  res.setHeader("Content-Type", "application/json");
  res.setHeader("Access-Control-Allow-Origin", "http://127.0.0.1:4186");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  if (req.method === "OPTIONS") { res.end(); return; }
  const path = url.pathname;
  const payload = path === "/firmware" ? { results: orderedFirmware(url.searchParams.get("sort")), total: firmware.length }
    : path === "/examples" ? { results: firmware.map(f => ({ kind: "firmware", id: f.id, firmware: f.id, label: f.name, group: "run-firmware", count: f.boards, stars: f.popularity.stars, forks: f.popularity.forks, as_of: f.popularity.as_of, github_as_of: f.popularity.github_as_of })) }
    : path === "/facets" ? facets : path === "/intent" ? intent : path.startsWith("/run/") ? guide : path === "/build" ? build
    : ["/wizard", "/search", "/parts"].includes(path) ? { results: [board] }
    : path.startsWith("/firmware/") ? firmware.find(f => f.id === path.split("/").pop())
    : path === "/status" ? { status: "operational" } : { results: [] };
  res.end(JSON.stringify(payload ?? {}));
}).listen(8766, "127.0.0.1");
