/** Slope grade (%) → angle (°) for TerrainIQ display. */

export function slopePctToDeg(pct: number): number {
  return (Math.atan(pct / 100) * 180) / Math.PI;
}

export const SLOPE_DEG_BANDS = [
  { lo: 0, hi: 2.5, label: "0 – 2.5° (excellent)", color: "#14532d" },
  { lo: 2.5, hi: 5, label: "2.5 – 5° (good)", color: "#1b8a3a" },
  { lo: 5, hi: 7.5, label: "5 – 7.5° (acceptable)", color: "#eab308" },
  { lo: 7.5, hi: 10, label: "7.5 – 10° (challenging)", color: "#f97316" },
  { lo: 10, hi: 20, label: "10 – 20° (critical)", color: "#d0021b" },
] as const;

export function slopeColorFromPct(pct: number): string {
  const deg = slopePctToDeg(pct);
  for (const band of SLOPE_DEG_BANDS) {
    if (deg <= band.hi) return band.color;
  }
  return SLOPE_DEG_BANDS[SLOPE_DEG_BANDS.length - 1].color;
}

export function formatSlopeDeg(pct: number, digits = 1): string {
  return `${slopePctToDeg(pct).toFixed(digits)}°`;
}
