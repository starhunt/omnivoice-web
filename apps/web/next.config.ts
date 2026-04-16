import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8320";
    return [
      { source: "/api/v1/:path*", destination: `${apiBase}/v1/:path*` },
      { source: "/media/:path*", destination: `${apiBase}/v1/assets/:path*` },
    ];
  },
};

export default nextConfig;
