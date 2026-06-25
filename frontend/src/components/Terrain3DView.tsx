import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { WorkflowTerrainMeshResponse } from "../types/workflow";
import type * as GeoJSON from "geojson";

interface Props {
  mesh: WorkflowTerrainMeshResponse;
  layoutGeoJson?: GeoJSON.GeoJSON | null;
}

function slopeColor(slope: number) {
  if (slope <= 3) return new THREE.Color("#22c55e");
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
  const dayOfYear = 172; // summer-solstice reference for first visual layer
  const decl = (23.44 * Math.PI) / 180 * Math.sin(((360 / 365) * (dayOfYear - 81) * Math.PI) / 180);
  const hourAngle = ((hour - 12) * 15 * Math.PI) / 180;
  const altitude = Math.asin(
    Math.sin(lat) * Math.sin(decl) + Math.cos(lat) * Math.cos(decl) * Math.cos(hourAngle),
  );
  const east = Math.sin(hourAngle);
  const north = Math.cos(hourAngle) * Math.sin(lat) - Math.tan(decl) * Math.cos(lat);
  const azimuth = Math.atan2(east, north);
  return { altitude, azimuth };
}

function pvRowFeatures(layoutGeoJson?: GeoJSON.GeoJSON | null) {
  if (!layoutGeoJson || layoutGeoJson.type !== "FeatureCollection") return [];
  return layoutGeoJson.features.filter(
    (feature) => feature.geometry?.type === "Polygon" && feature.properties?.kind === "pv_row",
  ) as Array<GeoJSON.Feature<GeoJSON.Polygon>>;
}

export function Terrain3DView({ mesh, layoutGeoJson }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [sunHour, setSunHour] = useState(12);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const scene = new THREE.Scene();
    scene.background = new THREE.Color("#f8fafc");
    const width = container.clientWidth || 900;
    const height = container.clientHeight || 480;
    const camera = new THREE.PerspectiveCamera(45, width / height, 0.1, 10000);
    const renderer = new THREE.WebGLRenderer({ antialias: true });
    renderer.setPixelRatio(window.devicePixelRatio);
    renderer.setSize(width, height);
    container.appendChild(renderer.domElement);

    const positions: number[] = [];
    const colors: number[] = [];
    mesh.vertices.forEach(([x, y, z], idx) => {
      positions.push(x, z * 3, -y);
      const color = slopeColor(mesh.slopes[idx] ?? 0);
      colors.push(color.r, color.g, color.b);
    });

    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geometry.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geometry.setIndex(mesh.faces.flat());
    geometry.computeVertexNormals();

    const material = new THREE.MeshLambertMaterial({
      vertexColors: true,
      side: THREE.DoubleSide,
      flatShading: false,
    });
    const terrain = new THREE.Mesh(geometry, material);
    scene.add(terrain);

    const wire = new THREE.LineSegments(
      new THREE.WireframeGeometry(geometry),
      new THREE.LineBasicMaterial({ color: "#334155", transparent: true, opacity: 0.12 }),
    );
    scene.add(wire);

    const box = new THREE.Box3().setFromObject(terrain);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    terrain.position.sub(center);
    wire.position.sub(center);

    scene.add(new THREE.AmbientLight("#ffffff", 0.64));
    const sun = new THREE.DirectionalLight("#ffffff", 1.1);
    const sunViz = sunPosition(mesh.origin.lat, sunHour);
    const sunRadius = Math.max(size.x, size.z, 180) * 0.75;
    const sunX = Math.sin(sunViz.azimuth) * Math.cos(sunViz.altitude) * sunRadius;
    const sunY = Math.max(Math.sin(sunViz.altitude) * sunRadius, 20);
    const sunZ = -Math.cos(sunViz.azimuth) * Math.cos(sunViz.altitude) * sunRadius;
    sun.position.set(sunX, sunY, sunZ);
    scene.add(sun);
    const sunMarker = new THREE.Mesh(
      new THREE.SphereGeometry(Math.max(size.x, size.z, 100) * 0.025, 24, 16),
      new THREE.MeshBasicMaterial({ color: "#facc15" }),
    );
    sunMarker.position.copy(sun.position);
    scene.add(sunMarker);

    const rowGroup = new THREE.Group();
    const rowMaterial = new THREE.MeshLambertMaterial({
      color: "#0f766e",
      emissive: "#042f2e",
      emissiveIntensity: 0.08,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: 0.92,
    });

    function nearestTerrainDisplayY(x: number, north: number) {
      let bestD = Number.POSITIVE_INFINITY;
      let bestZ = 0;
      for (const [vx, vy, vz] of mesh.vertices) {
        const dist = (x - vx) ** 2 + (north - vy) ** 2;
        if (dist < bestD) {
          bestD = dist;
          bestZ = vz;
        }
      }
      return bestZ * 3 - center.y + 1.4;
    }

    pvRowFeatures(layoutGeoJson).forEach((feature) => {
      const ring = feature.geometry.coordinates[0];
      if (!ring || ring.length < 4) return;
      const localRing = ring.slice(0, -1).map(([lon, lat]) => localXY(lon, lat, mesh.origin));
      const cx = localRing.reduce((sum, point) => sum + point.x, 0) / localRing.length;
      const cy = localRing.reduce((sum, point) => sum + point.y, 0) / localRing.length;
      const rowY = nearestTerrainDisplayY(cx, cy);
      const rowPositions: number[] = [];
      localRing.forEach((point) => {
        rowPositions.push(point.x - center.x, rowY, -point.y - center.z);
      });
      const rowIndices: number[] = [];
      for (let idx = 1; idx < localRing.length - 1; idx += 1) {
        rowIndices.push(0, idx, idx + 1);
      }
      const rowGeometry = new THREE.BufferGeometry();
      rowGeometry.setAttribute("position", new THREE.Float32BufferAttribute(rowPositions, 3));
      rowGeometry.setIndex(rowIndices);
      rowGeometry.computeVertexNormals();
      rowGroup.add(new THREE.Mesh(rowGeometry, rowMaterial));
    });
    scene.add(rowGroup);

    const axes = new THREE.AxesHelper(Math.max(size.x, size.z, 100) * 0.25);
    scene.add(axes);

    const maxDim = Math.max(size.x, size.y, size.z, 100);
    camera.position.set(maxDim * 0.55, maxDim * 0.65, maxDim * 0.9);
    camera.lookAt(0, 0, 0);
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;

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
      rowGroup.traverse((obj) => {
        if (obj instanceof THREE.Mesh) obj.geometry.dispose();
      });
      rowMaterial.dispose();
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
        <span>{mesh.faces.length.toLocaleString()} faces</span>
        <span>{pvRowFeatures(layoutGeoJson).length.toLocaleString()} draped PV rows</span>
        <span>
          Elevation {mesh.z_min.toFixed(0)}-{mesh.z_max.toFixed(0)} m
        </span>
        <span>Mean slope {mesh.slope_mean.toFixed(1)}%</span>
      </div>
    </div>
  );
}
