import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export interface MapBoundary {
  lat: number;
  lon: number;
}

interface Props {
  lat: number;
  lon: number;
  boundary?: MapBoundary[];
  onPick: (lat: number, lon: number) => void;
}

const pinIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

export function SiteMap({ lat, lon, boundary, onPick }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const polygonRef = useRef<L.Polygon | null>(null);
  const onPickRef = useRef(onPick);
  onPickRef.current = onPick;

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = L.map(containerRef.current, { zoomControl: true }).setView([lat, lon], 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);

    markerRef.current = L.marker([lat, lon], { icon: pinIcon, draggable: true }).addTo(map);
    markerRef.current.on("dragend", () => {
      const pos = markerRef.current?.getLatLng();
      if (pos) onPickRef.current(pos.lat, pos.lng);
    });

    map.on("click", (e: L.LeafletMouseEvent) => {
      onPickRef.current(e.latlng.lat, e.latlng.lng);
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current || !markerRef.current) return;
    markerRef.current.setLatLng([lat, lon]);
    mapRef.current.panTo([lat, lon], { animate: true });
  }, [lat, lon]);

  useEffect(() => {
    if (!mapRef.current) return;
    if (polygonRef.current) {
      polygonRef.current.remove();
      polygonRef.current = null;
    }
    if (boundary && boundary.length >= 3) {
      const latlngs = boundary.map((p) => [p.lat, p.lon] as [number, number]);
      polygonRef.current = L.polygon(latlngs, {
        color: "#1d9e52",
        fillColor: "#1d9e52",
        fillOpacity: 0.2,
        weight: 2,
      }).addTo(mapRef.current);
      mapRef.current.fitBounds(polygonRef.current.getBounds(), { padding: [24, 24] });
    }
  }, [boundary]);

  return <div ref={containerRef} className="site-map" aria-label="Interactive site map" />;
}
