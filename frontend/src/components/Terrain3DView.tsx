import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { WorkflowTerrainMeshResponse } from "../types/workflow";
import type * as GeoJSON from "geojson";
import { MAX_3D_ROWS, buildTerrain3DScene, parseLayoutRows } from "../lib/terrain3dScene";

interface Props {
  mesh: WorkflowTerrainMeshResponse;
  layoutGeoJson?: GeoJSON.GeoJSON | null;
  projectName?: string;
  mountType?: "fixed" | "tracker";
}

export function Terrain3DView({ mesh, layoutGeoJson, mountType = "tracker" }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sunHour, setSunHour] = useState(12);
  const [showWireframe, setShowWireframe] = useState(false);

  const rowCount = parseLayoutRows(layoutGeoJson ?? null, mesh.origin).length;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const built = buildTerrain3DScene(mesh, layoutGeoJson ?? null, sunHour, {
      showWireframe,
      mountType,
    });
    const { scene, terrainSize, dispose } = built;

    const width = container.clientWidth || 900;
    const height = container.clientHeight || 480;
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.5, 8000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.08;
    container.appendChild(renderer.domElement);

    const maxDim = Math.max(terrainSize.x, terrainSize.y, terrainSize.z, 100);
    camera.position.set(maxDim * 0.62, maxDim * 0.74, maxDim * 0.95);
    camera.lookAt(0, 0, 0);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.maxPolarAngle = Math.PI / 2.05;
    controls.minDistance = maxDim * 0.12;
    controls.maxDistance = maxDim * 3.8;

    function resize() {
      if (!container) return;
      const nextWidth = container.clientWidth || width;
      const nextHeight = container.clientHeight || height;
      camera.aspect = nextWidth / nextHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(nextWidth, nextHeight);
    }
    window.addEventListener("resize", resize);

    let active = true;
    function animate() {
      if (!active) return;
      controls.update();
      renderer.render(scene, camera);
      requestAnimationFrame(animate);
    }
    animate();

    return () => {
      active = false;
      window.removeEventListener("resize", resize);
      controls.dispose();
      dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [layoutGeoJson, mesh, showWireframe, sunHour, mountType]);

  return (
    <div className="terrain-3d-wrap">
      <div className="terrain-3d-toolbar">
        <div className="terrain-sun-controls">
          <label htmlFor="terrain-sun-hour">
            Sun hour: <strong>{sunHour}:00</strong>
          </label>
          <input
            id="terrain-sun-hour"
            type="range"
            min="6"
            max="18"
            step="1"
            value={sunHour}
            onChange={(event) => setSunHour(Number(event.target.value))}
          />
        </div>
        <label className="terrain-wire-toggle checkbox-field">
          <input
            type="checkbox"
            checked={showWireframe}
            onChange={(e) => setShowWireframe(e.target.checked)}
          />
          Terrain mesh wireframe
        </label>
      </div>
      <div ref={containerRef} className="terrain-3d-view" aria-label="3D terrain view" />
      <div className="terrain-3d-meta">
        <span>{mesh.vertices.length.toLocaleString()} vertices</span>
        <span>{mesh.faces.length.toLocaleString()} triangles</span>
        <span>
          {rowCount.toLocaleString()} {mountType === "fixed" ? "fixed-tilt" : "tracker"} rows
          {rowCount >= MAX_3D_ROWS ? " (capped)" : ""}
        </span>
        <span>
          Elevation {mesh.z_min.toFixed(0)}–{mesh.z_max.toFixed(0)} m
        </span>
        <span>Mean slope {mesh.slope_mean.toFixed(1)}%</span>
        <span>{mesh.grid_m_used?.toFixed(0) ?? "—"} m mesh</span>
      </div>
      <p className="hint terrain-3d-note">
        {mountType === "fixed"
          ? "3D preview: south-tilted fixed-tilt tables on front/back legs. Drag to orbit, scroll to zoom. XYZ gizmo: red=E, green=up, blue=N."
          : "3D preview: module tables, posts, and torque tubes on terrain. Drag to orbit, scroll to zoom. XYZ gizmo: red=E, green=up, blue=N."}
      </p>
    </div>
  );
}
