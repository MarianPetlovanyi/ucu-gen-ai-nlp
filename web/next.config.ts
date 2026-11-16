import type { NextConfig } from "next";

// The UI talks to the Python API (app/api.py) through this proxy, so the browser never needs CORS.
const API_URL = process.env.NDA_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // An uncached review (C1→C7, three LLM calls) can take a minute; the default proxy timeout is 30 s.
    proxyTimeout: 300_000,
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
