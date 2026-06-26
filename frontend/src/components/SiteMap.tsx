import { useEffect, useRef } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "leaflet-draw";
import "leaflet-draw/dist/leaflet.draw.css";
import type * as GeoJSON from "geojson";

export interface MapBoundary {
  lat: number;
  lon: number;
}

type DrawMode = "site" | "restriction";

export interface OverlayParcel {
  coords: MapBoundary[];
  enabled: boolean;
}

interface Props {
  lat: number;
  lon: number;
  siteBoundary?: MapBoundary[];
  restrictions?: MapBoundary[][];
  overlayParcels?: OverlayParcel[];
  buildableAreaGeoJson?: GeoJSON.GeoJSON | null;
  drawMode?: DrawMode;
  onPick: (lat: number, lon: number) => void;
  onSiteBoundaryChange?: (boundary: MapBoundary[] | undefined) => void;
  onRestrictionsChange?: (restrictions: MapBoundary[][]) => void;
}

const pinIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
});

export function SiteMap({
  lat,
  lon,
  siteBoundary,
  restrictions,
  overlayParcels,
  buildableAreaGeoJson,
  drawMode = "site",
  onPick,
  onSiteBoundaryChange,
  onRestrictionsChange,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const markerRef = useRef<L.Marker | null>(null);
  const drawLayerRef = useRef<L.FeatureGroup | null>(null);
  const parcelLayerRef = useRef<L.FeatureGroup | null>(null);
  const buildableLayerRef = useRef<L.GeoJSON | null>(null);
  const onPickRef = useRef(onPick);
  const drawModeRef = useRef<DrawMode>(drawMode);
  const onSiteBoundaryChangeRef = useRef(onSiteBoundaryChange);
  const onRestrictionsChangeRef = useRef(onRestrictionsChange);
  onPickRef.current = onPick;
  drawModeRef.current = drawMode;
  onSiteBoundaryChangeRef.current = onSiteBoundaryChange;
  onRestrictionsChangeRef.current = onRestrictionsChange;

  function normalizeBoundary(latlngs: L.LatLng[]): MapBoundary[] {
    return latlngs.map((p) => ({
      lat: Number(p.lat.toFixed(7)),
      lon: Number(p.lng.toFixed(7)),
    }));
  }

  function syncBoundaryFromMap() {
    const featureGroup = drawLayerRef.current;
    if (!featureGroup) return;
    const sitePolys: MapBoundary[][] = [];
    const restrictionPolys: MapBoundary[][] = [];
    featureGroup.eachLayer((layer) => {
      if (!(layer instanceof L.Polygon)) return;
      const role = (layer as L.Polygon & { _pvmRole?: DrawMode })._pvmRole || "restriction";
      const latlngs = layer.getLatLngs();
      const ring = Array.isArray(latlngs[0]) ? (latlngs[0] as L.LatLng[]) : [];
      const coords = normalizeBoundary(ring);
      if (coords.length < 3) return;
      if (role === "site") sitePolys.push(coords);
      else restrictionPolys.push(coords);
    });
    onSiteBoundaryChangeRef.current?.(sitePolys[0]);
    onRestrictionsChangeRef.current?.(restrictionPolys);
  }

  function clearDrawLayers() {
    if (drawLayerRef.current) {
      drawLayerRef.current.clearLayers();
    }
  }

  function addRolePolygon(coords: MapBoundary[], role: DrawMode) {
    if (!drawLayerRef.current || coords.length < 3) return;
    const layer = L.polygon(
      coords.map((p) => [p.lat, p.lon] as [number, number]),
      {
        color: role === "site" ? "#1d9e52" : "#f59e0b",
        fillColor: role === "site" ? "#1d9e52" : "#f59e0b",
        fillOpacity: role === "site" ? 0.2 : 0.18,
        weight: 2,
      },
    ) as L.Polygon & { _pvmRole?: DrawMode };
    layer._pvmRole = role;
    layer.addTo(drawLayerRef.current);
  }

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

    parcelLayerRef.current = new L.FeatureGroup().addTo(map);
    const drawnItems = new L.FeatureGroup().addTo(map);
    drawLayerRef.current = drawnItems;
    const drawControl = new L.Control.Draw({
      draw: {
        polygon: {
          allowIntersection: false,
          shapeOptions: {
            color: "#1d9e52",
            fillColor: "#1d9e52",
            fillOpacity: 0.2,
            weight: 2,
          },
        },
        rectangle: false,
        circle: false,
        marker: false,
        polyline: false,
        circlemarker: false,
      },
      edit: {
        featureGroup: drawnItems,
      },
    });
    map.addControl(drawControl);

    map.on(L.Draw.Event.CREATED, (e: any) => {
      const layer = e.layer as L.Polygon & { _pvmRole?: DrawMode };
      layer._pvmRole = drawModeRef.current === "site" ? "site" : "restriction";
      if (layer instanceof L.Polygon) {
        layer.setStyle({
          color: layer._pvmRole === "site" ? "#1d9e52" : "#f59e0b",
          fillColor: layer._pvmRole === "site" ? "#1d9e52" : "#f59e0b",
        });
      }
      if (layer._pvmRole === "site") {
        const toRemove: L.Layer[] = [];
        drawnItems.eachLayer((l) => {
          if ((l as L.Polygon & { _pvmRole?: DrawMode })._pvmRole === "site") {
            toRemove.push(l);
          }
        });
        toRemove.forEach((l) => drawnItems.removeLayer(l));
      }
      drawnItems.addLayer(layer);
      syncBoundaryFromMap();
    });
    map.on(L.Draw.Event.EDITED, () => syncBoundaryFromMap());
    map.on(L.Draw.Event.DELETED, () => syncBoundaryFromMap());

    mapRef.current = map;

    // Recompute tiles/size whenever the container resizes (e.g. the account
    // sidebar is collapsed or resized) so the map never shows a grey gap.
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
      drawLayerRef.current = null;
      parcelLayerRef.current = null;
      buildableLayerRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!mapRef.current || !markerRef.current) return;
    markerRef.current.setLatLng([lat, lon]);
    mapRef.current.panTo([lat, lon], { animate: true });
  }, [lat, lon]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !drawLayerRef.current) return;
    clearDrawLayers();
    if (siteBoundary && siteBoundary.length >= 3) {
      addRolePolygon(siteBoundary, "site");
    }
    (restrictions || []).forEach((ring) => {
      if (ring.length >= 3) addRolePolygon(ring, "restriction");
    });
    const groupBounds = drawLayerRef.current.getBounds();
    if (groupBounds.isValid()) {
      map.fitBounds(groupBounds, { padding: [24, 24] });
    }
  }, [siteBoundary, restrictions]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = parcelLayerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    (overlayParcels || []).forEach((parcel) => {
      if (parcel.coords.length < 3) return;
      const color = parcel.enabled ? "#1d9e52" : "#94a3b8";
      L.polygon(
        parcel.coords.map((p) => [p.lat, p.lon] as [number, number]),
        {
          color,
          fillColor: color,
          fillOpacity: parcel.enabled ? 0.22 : 0.06,
          weight: parcel.enabled ? 2 : 1,
          dashArray: parcel.enabled ? undefined : "5 4",
          interactive: false,
        },
      ).addTo(layer);
    });
    const enabled = (overlayParcels || []).filter((p) => p.enabled && p.coords.length >= 3);
    if (enabled.length) {
      const bounds = L.latLngBounds(
        enabled.flatMap((p) => p.coords.map((c) => [c.lat, c.lon] as [number, number])),
      );
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24] });
    }
  }, [overlayParcels]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (buildableLayerRef.current) {
      buildableLayerRef.current.remove();
      buildableLayerRef.current = null;
    }
    if (buildableAreaGeoJson) {
      buildableLayerRef.current = L.geoJSON(buildableAreaGeoJson as GeoJSON.GeoJsonObject, {
        style: {
          color: "#157a40",
          fillColor: "#4ade80",
          fillOpacity: 0.2,
          weight: 2,
          dashArray: "4 4",
        },
      }).addTo(map);
    }
  }, [buildableAreaGeoJson]);

  return <div ref={containerRef} className="site-map" aria-label="Interactive site map" />;
}
