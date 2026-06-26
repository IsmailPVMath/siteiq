import { useEffect, useState } from "react";
import { deleteProject, listProjects, type ProjectRecord } from "../lib/api";

function projectMeta(row: ProjectRecord) {
  const d = row.project_data ?? ({} as ProjectRecord["project_data"]);
  const lat = d.center?.lat ?? (d as { lat?: number }).lat;
  const lon = d.center?.lon ?? (d as { lon?: number }).lon;
  const area = (d as { area_ha?: number }).area_ha ?? d.workflow?.gross_area_ha;
  const mode = (d.workflow as { mode?: string } | undefined)?.mode;
  const isFull = mode === "full" || Boolean(d.site_boundary_geojson);
  return {
    name: d.name || "Untitled project",
    country: d.country || "—",
    lat,
    lon,
    area_ha: typeof area === "number" ? area : null,
    land_use: d.land_use || "Standard",
    mount_type: d.mount_type || "Fixed Tilt",
    isFull,
    updated_at: row.updated_at || row.created_at,
  };
}

function formatDate(iso?: string) {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return "";
  }
}

interface Props {
  token: string;
  onOpenProject: (id: string) => void;
  onNewProject: () => void;
}

export function MyProjectsPage({ token, onOpenProject, onNewProject }: Props) {
  const [rows, setRows] = useState<ProjectRecord[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState("");

  async function load() {
    setBusy(true);
    setError("");
    try {
      setRows(await listProjects(token));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load projects");
      setRows([]);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  async function handleDelete(id: string) {
    try {
      await deleteProject(token, id);
      setConfirmDeleteId("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  return (
    <div className="workflow-page my-projects-page">
      <div className="my-projects-head">
        <div>
          <p className="my-projects-kicker">Overview</p>
          <h1>My projects</h1>
          <p className="hint">
            Every site you have saved. Open one to continue, or start a new preliminary study.
          </p>
        </div>
        <button className="btn btn-primary" type="button" onClick={onNewProject}>
          + New project
        </button>
      </div>

      {error ? <div className="error-banner">{error}</div> : null}

      {busy ? (
        <p className="hint">Loading your projects…</p>
      ) : rows.length === 0 ? (
        <div className="my-projects-empty">
          <p className="my-projects-empty-title">No projects yet</p>
          <p className="hint">
            Set up your first site on Project setup, then use <strong>Save draft</strong> to keep
            it here.
          </p>
          <button className="btn btn-primary" type="button" onClick={onNewProject}>
            Start new project
          </button>
        </div>
      ) : (
        <>
          <p className="my-projects-count">
            {rows.length} project{rows.length !== 1 ? "s" : ""}
          </p>
          <div className="my-projects-grid">
            {rows.map((row) => {
              const meta = projectMeta(row);
              return (
                <article key={row.id} className="my-project-card">
                  <h2 className="my-project-name" title={meta.name}>
                    {meta.name}
                  </h2>
                  <span
                    className={`my-project-badge${meta.isFull ? " full" : " quick"}`}
                  >
                    {meta.isFull ? "Full mode" : "Quick mode"}
                  </span>
                  <dl className="my-project-meta">
                    <div>
                      <dt>Location</dt>
                      <dd>{meta.country}</dd>
                    </div>
                    <div>
                      <dt>Coordinates</dt>
                      <dd>
                        {meta.lat != null && meta.lon != null
                          ? `${meta.lat.toFixed(4)}°, ${meta.lon.toFixed(4)}°`
                          : "—"}
                      </dd>
                    </div>
                    <div>
                      <dt>Design</dt>
                      <dd>
                        {meta.land_use} · {meta.mount_type}
                        {meta.area_ha != null ? ` · ${meta.area_ha.toFixed(1)} ha` : ""}
                      </dd>
                    </div>
                    {meta.updated_at ? (
                      <div>
                        <dt>Updated</dt>
                        <dd>{formatDate(meta.updated_at)}</dd>
                      </div>
                    ) : null}
                  </dl>
                  <div className="my-project-actions">
                    <button
                      className="btn btn-primary btn-sm"
                      type="button"
                      onClick={() => onOpenProject(row.id)}
                    >
                      Open →
                    </button>
                    {confirmDeleteId === row.id ? (
                      <>
                        <button
                          className="btn btn-ghost btn-sm"
                          type="button"
                          onClick={() => setConfirmDeleteId("")}
                        >
                          Cancel
                        </button>
                        <button
                          className="btn btn-ghost btn-sm my-project-delete"
                          type="button"
                          onClick={() => void handleDelete(row.id)}
                        >
                          Confirm delete
                        </button>
                      </>
                    ) : (
                      <button
                        className="btn btn-ghost btn-sm"
                        type="button"
                        onClick={() => setConfirmDeleteId(row.id)}
                        title="Delete project"
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
