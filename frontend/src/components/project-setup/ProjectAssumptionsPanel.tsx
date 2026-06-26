import type { SetupValidationResult } from "../../types/projectSetup";
import { DEFAULT_LAYOUT_CONFIG } from "../../types/layoutConfig";

interface Props {
  validation: SetupValidationResult;
}

export function ProjectAssumptionsPanel({ validation }: Props) {
  const a = DEFAULT_LAYOUT_CONFIG;
  return (
    <section className="setup-panel setup-assumptions">
      <h3>Smart defaults</h3>
      <p className="hint">PVMath applies industry assumptions automatically for the preliminary study.</p>
      <ul className="assumptions-list">
        <li>
          <strong>Module</strong> — {a.module_wp} Wp · {a.module_h} × {a.module_w} m
        </li>
        <li>
          <strong>Strings</strong> — {a.modules_per_string} modules/string · {a.inter_string_gap_m * 1000} mm gap
        </li>
        <li>
          <strong>Trackers</strong> — {a.tracker_string_options.join("S / ")}S units · max {a.max_tracker_length_m} m
        </li>
        <li>
          <strong>Terrain</strong> — EU-DEM (Europe) or SRTM (global) from location
        </li>
        <li>
          <strong>Irradiation</strong> — PVGIS satellite-based GHI/DNI
        </li>
      </ul>
      {validation.readiness.has_boundary ? (
        <p className="hint setup-panel-note">
          Boundary detected — full pipeline will run automatically after you start.
        </p>
      ) : (
        <p className="hint setup-panel-note warn">
          Add a boundary to unlock TerrainIQ, LayoutIQ, and YieldIQ.
        </p>
      )}
    </section>
  );
}
