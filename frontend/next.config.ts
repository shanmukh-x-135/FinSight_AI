import type { NextConfig } from "next";

import { resolveApiOrigin, validateProductionApiOrigin } from "./lib/api-origin";

const isProductionDeployment =
  process.env.VERCEL_ENV === "production" ||
  process.env.FRONTEND_BUILD_ENV === "production";

const configuredBackendOrigin =
  process.env.BACKEND_API_URL ?? process.env.NEXT_PUBLIC_API_URL;
const backendOrigin = isProductionDeployment
  ? validateProductionApiOrigin(configuredBackendOrigin)
  : resolveApiOrigin(configuredBackendOrigin);

const nextConfig: NextConfig = {
  // Vercel consumes the default output. The production container requests the
  // minimal traced server bundle documented by Next.js for self-hosting.
  output: process.env.NEXT_OUTPUT_MODE === "standalone" ? "standalone" : undefined,
  async rewrites() {
    return [
      {
        source: "/api-proxy/:path*",
        destination: `${backendOrigin}/:path*`,
      },
    ];
  },
};

export default nextConfig;
