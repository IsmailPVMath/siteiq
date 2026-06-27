import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type * as GeoJSON from "geojson";
import { googleHybridLayer } from "../lib/mapTiles";

interface Props {
  center: { lat: number; lon: number };
  layoutGeoJson: GeoJSON.GeoJSON | null;
}

// Row numbers only become readable once individual rows are a few px apart.
// Below this zoom they collapse into an unreadable strip, so we hide them.
const ROW_LABEL_MIN_ZOOM = 18;

export function LayoutPreviewMap({ center, layoutGeoJson }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layoutLayerRef = useRef<L.GeoJSON | null>(null);
  const labelLayerRef = useRef<L.LayerGroup | null>(null);
  const labelPointsRef = useRef<{ lat: number; lon: number; n: number }[]>([]);

  function refreshLabels() {
    const map = mapRef.current;
    const group = labelLayerRef.current;
    if (!map || !group) return;
    group.clearLayers();
    if (map.getZoom() < ROW_LABEL_MIN_ZOOM) return;
    for (const p of labelPointsRef.current) {
      L.marker([p.lat, p.lon], {
        interactive: false,
        keyboard: false,
        icon: L.divIcon({
          className: "pv-row-number",
          html: String(p.n),
          iconSize: undefined,
        }),
      }).addTo(group);
    }
  }

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: true }).setView(
      [center.lat, center.lon],
      15,
    );
    googleHybridLayer().addTo(map);
    mapRef.current = map;
    labelLayerRef.current = L.layerGroup().addTo(map);
    map.on("zoomend", refreshLabels);
    let raf = 0;
    const ro = new ResizeObserver(() => {
      window.cancelAnimationFrame(raf);
      raf = window.requestAnimationFrame(() => map.invalidateSize());
    });
    ro.observe(containerRef.current);
    return () => {
      window.cancelAnimationFrame(raf);
      ro.disconnect();
      map.off("zoomend", refreshLabels);
      map.remove();
      mapRef.current = null;
      layoutLayerRef.current = null;
      labelLayerRef.current = null;
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
    labelPointsRef.current = [];
    labelLayerRef.current?.clearLayers();
    if (!layoutGeoJson) return;

    const isCollection = layoutGeoJson.type === "FeatureCollection";
    const hasModules =
      isCollection &&
      layoutGeoJson.features.some((f) => f.properties?.kind === "pv_module");

    if (isCollection) {
      for (const f of layoutGeoJson.features) {
        if (f.properties?.kind === "pv_axis_label" && f.geometry?.type === "Point") {
          const [lon, lat] = f.geometry.coordinates as [number, number];
          labelPointsRef.current.push({ lat, lon, n: f.properties.row_number });
        }
      }
    }

    layoutLayerRef.current = L.geoJSON(layoutGeoJson as GeoJSON.GeoJsonObject, {
      // Row-number points are rendered separately (zoom-gated) — skip here.
      filter: (feature) => feature.properties?.kind !== "pv_axis_label",
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
        if (kind === "pv_axis") {
          return { color: "#6b7280", weight: 0.8, opacity: 0.85 };
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
        } else if (kind === "pv_axis") {
          layer.bindTooltip(`Row ${feature.properties.row_number} axis`, { sticky: true });
        }
      },
    }).addTo(map);

    const bounds = layoutLayerRef.current.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [20, 20] });
    }
    refreshLabels();
  }, [layoutGeoJson]);

  return <div ref={containerRef} className="layout-preview-map" aria-label="Layout preview map" />;
}
