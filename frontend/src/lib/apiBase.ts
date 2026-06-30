const PRODUCTION_API = "https://api.pvmath.com";
const STAGING_API = "https://pvmath-api-staging-production.up.railway.app";

/** Resolve API base URL at runtime (Cloudflare preview builds may omit VITE_API_URL). */
export function getApiUrl(): string {
  const explicit = import.meta.env.VITE_API_URL?.trim();
  if (explicit) return explicit.replace(/\/$/, "");

  if (typeof window !== "undefined" && /\.pages\.dev$/i.test(window.location.hostname)) {
    const staging = import.meta.env.VITE_STAGING_API_URL?.trim() || STAGING_API;
    return staging.replace(/\/$/, "");
  }

  return PRODUCTION_API;
}
