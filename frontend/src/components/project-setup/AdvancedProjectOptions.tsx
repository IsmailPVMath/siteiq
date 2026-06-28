import type { ProjectSetupDraft } from "../../types/projectSetup";
import { ROAD_PRESETS, roadParamsFromPreset } from "../../types/layoutConfig";
import type { RoadMode } from "../../types/layoutConfig";

interface Props {
  draft: ProjectSetupDraft;
  trackerStringOptions: string;
  onTrackerStringOptionsChange: (v: string) => void;
  onDesignChange: (patch: Partial<ProjectSetupDraft["design_basis"]>) => void;
  onInfoChange: (patch: Partial<ProjectSetupDraft["project_info"]>) => void;
  onAssumptionsChange: (patch: Partial<ProjectSetupDraft["assumptions"]>) => void;
  onRoadModeChange: (mode: RoadMode, preset: string) => void;
}

export function AdvancedProjectOptions({
  draft,
  trackerStringOptions,
  onTrackerStringOptionsChange,
  onDesignChange,
  onInfoChange,
  onAssumptionsChange,
  onRoadModeChange,
}: Props) {
  const a = draft.assumptions;
  const d = draft.design_basis;

  return (
    <details className="setup-card layout-advanced">
      <summary>
        <h2>Advanced options</h2>
      </summary>
      <p className="hint">Override defaults only when you need a specific product or standard.</p>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="target-cap">Target capacity (MWp)</label>
          <input
            id="target-cap"
            type="number"
            step="0.1"
            min="0"
            value={d.target_capacity_mwp ?? ""}
            onChange={(e) =>
              onDesignChange({
                target_capacity_mwp: e.target.value ? Number(e.target.value) : null,
              })
            }
            placeholder="Optional"
          />
        </div>
        <div className="field">
          <label htmlFor="target-cod">Target COD</label>
          <input
            id="target-cod"
            value={d.target_cod}
            onChange={(e) => onDesignChange({ target_cod: e.target.value })}
            placeholder="e.g. Q4 2027"
          />
        </div>
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="currency">Currency</label>
          <input id="currency" value={d.currency} onChange={(e) => onDesignChange({ currency: e.target.value })} />
        </div>
        <div className="field">
          <label htmlFor="crs">Coordinate system</label>
          <input
            id="crs"
            value={d.coordinate_system}
            onChange={(e) => onDesignChange({ coordinate_system: e.target.value })}
          />
        </div>
      </div>
      <div className="field">
        <label htmlFor="notes">Notes</label>
        <textarea
          id="notes"
          rows={2}
          value={draft.project_info.notes}
          onChange={(e) => onInfoChange({ notes: e.target.value })}
          placeholder="Internal project notes"
        />
      </div>
      <h3 className="setup-subhead">Module &amp; electrical</h3>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="module-h">Module height (m)</label>
          <input
            id="module-h"
            type="number"
            step="0.001"
            value={a.module_h ?? ""}
            onChange={(e) => onAssumptionsChange({ module_h: Number(e.target.value) })}
          />
        </div>
        <div className="field">
          <label htmlFor="module-w">Module width (m)</label>
          <input
            id="module-w"
            type="number"
            step="0.001"
            value={a.module_w ?? ""}
            onChange={(e) => onAssumptionsChange({ module_w: Number(e.target.value) })}
          />
        </div>
      </div>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="module-wp">Module power (Wp)</label>
          <input
            id="module-wp"
            type="number"
            value={a.module_wp ?? ""}
            onChange={(e) => onAssumptionsChange({ module_wp: Number(e.target.value) })}
          />
        </div>
        <div className="field">
          <label htmlFor="mps">Modules per string</label>
          <input
            id="mps"
            type="number"
            value={a.modules_per_string ?? ""}
            onChange={(e) => onAssumptionsChange({ modules_per_string: Number(e.target.value) })}
          />
        </div>
      </div>
      <div className="field">
        <label htmlFor="tracker-strings">Tracker string options</label>
        <input
          id="tracker-strings"
          value={trackerStringOptions}
          onChange={(e) => onTrackerStringOptionsChange(e.target.value)}
          placeholder="8,7,6,5,4,3,2,1"
        />
      </div>
      <div className="grid-2">
        <label className="checkbox-field">
          <input
            type="checkbox"
            checked={!!a.exclude_tracker_slope}
            onChange={(e) => onAssumptionsChange({ exclude_tracker_slope: e.target.checked })}
          />
          Exclude trackers where slope exceeds limit
        </label>
        {a.exclude_tracker_slope ? (
          <div className="field">
            <label htmlFor="slope-limit">Slope limit (%)</label>
            <input
              id="slope-limit"
              type="number"
              step="0.5"
              min="0"
              value={a.tracker_slope_limit_pct ?? ""}
              onChange={(e) =>
                onAssumptionsChange({
                  tracker_slope_limit_pct: e.target.value ? Number(e.target.value) : undefined,
                })
              }
              placeholder="6"
            />
          </div>
        ) : null}
      </div>
      <div className="field">
        <label htmlFor="road-preset">Access roads</label>
        <select
          id="road-preset"
          value={a.road_preset || "no_roads"}
          onChange={(e) => {
            const id = e.target.value;
            if (id === "no_roads") onRoadModeChange("off", id);
            else if (id === "sat_auto") onRoadModeChange("auto", id);
            else onRoadModeChange("manual", id);
            if (id !== "custom") {
              const p = roadParamsFromPreset(id);
              onAssumptionsChange({
                cols_per_block: p.cols_per_block,
                ew_gap_m: p.ew_gap_m,
                rows_per_block: p.rows_per_block,
                ns_gap_1_m: p.ns_gap_1_m,
                block_gap_m: p.block_gap_m,
              });
            }
          }}
        >
          {ROAD_PRESETS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
        </select>
      </div>
      {a.road_preset === "custom" ? (
        <>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="cols-per-block">Columns before E-W gap</label>
              <input
                id="cols-per-block"
                type="number"
                step="1"
                min="0"
                value={a.cols_per_block ?? ""}
                onChange={(e) =>
                  onAssumptionsChange({
                    cols_per_block: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                placeholder="50"
              />
            </div>
            <div className="field">
              <label htmlFor="ew-gap">E-W gap / road (m)</label>
              <input
                id="ew-gap"
                type="number"
                step="0.5"
                min="0"
                value={a.ew_gap_m ?? ""}
                onChange={(e) =>
                  onAssumptionsChange({
                    ew_gap_m: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                placeholder="6"
              />
            </div>
          </div>
          <div className="field">
            <label htmlFor="rows-per-block">Pitch bands before N-S road</label>
            <input
              id="rows-per-block"
              type="number"
              step="1"
              min="0"
              value={a.rows_per_block ?? ""}
              onChange={(e) =>
                onAssumptionsChange({
                  rows_per_block: e.target.value ? Number(e.target.value) : undefined,
                })
              }
              placeholder="16"
            />
          </div>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="ns-gap-1">First N-S gap (m)</label>
              <input
                id="ns-gap-1"
                type="number"
                step="0.1"
                min="0"
                value={a.ns_gap_1_m ?? ""}
                onChange={(e) =>
                  onAssumptionsChange({
                    ns_gap_1_m: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                placeholder="0.6"
              />
            </div>
            <div className="field">
              <label htmlFor="block-gap">Second N-S gap / road (m)</label>
              <input
                id="block-gap"
                type="number"
                step="0.5"
                min="0"
                value={a.block_gap_m ?? ""}
                onChange={(e) =>
                  onAssumptionsChange({
                    block_gap_m: e.target.value ? Number(e.target.value) : undefined,
                  })
                }
                placeholder="5"
              />
            </div>
          </div>
        </>
      ) : null}
    </details>
  );
}
