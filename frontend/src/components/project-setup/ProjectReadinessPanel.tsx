import type { SetupValidationResult } from "../../types/projectSetup";

interface Props {
  validation: SetupValidationResult;
}

export function ProjectReadinessPanel({ validation }: Props) {
  const modules = [
    { key: "siteiq", label: "SiteIQ", ok: validation.readiness.can_run_siteiq },
    { key: "terrainiq", label: "TerrainIQ", ok: validation.readiness.can_run_terrainiq },
    { key: "layoutiq", label: "LayoutIQ", ok: validation.readiness.can_run_layoutiq },
    { key: "yieldiq", label: "YieldIQ", ok: validation.readiness.can_run_yieldiq },
  ];

  return (
    <section className="setup-panel setup-readiness">
      <h3>Preliminary study</h3>
      <p className="hint">Modules that will run when you click Start:</p>
      <ul className="readiness-modules">
        {modules.map((m) => (
          <li key={m.key} className={m.ok ? "ready" : "blocked"}>
            <span className="readiness-dot" aria-hidden />
            {m.label}
            <span className="readiness-status">{m.ok ? "Ready" : "Needs boundary"}</span>
          </li>
        ))}
      </ul>
      {validation.issues.length > 0 ? (
        <div className="readiness-issues">
          {validation.issues.map((issue, i) => (
            <p key={i} className={`readiness-issue ${issue.level}`}>
              {issue.message}
            </p>
          ))}
        </div>
      ) : (
        <p className="hint setup-panel-note">All required inputs are complete.</p>
      )}
    </section>
  );
}
