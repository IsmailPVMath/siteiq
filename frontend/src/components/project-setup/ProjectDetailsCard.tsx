import type { ProjectSetupDraft } from "../../types/projectSetup";
import type { LandUse } from "../../types/gate";

interface Props {
  draft: ProjectSetupDraft;
  onChange: (patch: Partial<ProjectSetupDraft["project_info"]>) => void;
  onDesignChange: (patch: Partial<ProjectSetupDraft["design_basis"]>) => void;
}

export function ProjectDetailsCard({ draft, onChange, onDesignChange }: Props) {
  const { project_info, design_basis } = draft;

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
      <div className="grid-2">
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
    </section>
  );
}
