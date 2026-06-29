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
