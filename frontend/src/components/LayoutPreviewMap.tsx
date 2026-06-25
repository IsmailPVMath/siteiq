import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type * as GeoJSON from "geojson";

interface Props {
  center: { lat: number; lon: number };
  layoutGeoJson: GeoJSON.GeoJSON | null;
}

export function LayoutPreviewMap({ center, layoutGeoJson }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layoutLayerRef = useRef<L.GeoJSON | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: true }).setView(
      [center.lat, center.lon],
      15,
    );
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "&copy; OpenStreetMap",
      maxZoom: 21,
    }).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layoutLayerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    map.setView([center.lat, center.lon], map.getZoom());
  }, [center.lat, center.lon]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (layoutLayerRef.current) {
      layoutLayerRef.current.remove();
      layoutLayerRef.current = null;
    }
    if (!layoutGeoJson) return;

    layoutLayerRef.current = L.geoJSON(layoutGeoJson as GeoJSON.GeoJsonObject, {
      style: (feature) => {
        const kind = feature?.properties?.kind;
        if (kind === "pv_row") {
          return { color: "#14532d", fillColor: "#22c55e", fillOpacity: 0.72, weight: 0.6 };
        }
        if (kind === "setback_inset") {
          return {
            color: "#64748b",
            fillOpacity: 0,
            weight: 1,
            dashArray: "4 4",
          };
        }
        return { color: "#7c3aed", fillOpacity: 0.03, weight: 2 };
      },
      onEachFeature: (feature, layer) => {
        if (feature.properties?.kind === "pv_row") {
          const row = feature.properties.row_index;
          const modules = feature.properties.n_modules;
          layer.bindTooltip(`Row ${row}: ${modules} modules`, { sticky: true });
        }
      },
    }).addTo(map);

    const bounds = layoutLayerRef.current.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [20, 20] });
    }
  }, [layoutGeoJson]);

  return <div ref={containerRef} className="layout-preview-map" aria-label="Layout preview map" />;
}
