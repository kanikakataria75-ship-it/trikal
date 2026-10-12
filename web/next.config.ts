import type { NextConfig } from "next";

const API = process.env.TRIKAL_API ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Off: dev-only double mounting races drei <Html> roots under React 19 (labels vanish, console floods).
  reactStrictMode: false,
  // The UI never talks to a data source directly: every request goes to the TRIKAL API (PIT reader).
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API}/api/:path*` }];
  },
  transpilePackages: ["three"],
};

export default nextConfig;
