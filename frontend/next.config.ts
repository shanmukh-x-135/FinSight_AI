import type { NextConfig } from "next";

import { validateProductionApiOrigin } from "./lib/api-origin";

const isProductionDeployment =
  process.env.VERCEL_ENV === "production" ||
  process.env.FRONTEND_BUILD_ENV === "production";

if (isProductionDeployment) {
  validateProductionApiOrigin(process.env.NEXT_PUBLIC_API_URL);
}

const nextConfig: NextConfig = {
  // Vercel consumes the default output. The production container requests the
  // minimal traced server bundle documented by Next.js for self-hosting.
  output: process.env.NEXT_OUTPUT_MODE === "standalone" ? "standalone" : undefined,
};

export default nextConfig;
