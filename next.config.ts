import type { NextConfig } from "next";
import path from "path";

const nextConfig: NextConfig = {
  images: {
    unoptimized: true,
  },
  turbopack: {
    root: path.resolve(__dirname),
  },
  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl.replace(/\/$/, "")}/api/:path*`,
      },
      {
        source: "/documents/:path*",
        destination: `${backendUrl.replace(/\/$/, "")}/documents/:path*`,
      },
      {
        source: "/comparisons/:path*",
        destination: `${backendUrl.replace(/\/$/, "")}/comparisons/:path*`,
      },
      {
        source: "/graph",
        destination: `${backendUrl.replace(/\/$/, "")}/graph`,
      },
      {
        source: "/graph/:path*",
        destination: `${backendUrl.replace(/\/$/, "")}/graph/:path*`,
      },
    ];
  },
};

export default nextConfig;
