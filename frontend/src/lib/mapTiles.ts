import L from "leaflet";

// Google imagery tiles — matches the Streamlit SiteIQ/TerrainIQ maps the user
// found "so good". lyrs=s = pure satellite, lyrs=y = hybrid (satellite + labels/roads).
export const GOOGLE_SATELLITE_URL = "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}";
export const GOOGLE_HYBRID_URL = "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}";

export function googleSatelliteLayer(opts?: L.TileLayerOptions): L.TileLayer {
  return L.tileLayer(GOOGLE_SATELLITE_URL, {
    attribution: "Imagery &copy; Google",
    maxZoom: 21,
    subdomains: [],
    ...opts,
  });
}

export function googleHybridLayer(opts?: L.TileLayerOptions): L.TileLayer {
  return L.tileLayer(GOOGLE_HYBRID_URL, {
    attribution: "Imagery &copy; Google",
    maxZoom: 21,
    subdomains: [],
    ...opts,
  });
}
