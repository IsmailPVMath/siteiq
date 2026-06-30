/** Multi-point alignment guide → single constant layout azimuth (degrees). */

export interface LatLon {
  lat: number;
  lon: number;
}

export function segmentBearingDeg(a: LatLon, b: LatLon): number {
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  const bearing = (Math.atan2(y, x) * 180) / Math.PI;
  return (bearing + 360) % 360;
}

function haversineM(a: LatLon, b: LatLon): number {
  const r = 6_371_000;
  const lat1 = (a.lat * Math.PI) / 180;
  const lat2 = (b.lat * Math.PI) / 180;
  const dLat = lat2 - lat1;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * r * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function bearingToLayoutAzimuth(bearing: number): number {
  let b = ((bearing % 360) + 360) % 360;
  if (b > 180) b -= 180;
  if (b < 90) b = 180 - b;
  return Math.max(90, Math.min(270, b));
}

/** Length-weighted average segment bearing → one azimuth for the whole PV area. */
export function azimuthFromAlignmentGuide(points: LatLon[]): number | null {
  if (points.length < 2) return null;
  let sumX = 0;
  let sumY = 0;
  for (let i = 0; i < points.length - 1; i += 1) {
    const a = points[i];
    const b = points[i + 1];
    const length = haversineM(a, b);
    if (length < 1e-3) continue;
    const bearing = (segmentBearingDeg(a, b) * Math.PI) / 180;
    sumX += length * Math.sin(bearing);
    sumY += length * Math.cos(bearing);
  }
  if (sumX === 0 && sumY === 0) return null;
  const avg = (Math.atan2(sumX, sumY) * 180) / Math.PI;
  const bearing = ((avg % 360) + 360) % 360;
  return Math.round(bearingToLayoutAzimuth(bearing) * 10) / 10;
}

export function layoutEffectiveAzimuth(
  source: "default" | "guide",
  guide: LatLon[],
  manualAzimuth: number,
): number {
  if (source === "guide") {
    const derived = azimuthFromAlignmentGuide(guide);
    if (derived != null) return derived;
  }
  return manualAzimuth;
}
