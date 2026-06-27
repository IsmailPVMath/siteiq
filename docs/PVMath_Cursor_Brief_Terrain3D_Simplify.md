# Cursor Brief — Simplify Terrain 3D View (remove sun control, fix pole positioning)

**Requested by:** Mohammed Ismail Pasha, 2026-06-27
**Goal:** Strip the sun-hour control out of the 3D terrain/layout viewer entirely and replace it with fixed, neutral lighting. For this preliminary stage, the view has one job: show the 3D layout (rows, posts/poles, terrain) clearly and accurately — no time-of-day complexity.

**Files touched:**
- `frontend/src/components/Terrain3DView.tsx`
- `frontend/src/lib/terrain3dScene.ts`

---

## 1. Remove the sun-hour slider and state (`Terrain3DView.tsx`)

- Delete `const [sunHour, setSunHour] = useState(12);` (line 17).
- Delete the `<div className="terrain-sun-controls">...</div>` block (lines 86–99) from the toolbar JSX.
- Remove `sunHour` from the `buildTerrain3DScene(...)` call (line 26) and from the `useEffect` dependency array (line 81).

## 2. Replace dynamic sun position with a fixed light (`terrain3dScene.ts`)

- Delete the `sunPosition()` function (lines 29–41) — no longer needed.
- Remove the `sunHour: number` parameter from `buildTerrain3DScene`'s signature (line 224).
- Replace the dynamic `sunViz = sunPosition(...)` block (lines 287–293) with a fixed light position:

```ts
const sunAzimuth = (135 * Math.PI) / 180; // fixed pleasant 3/4 angle — not geographically accurate, not meant to be
const sunAltitude = (50 * Math.PI) / 180;
const sunRadius = Math.max(terrainSize.x, terrainSize.z, 180) * 0.9;
sun.position.set(
  Math.sin(sunAzimuth) * Math.cos(sunAltitude) * sunRadius,
  Math.max(Math.sin(sunAltitude) * sunRadius, 40),
  -Math.cos(sunAzimuth) * Math.cos(sunAltitude) * sunRadius,
);
```

- Keep `HemisphereLight` and `AmbientLight` as-is — they were never sun-hour dependent.

## 3. Fix the pole/post vertical-position bug (`terrain3dScene.ts`)

This matters directly for the stated goal — the whole point of this view is showing accurate pole positions on terrain.

`toThreePosition()` (lines 200–207) multiplies its entire `elevM` argument by `Z_SCALE` (2.8). Every call site passes `groundElevation + offset` as that single combined argument (e.g. lines 360, 393, 398) — so physical offsets like `TABLE_CLEARANCE_M` (1.85 m) get exaggerated by 2.8× along with the terrain elevation, floating posts/tables ~1.7 m higher than correct.

**Fix:** take ground elevation and the real-meter offset as separate parameters, and only scale the ground term:

```ts
export function toThreePosition(
  lx: number,
  north: number,
  groundElevM: number,
  realOffsetM: number,
  center: THREE.Vector3,
): THREE.Vector3 {
  return new THREE.Vector3(lx - center.x, groundElevM * Z_SCALE + realOffsetM - center.y, -north - center.z);
}
```

Update every call site (post positions, table tops, tube endpoints — currently lines 360, 367, 393, 398, 422) to pass ground elevation and offset as two arguments instead of pre-summing them.

## 4. Recommended bundled fix — camera reset + orbit limits

This is what actually produced the broken-looking screenshot Ismail sent (long blue ribbons receding to the horizon). `controls.maxPolarAngle = Math.PI / 2.05` (line 50) lets the camera orbit down to ~88° — nearly grazing the ground — and there's no way back to a sane view once that happens.

```ts
controls.minPolarAngle = Math.PI / 8;   // ~22.5° — stop near-overhead disorientation
controls.maxPolarAngle = Math.PI / 2.4; // ~75° — stop near-horizon grazing views
```

Add a small "Reset view" button in the toolbar that re-applies the default `camera.position.set(...)` / `camera.lookAt(0, 0, 0)` and calls `controls.update()`. Cheap to add, directly fixes "got lost, can't recover."

## 5. Toolbar after this change

Only the "Terrain mesh wireframe" checkbox remains, plus the new "Reset view" button. Update the `terrain-3d-note` hint text (lines 123–127) to drop any sun references and stay focused on orbit/zoom instructions.

## Out of scope — don't touch unless separately asked

`MAX_3D_ROWS` cap, row-instancing/performance work, fixed-tilt tilt-angle logic. Not part of this request.
