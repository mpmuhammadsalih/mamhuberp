import type { NextConfig } from "next";

const API = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8090";

const nextConfig: NextConfig = {
  allowedDevOrigins: ["whatsapp.mamahub.store"],
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      { source: "/api/auth/login", destination: `${API}/api/auth/login` },
      { source: "/api/:path*", destination: `${API}/api/:path*` },
    ];
  },
};

export default nextConfig;
