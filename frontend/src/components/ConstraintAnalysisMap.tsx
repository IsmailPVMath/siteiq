import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type * as GeoJSON from "geojson";

export interface LayerStyle {
  color: string;
  fillColor: string;
}

interface Props {
  lat: number;
  lon: number;
  siteBoundary?: GeoJSON.GeoJSON | null;
  constraintLayers?: Record<string, GeoJSON.FeatureCollection>;
  layerStyles?: Record<string, LayerStyle>;
  buildableArea?: GeoJSON.GeoJSON | null;
  excludedArea?: GeoJSON.GeoJSON | null;
  /** Default: satellite + OSM street */
  baseLayer?: "osm" | "satellite" | "both";
}

const SAT_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}";

export function ConstraintAnalysisMap({
  lat,
  lon,
  siteBoundary,
  constraintLayers,
  layerStyles,
  buildableArea,
  excludedArea,
  baseLayer = "both",
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const baseLayersRef = useRef<L.LayerGroup | null>(null);
  const overlayRef = useRef<L.LayerGroup | null>(null);
  const [visible, setVisible] = useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {
      site: true,
      buildable: true,
      excluded: true,
    };
    Object.keys(constraintLayers || {}).forEach((k) => {
      init[k] = true;
    });
    return init;
  });

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: true }).setView([lat, lon], 14);
    const bases = L.layerGroup().addTo(map);
    if (baseLayer === "satellite" || baseLayer === "both") {
      L.tileLayer(SAT_URL, { attribution: "Esri", maxZoom: 19 }).addTo(bases);
    }
    if (baseLayer === "osm" || baseLayer === "both") {
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: "&copy; OpenStreetMap",
        maxZoom: 19,
        opacity: baseLayer === "both" ? 0.35 : 1,
      }).addTo(bases);
    }
    const overlays = L.layerGroup().addTo(map);
    baseLayersRef.current = bases;
    overlayRef.current = overlays;
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
      baseLayersRef.current = null;
      overlayRef.current = null;
    };
  }, [baseLayer, lat, lon]);

  useEffect(() => {
    const map = mapRef.current;
    const group = overlayRef.current;
    if (!map || !group) return;
    group.clearLayers();

    const addGeo = (
      data: GeoJSON.GeoJSON | null | undefined,
      style: L.PathOptions,
      key: string,
    ) => {
      if (!data || !visible[key]) return;
      L.geoJSON(data as GeoJSON.GeoJsonObject, {
        style: () => style,
        interactive: false,
      }).addTo(group);
    };

    addGeo(siteBoundary ?? null, { color: "#7c3aed", weight: 3, fillOpacity: 0 }, "site");

    Object.entries(constraintLayers || {}).forEach(([cat, fc]) => {
      const st = layerStyles?.[cat];
      addGeo(
        fc,
        {
          color: st?.color || "#64748b",
          fillColor: st?.fillColor || "#94a3b8",
          fillOpacity: 0.35,
          weight: 1.5,
        },
        cat,
      );
    });

    addGeo(excludedArea ?? null, {
      color: "#ef4444",
      fillColor: "#fca5a5",
      fillOpacity: 0.45,
      weight: 1,
      dashArray: "4 3",
    }, "excluded");

    addGeo(buildableArea ?? null, {
      color: "#157a40",
      fillColor: "#4ade80",
      fillOpacity: 0.35,
      weight: 2,
    }, "buildable");

    const bounds = L.latLngBounds([]);
    group.eachLayer((layer) => {
      if ("getBounds" in layer && typeof layer.getBounds === "function") {
        bounds.extend(layer.getBounds());
      }
    });
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [20, 20] });
    } else {
      map.setView([lat, lon], 14);
    }
  }, [siteBoundary, constraintLayers, layerStyles, buildableArea, excludedArea, visible, lat, lon]);

  const layerKeys = Object.keys(constraintLayers || {});

  return (
    <div className="constraint-map-wrap">
      <div className="constraint-map-legend">
        <label className="constraint-legend-item">
          <input
            type="checkbox"
            checked={visible.site}
            onChange={(e) => setVisible((v) => ({ ...v, site: e.target.checked }))}
          />
          <span className="swatch" style={{ background: "#7c3aed" }} />
          Site boundary
        </label>
        {layerKeys.map((k) => (
          <label key={k} className="constraint-legend-item">
            <input
              type="checkbox"
              checked={visible[k] ?? true}
              onChange={(e) => setVisible((v) => ({ ...v, [k]: e.target.checked }))}
            />
            <span
              className="swatch"
              style={{ background: layerStyles?.[k]?.fillColor || "#94a3b8" }}
            />
            {k.replace(/_/g, " ")}
          </label>
        ))}
        <label className="constraint-legend-item">
          <input
            type="checkbox"
            checked={visible.excluded}
            onChange={(e) => setVisible((v) => ({ ...v, excluded: e.target.checked }))}
          />
          <span className="swatch" style={{ background: "#fca5a5" }} />
          Excluded
        </label>
        <label className="constraint-legend-item">
          <input
            type="checkbox"
            checked={visible.buildable}
            onChange={(e) => setVisible((v) => ({ ...v, buildable: e.target.checked }))}
          />
          <span className="swatch" style={{ background: "#4ade80" }} />
          Buildable
        </label>
      </div>
      <div ref={containerRef} className="constraint-map site-map" aria-label="GIS constraint map" />
    </div>
  );
}
