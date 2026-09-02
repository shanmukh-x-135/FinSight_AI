const LOCAL_API_ORIGIN = "http://localhost:8000";
export const BROWSER_API_BASE = "/api-proxy";

export function resolveConfiguredApiOrigin(
  backendOrigin = process.env.BACKEND_API_URL,
  legacyPublicOrigin = process.env.NEXT_PUBLIC_API_URL,
): string | undefined {
  return backendOrigin?.trim() || legacyPublicOrigin?.trim() || undefined;
}

export function resolveApiOrigin(rawOrigin = process.env.NEXT_PUBLIC_API_URL): string {
  return (rawOrigin?.trim() || LOCAL_API_ORIGIN).replace(/\/$/, "");
}

export function validateProductionApiOrigin(rawOrigin: string | undefined): string {
  if (!rawOrigin?.trim()) {
    throw new Error(
      "NEXT_PUBLIC_API_URL is required for a production frontend build.",
    );
  }

  let origin: URL;
  try {
    origin = new URL(rawOrigin);
  } catch {
    throw new Error("NEXT_PUBLIC_API_URL must be a valid absolute URL.");
  }

  if (origin.protocol !== "https:") {
    throw new Error("NEXT_PUBLIC_API_URL must use HTTPS in production.");
  }
  if (origin.hostname === "localhost" || origin.hostname === "127.0.0.1") {
    throw new Error("NEXT_PUBLIC_API_URL cannot target localhost in production.");
  }
  if (origin.username || origin.password || origin.search || origin.hash) {
    throw new Error(
      "NEXT_PUBLIC_API_URL must not contain credentials, query parameters, or a fragment.",
    );
  }
  if (origin.pathname !== "/") {
    throw new Error("NEXT_PUBLIC_API_URL must be an origin without a path.");
  }

  return origin.origin;
}
