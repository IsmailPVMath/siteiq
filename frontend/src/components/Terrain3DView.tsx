import { useCallback, useEffect, useRef, useState } from "react";
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
  const [showWireframe, setShowWireframe] = useState(false);
  const [showStructure, setShowStructure] = useState(false);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const controlsRef = useRef<OrbitControls | null>(null);
  const defaultCamPosRef = useRef<THREE.Vector3 | null>(null);

  const rowCount = parseLayoutRows(layoutGeoJson ?? null, mesh.origin).length;

  const resetView = useCallback(() => {
    const cam = cameraRef.current;
    const controls = controlsRef.current;
    const defaultPos = defaultCamPosRef.current;
    if (!cam || !controls || !defaultPos) return;
    cam.position.copy(defaultPos);
    cam.lookAt(0, 0, 0);
    controls.target.set(0, 0, 0);
    controls.update();
  }, []);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const built = buildTerrain3DScene(mesh, layoutGeoJson ?? null, {
      showWireframe,
      showStructure,
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
    const defaultPos = new THREE.Vector3(maxDim * 0.62, maxDim * 0.74, maxDim * 0.95);
    camera.position.copy(defaultPos);
    camera.lookAt(0, 0, 0);
    cameraRef.current = camera;
    defaultCamPosRef.current = defaultPos.clone();

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.minPolarAngle = Math.PI / 8;
    controls.maxPolarAngle = Math.PI / 2.4;
    controls.minDistance = maxDim * 0.12;
    controls.maxDistance = maxDim * 3.8;
    controlsRef.current = controls;

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
      cameraRef.current = null;
      controlsRef.current = null;
      defaultCamPosRef.current = null;
      dispose();
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [layoutGeoJson, mesh, showWireframe, showStructure, mountType]);

  return (
    <div className="terrain-3d-wrap">
      <div className="terrain-3d-toolbar">
        <label className="terrain-wire-toggle checkbox-field">
          <input
            type="checkbox"
            checked={showWireframe}
            onChange={(e) => setShowWireframe(e.target.checked)}
          />
          Terrain mesh wireframe
        </label>
        <label className="terrain-wire-toggle checkbox-field">
          <input
            type="checkbox"
            checked={showStructure}
            onChange={(e) => setShowStructure(e.target.checked)}
          />
          Show structure
        </label>
        <button className="btn btn-ghost btn-sm" type="button" onClick={resetView}>
          Reset view
        </button>
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
          ? "3D layout preview: per-table gaps, fixed-tilt tables and posts on terrain. Toggle Show structure to see posts through semi-transparent tables. Drag to orbit, scroll to zoom — use Reset view if you lose orientation."
          : "3D layout preview: per-table gaps, tracker posts, and torque tubes on terrain. Toggle Show structure to see posts and tube through semi-transparent tables. Drag to orbit, scroll to zoom — use Reset view if you lose orientation."}
      </p>
    </div>
  );
}
