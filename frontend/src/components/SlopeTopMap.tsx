import { useEffect, useRef, useState } from "react";
import type { WorkflowTerrainMeshResponse } from "../types/workflow";

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

function localXY(lat: number, lon: number, originLat: number, originLon: number) {
  const mPerDegLat = 111_320;
  const mPerDegLon = 111_320 * Math.cos((originLat * Math.PI) / 180);
  return { x: (lon - originLon) * mPerDegLon, y: (lat - originLat) * mPerDegLat };
}

export function SlopeTopMap({ mesh, boundaries, height = 440 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ x: number; y: number; slope: number } | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const wrap = wrapRef.current;
    if (!canvas || !wrap) return;
    const cv = canvas;
    const wrapEl = wrap;

    const vertices = mesh.vertices;
    if (!vertices.length) return;

    let xMin = Infinity;
    let xMax = -Infinity;
    let yMin = Infinity;
    let yMax = -Infinity;
    for (const [x, y] of vertices) {
      if (x < xMin) xMin = x;
      if (x > xMax) xMax = x;
      if (y < yMin) yMin = y;
      if (y > yMax) yMax = y;
    }
    const dataW = Math.max(1, xMax - xMin);
    const dataH = Math.max(1, yMax - yMin);

    function draw() {
      const ctx = cv.getContext("2d");
      if (!ctx) return;
      const cssW = wrapEl.clientWidth || 600;
      const cssH = height;
      const dpr = window.devicePixelRatio || 1;
      cv.width = Math.round(cssW * dpr);
      cv.height = Math.round(cssH * dpr);
      cv.style.width = `${cssW}px`;
      cv.style.height = `${cssH}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, cssW, cssH);

      const pad = 8;
      const availW = cssW - pad * 2;
      const availH = cssH - pad * 2;
      const scale = Math.min(availW / dataW, availH / dataH);
      const drawW = dataW * scale;
      const drawH = dataH * scale;
      const offX = pad + (availW - drawW) / 2;
      const offY = pad + (availH - drawH) / 2;

      const toScreen = (x: number, y: number): [number, number] => [
        offX + (x - xMin) * scale,
        offY + (yMax - y) * scale,
      ];

      ctx.fillStyle = "#eef1ee";
      ctx.fillRect(offX, offY, drawW, drawH);

      for (const face of mesh.faces) {
        const [a, b, c] = face;
        const va = vertices[a];
        const vb = vertices[b];
        const vc = vertices[c];
        if (!va || !vb || !vc) continue;
        const meanSlope =
          ((mesh.slopes[a] ?? 0) + (mesh.slopes[b] ?? 0) + (mesh.slopes[c] ?? 0)) / 3;
        const [ax, ay] = toScreen(va[0], va[1]);
        const [bx, by] = toScreen(vb[0], vb[1]);
        const [cx, cy] = toScreen(vc[0], vc[1]);
        ctx.beginPath();
        ctx.moveTo(ax, ay);
        ctx.lineTo(bx, by);
        ctx.lineTo(cx, cy);
        ctx.closePath();
        ctx.fillStyle = slopeColor(meanSlope);
        ctx.fill();
      }

      const rings = boundaries && boundaries.length ? boundaries : [];
      if (rings.length) {
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = "#ffffff";
        ctx.shadowColor = "rgba(0,0,0,0.5)";
        ctx.shadowBlur = 2;
        for (const ring of rings) {
          if (ring.length < 2) continue;
          ctx.beginPath();
          ring.forEach((pt, i) => {
            const loc = localXY(pt.lat, pt.lon, mesh.origin.lat, mesh.origin.lon);
            const [sx, sy] = toScreen(loc.x, loc.y);
            if (i === 0) ctx.moveTo(sx, sy);
            else ctx.lineTo(sx, sy);
          });
          ctx.closePath();
          ctx.stroke();
        }
        ctx.shadowBlur = 0;
      }
    }

    draw();
    const ro = new ResizeObserver(() => draw());
    ro.observe(wrapEl);

    function onMove(e: PointerEvent) {
      const rect = cv.getBoundingClientRect();
      const cssW = rect.width;
      const cssH = rect.height;
      const pad = 8;
      const availW = cssW - pad * 2;
      const availH = cssH - pad * 2;
      const scale = Math.min(availW / dataW, availH / dataH);
      const drawW = dataW * scale;
      const drawH = dataH * scale;
      const offX = pad + (availW - drawW) / 2;
      const offY = pad + (availH - drawH) / 2;
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      const dataX = (mx - offX) / scale + xMin;
      const dataY = yMax - (my - offY) / scale;
      if (dataX < xMin || dataX > xMax || dataY < yMin || dataY > yMax) {
        setHover(null);
        return;
      }
      let bestD = Infinity;
      let bestSlope = 0;
      for (let i = 0; i < vertices.length; i += 1) {
        const dx = vertices[i][0] - dataX;
        const dy = vertices[i][1] - dataY;
        const d = dx * dx + dy * dy;
        if (d < bestD) {
          bestD = d;
          bestSlope = mesh.slopes[i] ?? 0;
        }
      }
      setHover({ x: mx, y: my, slope: bestSlope });
    }
    function onLeave() {
      setHover(null);
    }
    cv.addEventListener("pointermove", onMove);
    cv.addEventListener("pointerleave", onLeave);

    return () => {
      ro.disconnect();
      cv.removeEventListener("pointermove", onMove);
      cv.removeEventListener("pointerleave", onLeave);
    };
  }, [mesh, boundaries, height]);

  return (
    <div className="slope-top-map" ref={wrapRef}>
      <canvas ref={canvasRef} className="slope-top-canvas" />
      <div className="slope-top-north" aria-hidden="true">
        <span className="slope-top-north-arrow">↑</span>
        <span>N</span>
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
        <div
          className="slope-top-tooltip"
          style={{ left: hover.x + 12, top: hover.y + 12 }}
        >
          {hover.slope.toFixed(1)}% slope
        </div>
      ) : null}
    </div>
  );
}
