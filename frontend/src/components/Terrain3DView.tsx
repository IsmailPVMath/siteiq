import { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { WorkflowTerrainMeshResponse } from "../types/workflow";

interface Props {
  mesh: WorkflowTerrainMeshResponse;
}

function slopeColor(slope: number) {
  if (slope <= 3) return new THREE.Color("#22c55e");
  if (slope <= 6) return new THREE.Color("#84cc16");
  if (slope <= 10) return new THREE.Color("#f59e0b");
  return new THREE.Color("#ef4444");
}

export function Terrain3DView({ mesh }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

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

    scene.add(new THREE.AmbientLight("#ffffff", 0.72));
    const sun = new THREE.DirectionalLight("#ffffff", 1.1);
    sun.position.set(size.x || 200, Math.max(size.y, 80) * 2, size.z || 200);
    scene.add(sun);

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
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [mesh]);

  return (
    <div className="terrain-3d-wrap">
      <div ref={containerRef} className="terrain-3d-view" aria-label="3D terrain view" />
      <div className="terrain-3d-meta">
        <span>{mesh.vertices.length.toLocaleString()} vertices</span>
        <span>{mesh.faces.length.toLocaleString()} faces</span>
        <span>
          Elevation {mesh.z_min.toFixed(0)}-{mesh.z_max.toFixed(0)} m
        </span>
        <span>Mean slope {mesh.slope_mean.toFixed(1)}%</span>
      </div>
    </div>
  );
}
