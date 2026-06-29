export function parseCoordinates(text: string): { lat: number; lon: number } | null {
  const raw = (text || "").trim();
  if (!raw) return null;

  const plain = raw.match(/^(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)/);
  if (plain) {
    return { lat: Number(plain[1]), lon: Number(plain[2]) };
  }

  const patterns = [
    /@(-?\d+\.\d+),(-?\d+\.\d+)/,
    /q=(-?\d+\.\d+),(-?\d+\.\d+)/,
    /ll=(-?\d+\.\d+),(-?\d+\.\d+)/,
    /place\/[^/]+\/@(-?\d+\.\d+),(-?\d+\.\d+)/,
  ];
  for (const re of patterns) {
    const m = raw.match(re);
    if (m) return { lat: Number(m[1]), lon: Number(m[2]) };
  }
  return null;
}

/** Square site envelope (ha) centered on a pin — geodesic approximation. */
export function squareBoundaryFromPin(
  lat: number,
  lon: number,
  areaHa: number,
): { lat: number; lon: number }[] {
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || areaHa <= 0) return [];
  const sideM = Math.sqrt(areaHa * 10_000);
  const halfM = sideM / 2;
  const cosLat = Math.cos((lat * Math.PI) / 180);
  const dLat = halfM / 111_320;
  const dLon = halfM / (111_320 * Math.max(cosLat, 1e-6));
  const fix = (n: number) => Number(n.toFixed(7));
  return [
    { lat: fix(lat + dLat), lon: fix(lon - dLon) },
    { lat: fix(lat + dLat), lon: fix(lon + dLon) },
    { lat: fix(lat - dLat), lon: fix(lon + dLon) },
    { lat: fix(lat - dLat), lon: fix(lon - dLon) },
  ];
}

function ringCenter(ring: { lat: number; lon: number }[]): { lat: number; lon: number } | null {
  if (!ring.length) return null;
  const lat = ring.reduce((s, p) => s + p.lat, 0) / ring.length;
  const lon = ring.reduce((s, p) => s + p.lon, 0) / ring.length;
  return { lat, lon };
}

/** True when an assumed envelope already matches pin + target area. */
export function assumedEnvelopeMatches(
  ring: { lat: number; lon: number }[] | undefined,
  lat: number,
  lon: number,
  areaHa: number,
): boolean {
  if (!ring || ring.length < 4 || areaHa <= 0) return false;
  const center = ringCenter(ring);
  if (!center) return false;
  const moved =
    Math.abs(center.lat - lat) > 1e-5 || Math.abs(center.lon - lon) > 1e-5;
  if (moved) return false;
  const ha = polygonAreaHa(ring);
  return Math.abs(ha - areaHa) < Math.max(0.05, areaHa * 0.02);
}

/** Approximate polygon area in hectares (spherical shoelace). */
export function polygonAreaHa(coords: { lat: number; lon: number }[]): number {
  if (coords.length < 3) return 0;
  const R = 6_371_000;
  let area = 0;
  const n = coords.length;
  for (let i = 0; i < n; i++) {
    const lat1 = (coords[i].lat * Math.PI) / 180;
    const lon1 = (coords[i].lon * Math.PI) / 180;
    const lat2 = (coords[(i + 1) % n].lat * Math.PI) / 180;
    const lon2 = (coords[(i + 1) % n].lon * Math.PI) / 180;
    area += (lon2 - lon1) * (2 + Math.sin(lat1) + Math.sin(lat2));
  }
  return Math.round((Math.abs(area) * R * R) / 2 / 10_000 * 100) / 100;
}
