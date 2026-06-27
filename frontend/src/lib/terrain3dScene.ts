import * as THREE from "three";
import { GLTFExporter } from "three/examples/jsm/exporters/GLTFExporter.js";
import type { WorkflowTerrainMeshResponse } from "../types/workflow";
import type * as GeoJSON from "geojson";

export const Z_SCALE = 2.8;
export const MAX_3D_ROWS = 800;
export const POST_SPACING_M = 8;
export const TABLE_THICKNESS_M = 0.06;
export const TABLE_CLEARANCE_M = 1.85;
export const TUBE_RADIUS_M = 0.055;

export function slopeColor(slope: number) {
  if (slope <= 3) return new THREE.Color("#2d8a47");
  if (slope <= 6) return new THREE.Color("#6aaf3a");
  if (slope <= 10) return new THREE.Color("#d97706");
  return new THREE.Color("#dc2626");
}

export function localXY(lon: number, lat: number, origin: { lat: number; lon: number }) {
  const mPerDegLat = 111_320;
  const mPerDegLon = 111_320 * Math.cos((origin.lat * Math.PI) / 180);
  return {
    x: (lon - origin.lon) * mPerDegLon,
    y: (lat - origin.lat) * mPerDegLat,
  };
}

export function toThreePosition(
  lx: number,
  north: number,
  groundElevM: number,
  realOffsetM: number,
  center: THREE.Vector3,
): THREE.Vector3 {
  return new THREE.Vector3(
    lx - center.x,
    groundElevM * Z_SCALE + realOffsetM - center.y,
    -north - center.z,
  );
}

export function buildElevationSampler(mesh: WorkflowTerrainMeshResponse, cellSize = 6): ElevationSampler {
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
      return z00 * (1 - tx) * (1 - ty) + z10 * tx * (1 - ty) + z01 * (1 - tx) * ty + z11 * tx * ty;
    }
    return samples.reduce((a, b) => a + b, 0) / samples.length;
  };
}

export interface OrientedRow {
  cx: number;
  cy: number;
  length: number;
  width: number;
  angle: number;
  nModules: number;
}

function orientedRowFromRing(
  ring: number[][],
  origin: { lat: number; lon: number },
  props?: { length_m?: number; n_modules?: number },
): OrientedRow | null {
  const pts = ring.slice(0, -1).map(([lon, lat]) => localXY(lon, lat, origin));
  if (pts.length < 3) return null;

  let bestLen = 0;
  let angle = 0;
  for (let i = 0; i < pts.length; i += 1) {
    const j = (i + 1) % pts.length;
    const dx = pts[j].x - pts[i].x;
    const dy = pts[j].y - pts[i].y;
    const len = Math.hypot(dx, dy);
    if (len > bestLen) {
      bestLen = len;
      angle = Math.atan2(dy, dx);
    }
  }

  const cos = Math.cos(-angle);
  const sin = Math.sin(-angle);
  let minRx = Infinity;
  let maxRx = -Infinity;
  let minRy = Infinity;
  let maxRy = -Infinity;
  for (const p of pts) {
    const rx = p.x * cos - p.y * sin;
    const ry = p.x * sin + p.y * cos;
    minRx = Math.min(minRx, rx);
    maxRx = Math.max(maxRx, rx);
    minRy = Math.min(minRy, ry);
    maxRy = Math.max(maxRy, ry);
  }

  const geomLength = Math.max(0.8, maxRx - minRx);
  const geomWidth = Math.max(0.4, maxRy - minRy);
  const length = props?.length_m && props.length_m > 0 ? props.length_m : geomLength;
  const width = geomWidth;
  const rcx = (minRx + maxRx) / 2;
  const rcy = (minRy + maxRy) / 2;
  const cx = rcx * Math.cos(angle) - rcy * Math.sin(angle);
  const cy = rcx * Math.sin(angle) + rcy * Math.cos(angle);

  const nModules =
    props?.n_modules && props.n_modules > 0
      ? props.n_modules
      : Math.max(4, Math.round(length / 1.038));

  return { cx, cy, length, width, angle, nModules };
}

