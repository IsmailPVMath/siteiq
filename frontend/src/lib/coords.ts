/** Parse Google Maps URLs or plain "lat, lon" paste (SiteIQ parity). */

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
