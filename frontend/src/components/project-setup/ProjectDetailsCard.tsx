import type { ProjectSetupDraft } from "../../types/projectSetup";
import type { LandUse } from "../../types/gate";

interface Props {
  draft: ProjectSetupDraft;
  onChange: (patch: Partial<ProjectSetupDraft["project_info"]>) => void;
  onDesignChange: (patch: Partial<ProjectSetupDraft["design_basis"]>) => void;
  onLocationChange: (patch: Partial<ProjectSetupDraft["location"]>) => void;
  onAreaChange: (gross_area_ha: number) => void;
}

export function ProjectDetailsCard({
  draft,
  onChange,
  onDesignChange,
  onLocationChange,
  onAreaChange,
}: Props) {
  const { project_info, location, design_basis, geometry } = draft;

  return (
    <section className="setup-card">
      <h2>Project details</h2>
      <div className="grid-2">
        <div className="field">
          <label htmlFor="project-name">Project name</label>
          <input
            id="project-name"
            value={project_info.name}
            onChange={(e) => onChange({ name: e.target.value })}
            placeholder="e.g. Bavaria Solar Park"
          />
        </div>
        <div className="field">
          <label htmlFor="client">Client</label>
          <input
            id="client"
            value={project_info.client}
            onChange={(e) => onChange({ client: e.target.value })}
            placeholder="Optional"
          />
        </div>
      </div>
      <div className="setup-location-group">
        <div className="setup-location-head">
          <span>Location</span>
          <span className="hint">Auto-filled from map / coordinates — optional</span>
        </div>
        <div className="grid-3">
          <div className="field">
            <label htmlFor="country">Country</label>
            <input
              id="country"
              value={location.country}
              onChange={(e) => onLocationChange({ country: e.target.value })}
              placeholder="Auto"
            />
          </div>
          <div className="field">
            <label htmlFor="state">State / region</label>
            <input
              id="state"
              value={location.state}
              onChange={(e) => onLocationChange({ state: e.target.value })}
              placeholder="Auto"
            />
          </div>
          <div className="field">
            <label htmlFor="city">Nearest city</label>
            <input
              id="city"
              value={location.city}
              onChange={(e) => onLocationChange({ city: e.target.value })}
              placeholder="Auto"
            />
          </div>
        </div>
      </div>
      <div className="grid-3">
        <div className="field">
          <label htmlFor="land">Project type</label>
          <select
            id="land"
            value={design_basis.land_use}
            onChange={(e) => onDesignChange({ land_use: e.target.value as LandUse })}
          >
            <option value="Standard">Standard Ground Mount</option>
            <option value="Agri-PV">Agri-PV (Dual Use)</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="area">Gross area (ha)</label>
          <input
            id="area"
            type="number"
            step="any"
            min="0.1"
            value={geometry.gross_area_ha}
            onChange={(e) => onAreaChange(Number(e.target.value))}
          />
        </div>
        <div className="field">
          <label htmlFor="units">Units</label>
          <select
            id="units"
            value={design_basis.units}
            onChange={(e) => onDesignChange({ units: e.target.value as "metric" | "imperial" })}
          >
            <option value="metric">Metric</option>
            <option value="imperial">Imperial</option>
          </select>
        </div>
      </div>
      {geometry.buildable_area_ha != null ? (
        <p className="hint setup-buildable">
          Buildable: <strong>{geometry.buildable_area_ha} ha</strong>
        </p>
      ) : null}
    </section>
  );
}