export function parseLayoutRows(
  layoutGeoJson: GeoJSON.GeoJSON | null | undefined,
  origin: { lat: number; lon: number },
): OrientedRow[] {
  if (!layoutGeoJson || layoutGeoJson.type !== "FeatureCollection") return [];
  const rows: OrientedRow[] = [];

  let features = layoutGeoJson.features.filter(
    (f) => f.geometry?.type === "Polygon" && f.properties?.kind === "pv_row",
  ) as Array<GeoJSON.Feature<GeoJSON.Polygon>>;

  // Do not fall back to per-string polygons — clipped fragments collapse the 3D view.
  for (const feature of features.slice(0, MAX_3D_ROWS)) {
    const ring = feature.geometry.coordinates[0];
    if (!ring || ring.length < 4) continue;
    const lengthM = Number(feature.properties?.length_m ?? 0);
    const nMod = Number(feature.properties?.n_modules ?? 0);
    const row = orientedRowFromRing(ring, origin, {
      length_m: Number.isFinite(lengthM) ? lengthM : undefined,
      n_modules: Number.isFinite(nMod) ? nMod : undefined,
    });
    if (!row) continue;
    if (row.length < 3) continue;
    rows.push(row);
  }
  return rows;
}

function createModuleTableTexture(moduleCols: number): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.fillStyle = "#1d4ed8";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = "#60a5fa";
    ctx.lineWidth = 1;
    const cols = Math.min(Math.max(moduleCols, 4), 40);
    for (let i = 1; i < cols; i += 1) {
      const x = (i / cols) * canvas.width;
      ctx.beginPath();
      ctx.moveTo(x, 0);
      ctx.lineTo(x, canvas.height);
      ctx.stroke();
    }
  }
  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.ClampToEdgeWrapping;
  tex.repeat.set(Math.max(1, moduleCols / 8), 1);
  return tex;
}

export type ElevationSampler = (x: number, y: number) => number;

export interface Terrain3DScene {
  scene: THREE.Scene;
  terrain: THREE.Mesh;
  terrainCenter: THREE.Vector3;
  terrainSize: THREE.Vector3;
  rowCount: number;
  postCount: number;
  dispose: () => void;
}

export type MountKind = "fixed" | "tracker";

