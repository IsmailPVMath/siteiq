import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { WorkflowTerrainMeshResponse } from "../types/workflow";
import type * as GeoJSON from "geojson";

interface Props {
  mesh: WorkflowTerrainMeshResponse;
  layoutGeoJson?: GeoJSON.GeoJSON | null;
}

const Z_SCALE = 2.8;
const MAX_3D_MODULES = 2500;

function slopeColor(slope: number) {
  if (slope <= 3) return new THREE.Color("#1d9e52");
  if (slope <= 6) return new THREE.Color("#84cc16");
  if (slope <= 10) return new THREE.Color("#f59e0b");
  return new THREE.Color("#ef4444");
}

function localXY(lon: number, lat: number, origin: { lat: number; lon: number }) {
  const mPerDegLat = 111_320;
  const mPerDegLon = 111_320 * Math.cos((origin.lat * Math.PI) / 180);
  return {
    x: (lon - origin.lon) * mPerDegLon,
    y: (lat - origin.lat) * mPerDegLat,
  };
}

function sunPosition(latDeg: number, hour: number) {
  const lat = (latDeg * Math.PI) / 180;
  const dayOfYear = 172;
  const decl = ((23.44 * Math.PI) / 180) * Math.sin((((360 / 365) * (dayOfYear - 81) * Math.PI) / 180));
  const hourAngle = ((hour - 12) * 15 * Math.PI) / 180;
  const altitude = Math.asin(
    Math.sin(lat) * Math.sin(decl) + Math.cos(lat) * Math.cos(decl) * Math.cos(hourAngle),
  );
  const east = Math.sin(hourAngle);
  const north = Math.cos(hourAngle) * Math.sin(lat) - Math.tan(decl) * Math.cos(lat);
  const azimuth = Math.atan2(east, north);
  return { altitude, azimuth };
}

function pvModuleFeatures(layoutGeoJson?: GeoJSON.GeoJSON | null) {
  if (!layoutGeoJson || layoutGeoJson.type !== "FeatureCollection") return [];
  const modules = layoutGeoJson.features.filter(
    (feature) =>
      feature.geometry?.type === "Polygon" && feature.properties?.kind === "pv_module",
  ) as Array<GeoJSON.Feature<GeoJSON.Polygon>>;
  if (modules.length) return modules.slice(0, MAX_3D_MODULES);
  return layoutGeoJson.features
    .filter(
      (feature) => feature.geometry?.type === "Polygon" && feature.properties?.kind === "pv_row",
    )
    .slice(0, MAX_3D_MODULES) as Array<GeoJSON.Feature<GeoJSON.Polygon>>;
}

type ElevationSampler = (x: number, y: number) => number;

