import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  // Inline the CSS into each HTML response instead of a render-blocking stylesheet request (2026-11-18).
  // Lighthouse mobile, real throttling, local production build, 3 interleaved runs: first paint / LCP
  // home 1620 -> 876 ms, /parts/esp32-c6 1639 -> 987 ms. Cost: ~30 KB more compressed HTML per full page
  // load and no separate CSS cache; visits average 1.6 pages and arrive mostly from search, so first view wins.
  experimental: { inlineCss: true },
  async redirects() {
    return [{ source: "/boards/:id", destination: "/parts/:id", permanent: true }];
  },
};

export default nextConfig;
