/** RevenueIQ staging gate — set VITE_ENABLE_REVENUEIQ=true on Cloudflare Preview only. */
export const REVENUEIQ_ENABLED =
  import.meta.env.VITE_ENABLE_REVENUEIQ === "true" ||
  import.meta.env.VITE_ENABLE_REVENUEIQ === "1";
