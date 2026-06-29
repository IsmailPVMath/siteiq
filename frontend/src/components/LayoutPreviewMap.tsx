import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type * as GeoJSON from "geojson";
import { googleHybridLayer } from "../lib/mapTiles";

interface Props {
  center: { lat: number; lon: number };
  layoutGeoJson: GeoJSON.GeoJSON | null;
  excludedGeoJson?: GeoJSON.GeoJSON | null;
  constraintLayers?: Record<string, GeoJSON.GeoJSON | null> | null;
}

export function LayoutPreviewMap({ center, layoutGeoJson, excludedGeoJson, constraintLayers }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layoutLayerRef = useRef<L.GeoJSON | null>(null);
  const exclusionLayerRef = useRef<L.GeoJSON | null>(null);

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
      exclusionLayerRef.current = null;
    };
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (exclusionLayerRef.current) {
      exclusionLayerRef.current.remove();
      exclusionLayerRef.current = null;
    }

    const features: GeoJSON.Feature[] = [];
    if (excludedGeoJson) {
      if (excludedGeoJson.type === "FeatureCollection") {
        features.push(...excludedGeoJson.features);
      } else if (excludedGeoJson.type === "Feature") {
        features.push(excludedGeoJson);
      } else {
        features.push({ type: "Feature", properties: { category: "excluded" }, geometry: excludedGeoJson });
      }
    }
    if (constraintLayers) {
      for (const [key, layer] of Object.entries(constraintLayers)) {
        if (!layer) continue;
        if (layer.type === "FeatureCollection") {
          for (const f of layer.features) {
            features.push({
              ...f,
              properties: { ...f.properties, category: f.properties?.category ?? key },
            });
          }
        }
      }
    }
    if (!features.length) return;

    exclusionLayerRef.current = L.geoJSON(
      { type: "FeatureCollection", features } as GeoJSON.FeatureCollection,
      {
        style: (feature) => {
          const cat = String(feature?.properties?.category ?? "");
          if (cat === "water" || cat === "waterway") {
            return { color: "#1d4ed8", fillColor: "#3b82f6", fillOpacity: 0.35, weight: 1.2 };
          }
          if (cat === "building") {
            return { color: "#7f1d1d", fillColor: "#ef4444", fillOpacity: 0.4, weight: 1 };
          }
          if (cat === "forest" || cat === "wood" || cat === "vegetation") {
            return { color: "#14532d", fillColor: "#22c55e", fillOpacity: 0.3, weight: 1 };
          }
          return {
            color: "#dc2626",
            fillColor: "#fca5a5",
            fillOpacity: 0.42,
            weight: 1.5,
            dashArray: "5 4",
          };
        },
        onEachFeature: (feature, layer) => {
          const label =
            (feature.properties?.label as string) ||
            (feature.properties?.category as string) ||
            "Excluded";
          layer.bindTooltip(label, { sticky: true });
        },
      },
    ).addTo(map);
  }, [excludedGeoJson, constraintLayers]);

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
            color: "#93c5fd",
            fillColor: "#bfdbfe",
            fillOpacity: 0.45,
            weight: 0.25,
          };
        }
        if (kind === "tracker_unit") {
          const fill = (feature?.properties?.fill as string) || "#2563eb";
          const stroke = (feature?.properties?.stroke as string) || "#1e40af";
          return {
            color: stroke,
            fillColor: fill,
            fillOpacity: 0.72,
            weight: 1.4,
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
        } else if (kind === "tracker_unit") {
          const label = feature.properties.unit_label || `${feature.properties.unit_strings}S`;
          layer.bindTooltip(`Tracker ${label}`, { sticky: true });
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
    if (exclusionLayerRef.current) {
      bounds.extend(exclusionLayerRef.current.getBounds());
    }
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [20, 20] });
    }
  }, [layoutGeoJson]);

  return <div ref={containerRef} className="layout-preview-map" aria-label="Layout preview map" />;
}