function buildElevationSampler(
  mesh: WorkflowTerrainMeshResponse,
  cellSize = 8,
): ElevationSampler {
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;
  for (const [x, y] of mesh.vertices) {
    minX = Math.min(minX, x);
    maxX = Math.max(maxX, x);
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  const nx = Math.max(2, Math.ceil((maxX - minX) / cellSize));
  const ny = Math.max(2, Math.ceil((maxY - minY) / cellSize));
  const grid = new Float32Array(nx * ny).fill(NaN);
  const counts = new Uint16Array(nx * ny);

  for (const [x, y, z] of mesh.vertices) {
    const ix = Math.min(nx - 1, Math.max(0, Math.floor((x - minX) / cellSize)));
    const iy = Math.min(ny - 1, Math.max(0, Math.floor((y - minY) / cellSize)));
    const idx = iy * nx + ix;
    grid[idx] = Number.isNaN(grid[idx]) ? z : grid[idx] + z;
    counts[idx] += 1;
  }
  for (let i = 0; i < grid.length; i += 1) {
    if (counts[i] > 0) grid[i] /= counts[i];
  }

  return (x: number, y: number) => {
    const fx = (x - minX) / cellSize;
    const fy = (y - minY) / cellSize;
    const x0 = Math.min(nx - 1, Math.max(0, Math.floor(fx)));
    const y0 = Math.min(ny - 1, Math.max(0, Math.floor(fy)));
    const x1 = Math.min(nx - 1, x0 + 1);
    const y1 = Math.min(ny - 1, y0 + 1);
    const tx = fx - x0;
    const ty = fy - y0;
    const z00 = grid[y0 * nx + x0];
    const z10 = grid[y0 * nx + x1];
    const z01 = grid[y1 * nx + x0];
    const z11 = grid[y1 * nx + x1];
    const samples = [z00, z10, z01, z11].filter((v) => !Number.isNaN(v));
    if (!samples.length) return 0;
    if (samples.length === 4) {
      return (
        z00 * (1 - tx) * (1 - ty) +
        z10 * tx * (1 - ty) +
        z01 * (1 - tx) * ty +
        z11 * tx * ty
      );
    }
    return samples.reduce((a, b) => a + b, 0) / samples.length;
  };
}

function polygonLocalBounds(ring: number[][], origin: { lat: number; lon: number }) {
  const pts = ring.slice(0, -1).map(([lon, lat]) => localXY(lon, lat, origin));
  const xs = pts.map((p) => p.x);
  const ys = pts.map((p) => p.y);
  return {
    minX: Math.min(...xs),
    maxX: Math.max(...xs),
    minY: Math.min(...ys),
    maxY: Math.max(...ys),
    cx: (Math.min(...xs) + Math.max(...xs)) / 2,
    cy: (Math.min(...ys) + Math.max(...ys)) / 2,
    width: Math.max(0.5, Math.max(...xs) - Math.min(...xs)),
    depth: Math.max(0.5, Math.max(...ys) - Math.min(...ys)),
  };
}

export function Terrain3DView({ mesh, layoutGeoJson }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sunHour, setSunHour] = useState(12);

  const moduleCount = pvModuleFeatures(layoutGeoJson).length;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#e8eef2");
    scene.fog = new THREE.Fog("#e8eef2", 400, 2800);

    const width = container.clientWidth || 900;
    const height = container.clientHeight || 480;
    const camera = new THREE.PerspectiveCamera(42, width / height, 0.5, 8000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: "high-performance" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.setSize(width, height);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    container.appendChild(renderer.domElement);

    const positions: number[] = [];
    const colors: number[] = [];
    mesh.vertices.forEach(([x, y, z], idx) => {
      positions.push(x, z * Z_SCALE, -y);
      const color = slopeColor(mesh.slopes[idx] ?? 0);
      colors.push(color.r, color.g, color.b);
    });

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geometry.setIndex(mesh.faces.flat());
    geometry.computeVertexNormals();

    const material = new THREE.MeshStandardMaterial({
      vertexColors: true,
      roughness: 0.82,
      metalness: 0.04,
      flatShading: false,
      side: THREE.DoubleSide,
    });
    const terrain = new THREE.Mesh(geometry, material);
    terrain.castShadow = false;
    terrain.receiveShadow = true;
    scene.add(terrain);

    const box = new THREE.Box3().setFromObject(terrain);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    terrain.position.sub(center);

    const sampler = buildElevationSampler(mesh);
    const displayElevation = (x: number, north: number) =>
      sampler(x, north) * Z_SCALE - center.y + 1.6;

    scene.add(new THREE.HemisphereLight("#dbeafe", "#3f6212", 0.45));
    const ambient = new THREE.AmbientLight("#ffffff", 0.28);
    scene.add(ambient);

    const sun = new THREE.DirectionalLight("#fff7e6", 1.35);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = Math.max(size.x, size.z, 200) * 4;
    const shadowSpan = Math.max(size.x, size.z, 120) * 0.75;
    sun.shadow.camera.left = -shadowSpan;
    sun.shadow.camera.right = shadowSpan;
    sun.shadow.camera.top = shadowSpan;
    sun.shadow.camera.bottom = -shadowSpan;
    sun.shadow.bias = -0.0008;
    scene.add(sun);

    const sunViz = sunPosition(mesh.origin.lat, sunHour);
    const sunRadius = Math.max(size.x, size.z, 180) * 0.85;
    const sunX = Math.sin(sunViz.azimuth) * Math.cos(sunViz.altitude) * sunRadius;
    const sunY = Math.max(Math.sin(sunViz.altitude) * sunRadius, 35);
    const sunZ = -Math.cos(sunViz.azimuth) * Math.cos(sunViz.altitude) * sunRadius;
    sun.position.set(sunX, sunY, sunZ);
    sun.target.position.set(0, 0, 0);
    scene.add(sun.target);

    const pvFeatures = pvModuleFeatures(layoutGeoJson);
    const pvGroup = new THREE.Group();
    const moduleMat = new THREE.MeshStandardMaterial({
      color: "#2563eb",
      emissive: "#1e3a8a",
      emissiveIntensity: 0.12,
      roughness: 0.35,
      metalness: 0.25,
    });

    if (pvFeatures.length > 0) {
      const unitGeo = new THREE.BoxGeometry(1, 1, 1);
      const instanced = new THREE.InstancedMesh(unitGeo, moduleMat, pvFeatures.length);
      instanced.castShadow = true;
      instanced.receiveShadow = false;
      const matrix = new THREE.Matrix4();
      const quat = new THREE.Quaternion();
      const scale = new THREE.Vector3();
      const pos = new THREE.Vector3();

      pvFeatures.forEach((feature, idx) => {
        const ring = feature.geometry.coordinates[0];
        if (!ring || ring.length < 4) return;
        const bounds = polygonLocalBounds(ring, mesh.origin);
        const elev = displayElevation(bounds.cx, bounds.cy);
        const thickness = 0.35;
        pos.set(bounds.cx - center.x, elev + thickness * 0.5, -(bounds.cy - center.z));
        scale.set(bounds.width, thickness, bounds.depth);
        matrix.compose(pos, quat, scale);
        instanced.setMatrixAt(idx, matrix);
      });
      instanced.instanceMatrix.needsUpdate = true;
      pvGroup.add(instanced);
    }
    scene.add(pvGroup);

    const northArrow = new THREE.ArrowHelper(
      new THREE.Vector3(0, 0, -1),
      new THREE.Vector3(-size.x * 0.42, size.y * 0.15, size.z * 0.38),
      Math.max(size.x, size.z) * 0.12,
      0x1d4ed8,
      Math.max(size.x, size.z) * 0.03,
      Math.max(size.x, size.z) * 0.02,
    );
    scene.add(northArrow);

    const maxDim = Math.max(size.x, size.y, size.z, 100);
    camera.position.set(maxDim * 0.62, maxDim * 0.72, maxDim * 0.95);
    camera.lookAt(0, 0, 0);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.07;
    controls.maxPolarAngle = Math.PI / 2.05;
    controls.minDistance = maxDim * 0.15;
    controls.maxDistance = maxDim * 3.5;

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
      geometry.dispose();
      material.dispose();
      moduleMat.dispose();
      pvGroup.traverse((obj) => {
        if (obj instanceof THREE.Mesh) obj.geometry.dispose();
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [layoutGeoJson, mesh, sunHour]);

  return (
    <div className="terrain-3d-wrap">
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
      <div ref={containerRef} className="terrain-3d-view" aria-label="3D terrain view" />
      <div className="terrain-3d-meta">
        <span>{mesh.vertices.length.toLocaleString()} vertices</span>
        <span>{mesh.faces.length.toLocaleString()} triangles</span>
        <span>
          {moduleCount.toLocaleString()} PV strings
          {moduleCount >= MAX_3D_MODULES ? " (capped)" : ""}
        </span>
        <span>
          Elevation {mesh.z_min.toFixed(0)}–{mesh.z_max.toFixed(0)} m
        </span>
        <span>Mean slope {mesh.slope_mean.toFixed(1)}%</span>
        <span>{mesh.grid_m_used?.toFixed(0) ?? "—"} m mesh</span>
      </div>
      <p className="hint terrain-3d-note">
        3D view drapes PV strings on the TopoIQ DEM with directional sun shadows. Screening-grade
        only — not a substitute for detailed shading simulation.
      </p>
    </div>
  );
}