export function buildTerrain3DScene(
  mesh: WorkflowTerrainMeshResponse,
  layoutGeoJson: GeoJSON.GeoJSON | null | undefined,
  options?: { showWireframe?: boolean; mountType?: MountKind },
): Terrain3DScene {
  const mountType: MountKind = options?.mountType ?? "tracker";
  const FIXED_TILT_DEG = 22;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#c8e6c9");
  const fogFar = Math.max(1200, Math.max(mesh.vertices.length > 0 ? 800 : 1200, 1));
  scene.fog = new THREE.Fog("#c8e6c9", fogFar * 0.35, fogFar * 2.4);

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

  const terrainMat = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.88,
    metalness: 0.02,
    side: THREE.DoubleSide,
  });
  const terrain = new THREE.Mesh(geometry, terrainMat);
  terrain.receiveShadow = true;
  scene.add(terrain);

  if (options?.showWireframe) {
    const wire = new THREE.LineSegments(
      new THREE.WireframeGeometry(geometry),
      new THREE.LineBasicMaterial({ color: "#166534", transparent: true, opacity: 0.22 }),
    );
    terrain.add(wire);
  }

  const box = new THREE.Box3().setFromObject(terrain);
  const terrainCenter = box.getCenter(new THREE.Vector3());
  const terrainSize = box.getSize(new THREE.Vector3());
  terrain.position.sub(terrainCenter);

  const sampler = buildElevationSampler(mesh);
  scene.add(new THREE.HemisphereLight("#dbeafe", "#3f6212", 0.5));
  scene.add(new THREE.AmbientLight("#ffffff", 0.22));

  const sun = new THREE.DirectionalLight("#fff4d6", 1.4);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.near = 1;
  sun.shadow.camera.far = Math.max(terrainSize.x, terrainSize.z, 200) * 5;
  const shadowSpan = Math.max(terrainSize.x, terrainSize.z, 120) * 0.8;
  sun.shadow.camera.left = -shadowSpan;
  sun.shadow.camera.right = shadowSpan;
  sun.shadow.camera.top = shadowSpan;
  sun.shadow.camera.bottom = -shadowSpan;
  sun.shadow.bias = -0.0006;
  scene.add(sun);

  const sunAzimuth = (135 * Math.PI) / 180;
  const sunAltitude = (50 * Math.PI) / 180;
  const sunRadius = Math.max(terrainSize.x, terrainSize.z, 180) * 0.9;
  sun.position.set(
    Math.sin(sunAzimuth) * Math.cos(sunAltitude) * sunRadius,
    Math.max(Math.sin(sunAltitude) * sunRadius, 40),
    -Math.cos(sunAzimuth) * Math.cos(sunAltitude) * sunRadius,
  );
  sun.target.position.set(0, 0, 0);
  scene.add(sun.target);

  const tableMat = new THREE.MeshStandardMaterial({
    color: "#2563eb",
    roughness: 0.28,
    metalness: 0.35,
    side: THREE.DoubleSide,
  });
  const postMat = new THREE.MeshStandardMaterial({
    color: "#94a3b8",
    roughness: 0.55,
    metalness: 0.45,
  });
  const tubeMat = new THREE.MeshStandardMaterial({
    color: "#475569",
    roughness: 0.4,
    metalness: 0.55,
  });

  const rows = parseLayoutRows(layoutGeoJson ?? null, mesh.origin);
  let postCount = 0;

  const pvGroup = new THREE.Group();
  pvGroup.name = "PV_Layout";

  for (const row of rows) {
    const tableTex = createModuleTableTexture(row.nModules);
    const rowTableMat = tableMat.clone();
    rowTableMat.map = tableTex;

    const nPosts = Math.max(2, Math.floor(row.length / POST_SPACING_M) + 1);
    const postXs: number[] = [];
    for (let i = 0; i < nPosts; i += 1) {
      const t = nPosts === 1 ? 0.5 : i / (nPosts - 1);
      postXs.push(-row.length / 2 + t * row.length);
    }

    const cos = Math.cos(row.angle);
    const sin = Math.sin(row.angle);

    if (mountType === "fixed") {
      // Fixed tilt: tables tilted toward the sun on front (short) + back (tall) legs.
      const tiltRad = (FIXED_TILT_DEG * Math.PI) / 180;
      const backExtra = Math.sin(tiltRad) * row.width;
      const frontH = TABLE_CLEARANCE_M * 0.55;
      const backH = frontH + backExtra;
      // legs are offset along the row's transverse (width) axis
      const tcos = Math.cos(row.angle + Math.PI / 2);
      const tsin = Math.sin(row.angle + Math.PI / 2);
      const halfW = row.width / 2;

      const tableTops: THREE.Vector3[] = [];
      for (const px of postXs) {
        const baseLx = row.cx + px * cos;
        const baseNorth = row.cy + px * sin;
        for (const [off, h] of [
          [-halfW, frontH],
          [halfW, backH],
        ] as const) {
          const lx = baseLx + off * tcos;
          const north = baseNorth + off * tsin;
          const postGeo = new THREE.CylinderGeometry(0.06, 0.08, h, 8);
          const post = new THREE.Mesh(postGeo, postMat);
          post.castShadow = true;
          post.receiveShadow = true;
          post.position.copy(toThreePosition(lx, north, sampler(lx, north), h / 2, terrainCenter));
          pvGroup.add(post);
          postCount += 1;
        }
        // table-top centre reference for this support
        const groundZ = sampler(baseLx, baseNorth);
        tableTops.push(
          toThreePosition(baseLx, baseNorth, groundZ, (frontH + backH) / 2, terrainCenter),
        );
      }

      const avgTop =
        tableTops.reduce((acc, v) => acc.add(v), new THREE.Vector3()).multiplyScalar(1 / tableTops.length);
      const tableGeo = new THREE.BoxGeometry(row.length, TABLE_THICKNESS_M, row.width);
      const table = new THREE.Mesh(tableGeo, rowTableMat);
      table.castShadow = true;
      table.receiveShadow = false;
      table.position.copy(avgTop);
      table.rotation.y = -row.angle;
      table.rotateX(-tiltRad);
      pvGroup.add(table);
      continue;
    }

    const postTops: THREE.Vector3[] = [];
    for (const px of postXs) {
      const lx = row.cx + px * cos;
      const north = row.cy + px * sin;
      const postH = TABLE_CLEARANCE_M;
      const postGeo = new THREE.CylinderGeometry(0.07, 0.09, postH, 10);
      const post = new THREE.Mesh(postGeo, postMat);
      post.castShadow = true;
      post.receiveShadow = true;
      const pos = toThreePosition(lx, north, sampler(lx, north), postH / 2, terrainCenter);
      post.position.copy(pos);
      pvGroup.add(post);
      postCount += 1;

      postTops.push(toThreePosition(lx, north, sampler(lx, north), TABLE_CLEARANCE_M, terrainCenter));
    }

    if (postTops.length >= 2) {
      const start = postTops[0];
      const end = postTops[postTops.length - 1];
      const tubeLen = start.distanceTo(end);
      const tubeGeo = new THREE.CylinderGeometry(TUBE_RADIUS_M, TUBE_RADIUS_M, tubeLen, 10);
      const tube = new THREE.Mesh(tubeGeo, tubeMat);
      tube.castShadow = true;
      const mid = start.clone().add(end).multiplyScalar(0.5);
      tube.position.copy(mid);
      tube.lookAt(end);
      tube.rotateX(Math.PI / 2);
      pvGroup.add(tube);
    }

    const avgTop =
      postTops.reduce((acc, v) => acc.add(v), new THREE.Vector3()).multiplyScalar(1 / postTops.length);
    const tableGeo = new THREE.BoxGeometry(row.length, TABLE_THICKNESS_M, row.width);
    const table = new THREE.Mesh(tableGeo, rowTableMat);
    table.castShadow = true;
    table.receiveShadow = false;
    table.position.copy(avgTop);
    table.position.y += TABLE_THICKNESS_M / 2;
    table.rotation.y = -row.angle;
    pvGroup.add(table);
  }

  scene.add(pvGroup);

  // XYZ orientation gizmo (red=E/X, green=up/Y, blue=N/Z) in a corner of the site.
  const axisLen = Math.max(terrainSize.x, terrainSize.z) * 0.08;
  const axes = new THREE.AxesHelper(axisLen);
  axes.position.set(-terrainSize.x * 0.46, terrainSize.y * 0.1, terrainSize.z * 0.46);
  scene.add(axes);

  const northArrow = new THREE.ArrowHelper(
    new THREE.Vector3(0, 0, -1),
    new THREE.Vector3(-terrainSize.x * 0.42, terrainSize.y * 0.12, terrainSize.z * 0.38),
    Math.max(terrainSize.x, terrainSize.z) * 0.1,
    0x1d4ed8,
    Math.max(terrainSize.x, terrainSize.z) * 0.028,
    Math.max(terrainSize.x, terrainSize.z) * 0.018,
  );
  scene.add(northArrow);

  const disposables: Array<() => void> = [
    () => geometry.dispose(),
    () => terrainMat.dispose(),
    () => tableMat.dispose(),
    () => postMat.dispose(),
    () => tubeMat.dispose(),
  ];

  return {
    scene,
    terrain,
    terrainCenter,
    terrainSize,
    rowCount: rows.length,
    postCount,
    dispose: () => {
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) {
          obj.geometry.dispose();
          const mats = Array.isArray(obj.material) ? obj.material : [obj.material];
          mats.forEach((m) => {
            if (m.map) m.map.dispose();
            m.dispose();
          });
        }
      });
      disposables.forEach((fn) => fn());
    },
  };
}

export function exportSceneGlb(scene: THREE.Scene): Promise<Blob> {
  const exporter = new GLTFExporter();
  return new Promise((resolve, reject) => {
    exporter.parse(
      scene,
      (result) => {
        if (result instanceof ArrayBuffer) {
          resolve(new Blob([result], { type: "model/gltf-binary" }));
          return;
        }
        resolve(new Blob([JSON.stringify(result)], { type: "model/gltf+json" }));
      },
      (err) => reject(err instanceof Error ? err : new Error(String(err))),
      { binary: true },
    );
  });
}
