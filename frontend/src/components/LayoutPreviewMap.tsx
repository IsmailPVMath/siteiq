import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type * as GeoJSON from "geojson";
import { googleHybridLayer } from "../lib/mapTiles";

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
    googleHybridLayer().addTo(map);
    mapRef.current = map;
    let raf = 0;
    const ro = new ResizeObserver(() => {
      window.cancelAnimationFrame(raf);
      raf = window.requestAnimationFrame(() => map.invalidateSize());
    });
    ro.observe(containerRef.current);
    return () => {
      window.cancelAnimationFrame(raf);
      ro.disconnect();
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

    const isCollection = layoutGeoJson.type === "FeatureCollection";
    const hasModules =
      isCollection &&
      layoutGeoJson.features.some((f) => f.properties?.kind === "pv_module");

    layoutLayerRef.current = L.geoJSON(layoutGeoJson as GeoJSON.GeoJsonObject, {
      style: (feature) => {
        const kind = feature?.properties?.kind;
        if (kind === "pv_module") {
          return {
            color: "#1d4ed8",
            fillColor: "#3b82f6",
            fillOpacity: 0.88,
            weight: 0.35,
          };
        }
        if (kind === "pv_row") {
          if (hasModules) {
            return { opacity: 0, fillOpacity: 0, weight: 0 };
          }
          return { color: "#1d4ed8", fillColor: "#3b82f6", fillOpacity: 0.75, weight: 0.5 };
        }
        if (kind === "buildable_parcel" || kind === "setback_inset") {
          return {
            color: "#0ea5e9",
            fillOpacity: 0,
            weight: 2,
            dashArray: "6 4",
          };
        }
        return { color: "#7c3aed", fillOpacity: 0.02, weight: 2 };
      },
      onEachFeature: (feature, layer) => {
        const kind = feature.properties?.kind;
        if (kind === "pv_module") {
          const idx = feature.properties.string_index;
          const mps = feature.properties.modules_per_string;
          layer.bindTooltip(`String ${idx} · ${mps} modules`, { sticky: true });
        } else if (kind === "pv_row" && !hasModules) {
          const row = feature.properties.row_index;
          const modules = feature.properties.n_modules;
          layer.bindTooltip(`Row ${row}: ${modules} modules`, { sticky: true });
        } else if (kind === "buildable_parcel") {
          layer.bindTooltip("Buildable parcel", { sticky: true });
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
