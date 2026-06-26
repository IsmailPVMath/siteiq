import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { WorkflowTerrainMeshResponse } from "../types/workflow";
import { googleSatelliteLayer } from "../lib/mapTiles";

interface Props {
  mesh: WorkflowTerrainMeshResponse;
  boundaries?: { lat: number; lon: number }[][];
  height?: number;
}

const SLOPE_STOPS: { max: number; color: string; label: string }[] = [
  { max: 3, color: "#1b8a3a", label: "0–3%" },
  { max: 6, color: "#8bc34a", label: "3–6%" },
  { max: 10, color: "#f5a623", label: "6–10%" },
  { max: Infinity, color: "#d0021b", label: ">10%" },
];

function slopeColor(slope: number): string {
  for (const stop of SLOPE_STOPS) {
    if (slope <= stop.max) return stop.color;
  }
  return SLOPE_STOPS[SLOPE_STOPS.length - 1].color;
}

export function SlopeTopMap({ mesh, boundaries, height = 440 }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [opacity, setOpacity] = useState(0.6);
  const opacityRef = useRef(opacity);
  const [hover, setHover] = useState<{ x: number; y: number; slope: number } | null>(null);

  opacityRef.current = opacity;

  // Convert mesh local-metre vertices to lat/lon once.
  const latLngsRef = useRef<{ lat: number; lon: number }[]>([]);
  useEffect(() => {
    const mPerDegLat = 111_320;
    const mPerDegLon = 111_320 * Math.cos((mesh.origin.lat * Math.PI) / 180);
    latLngsRef.current = mesh.vertices.map(([x, y]) => ({
      lat: mesh.origin.lat + y / mPerDegLat,
      lon: mesh.origin.lon + x / mPerDegLon,
    }));
  }, [mesh]);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, { zoomControl: true, attributionControl: false }).setView(
      [mesh.origin.lat, mesh.origin.lon],
      15,
    );
    googleSatelliteLayer().addTo(map);
    mapRef.current = map;

    // Canvas overlay for slope triangles.
    const canvas = L.DomUtil.create("canvas", "slope-overlay-canvas") as HTMLCanvasElement;
    canvas.style.position = "absolute";
    canvas.style.top = "0";
    canvas.style.left = "0";
    canvas.style.pointerEvents = "none";
    canvas.style.zIndex = "400";
    map.getContainer().appendChild(canvas);
    canvasRef.current = canvas;

    const latLngs = latLngsRef.current;

    function redraw() {
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      const size = map.getSize();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.round(size.x * dpr);
      canvas.height = Math.round(size.y * dpr);
      canvas.style.width = `${size.x}px`;
      canvas.style.height = `${size.y}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size.x, size.y);
      ctx.globalAlpha = opacityRef.current;

      const pts = latLngs.map((p) => map.latLngToContainerPoint([p.lat, p.lon]));
      for (const face of mesh.faces) {
        const [a, b, c] = face;
        const pa = pts[a];
        const pb = pts[b];
        const pc = pts[c];
        if (!pa || !pb || !pc) continue;
        const meanSlope =
          ((mesh.slopes[a] ?? 0) + (mesh.slopes[b] ?? 0) + (mesh.slopes[c] ?? 0)) / 3;
        ctx.beginPath();
        ctx.moveTo(pa.x, pa.y);
        ctx.lineTo(pb.x, pb.y);
        ctx.lineTo(pc.x, pc.y);
        ctx.closePath();
        ctx.fillStyle = slopeColor(meanSlope);
        ctx.fill();
      }
      ctx.globalAlpha = 1;
    }

    redraw();
    map.on("move zoom moveend zoomend resize viewreset", redraw);

    // Boundary outline.
    const rings = boundaries && boundaries.length ? boundaries : [];
    let boundaryLayer: L.Polyline | null = null;
    if (rings.length) {
      boundaryLayer = L.polyline(
        rings.map((ring) => ring.map((p) => [p.lat, p.lon] as [number, number])),
        { color: "#ffffff", weight: 2, opacity: 0.95 },
      ).addTo(map);
      const b = boundaryLayer.getBounds();
      if (b.isValid()) map.fitBounds(b, { padding: [24, 24] });
    } else {
      const latArr = latLngs.map((p) => p.lat);
      const lonArr = latLngs.map((p) => p.lon);
      map.fitBounds(
        [
          [Math.min(...latArr), Math.min(...lonArr)],
          [Math.max(...latArr), Math.max(...lonArr)],
        ],
        { padding: [24, 24] },
      );
    }

    function onMouseMove(e: L.LeafletMouseEvent) {
      let bestD = Infinity;
      let bestSlope = 0;
      for (let i = 0; i < latLngs.length; i += 1) {
        const dLat = latLngs[i].lat - e.latlng.lat;
        const dLon = latLngs[i].lon - e.latlng.lng;
        const d = dLat * dLat + dLon * dLon;
        if (d < bestD) {
          bestD = d;
          bestSlope = mesh.slopes[i] ?? 0;
        }
      }
      setHover({ x: e.containerPoint.x, y: e.containerPoint.y, slope: bestSlope });
    }
    map.on("mousemove", onMouseMove);
    map.on("mouseout", () => setHover(null));

    let raf = 0;
    const ro = new ResizeObserver(() => {
      window.cancelAnimationFrame(raf);
      raf = window.requestAnimationFrame(() => {
        map.invalidateSize();
        redraw();
      });
    });
    ro.observe(containerRef.current);

    return () => {
      window.cancelAnimationFrame(raf);
      ro.disconnect();
      map.off();
      map.remove();
      canvas.remove();
      mapRef.current = null;
      canvasRef.current = null;
    };
  }, [mesh, boundaries]);

  // Redraw when opacity slider changes.
  useEffect(() => {
    const map = mapRef.current;
    if (map) map.fire("viewreset");
  }, [opacity]);

  return (
    <div className="slope-top-map" style={{ height }}>
      <div ref={containerRef} className="slope-top-leaflet" />
      <div className="slope-top-controls">
        <label htmlFor="slope-opacity">Slope overlay</label>
        <input
          id="slope-opacity"
          type="range"
          min="0"
          max="1"
          step="0.05"
          value={opacity}
          onChange={(e) => setOpacity(Number(e.target.value))}
        />
      </div>
      <div className="slope-top-legend" aria-hidden="true">
        {SLOPE_STOPS.map((s) => (
          <span key={s.label} className="slope-top-legend-item">
            <span className="slope-top-swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      {hover ? (
        <div className="slope-top-tooltip" style={{ left: hover.x + 12, top: hover.y + 12 }}>
          {hover.slope.toFixed(1)}% slope
        </div>
      ) : null}
    </div>
  );
}
