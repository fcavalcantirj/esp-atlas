import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  agentRules: false,
  async redirects() {
    return [{ source: "/boards/:id", destination: "/parts/:id", permanent: true }];
  },
};

export default nextConfig;
