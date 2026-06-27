import { useEffect, useMemo, useRef, useState } from "react";
import { deleteProject, deleteProjectsBulk, listProjects, type ProjectRecord } from "../lib/api";

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
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [bulkDeleteBusy, setBulkDeleteBusy] = useState(false);
  const selectAllRef = useRef<HTMLInputElement>(null);

  const allIds = useMemo(() => rows.map((row) => row.id), [rows]);
  const selectedCount = selectedIds.size;
  const allSelected = rows.length > 0 && selectedCount === rows.length;
  const someSelected = selectedCount > 0 && !allSelected;

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = someSelected;
    }
  }, [someSelected]);

  async function load() {
    setBusy(true);
    setError("");
    try {
      const nextRows = await listProjects(token);
      setRows(nextRows);
      setSelectedIds(new Set());
      setConfirmBulkDelete(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load projects");
      setRows([]);
      setSelectedIds(new Set());
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  function toggleSelectAll(checked: boolean) {
    setSelectedIds(checked ? new Set(allIds) : new Set());
    setConfirmBulkDelete(false);
  }

  function toggleSelectId(id: string, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (checked) next.add(id);
      else next.delete(id);
      return next;
    });
    setConfirmBulkDelete(false);
  }

  async function handleDelete(id: string) {
    try {
      await deleteProject(token, id);
      setConfirmDeleteId("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed");
    }
  }

  async function handleDeleteSelected() {
    const ids = [...selectedIds];
    if (!ids.length) return;
    setBulkDeleteBusy(true);
    setError("");
    try {
      await deleteProjectsBulk(token, ids);
      setConfirmBulkDelete(false);
      setConfirmDeleteId("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete selected failed");
    } finally {
      setBulkDeleteBusy(false);
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
          <div className="my-projects-toolbar">
            <div className="my-projects-toolbar-left">
              <p className="my-projects-count">
                {rows.length} project{rows.length !== 1 ? "s" : ""}
              </p>
              <label className="my-projects-select-all checkbox-field">
                <input
                  ref={selectAllRef}
                  type="checkbox"
                  checked={allSelected}
                  disabled={bulkDeleteBusy}
                  onChange={(event) => toggleSelectAll(event.target.checked)}
                />
                Select all
              </label>
              {selectedCount > 0 ? (
                <span className="my-projects-selected-count">
                  {selectedCount} selected
                </span>
              ) : null}
            </div>
            {confirmBulkDelete ? (
              <div className="my-projects-bulk-delete">
                <span className="hint">
                  Delete {selectedCount} selected project{selectedCount !== 1 ? "s" : ""}? This
                  cannot be undone.
                </span>
                <button
                  className="btn btn-ghost btn-sm"
                  type="button"
                  disabled={bulkDeleteBusy}
                  onClick={() => setConfirmBulkDelete(false)}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-ghost btn-sm my-project-delete"
                  type="button"
                  disabled={bulkDeleteBusy}
                  onClick={() => void handleDeleteSelected()}
                >
                  {bulkDeleteBusy ? "Deleting…" : "Confirm delete"}
                </button>
              </div>
            ) : (
              <button
                className="btn btn-ghost btn-sm my-project-delete"
                type="button"
                disabled={bulkDeleteBusy || selectedCount === 0}
                onClick={() => {
                  setConfirmDeleteId("");
                  setConfirmBulkDelete(true);
                }}
              >
                Delete selected
              </button>
            )}
          </div>
          <div className="my-projects-grid">
            {rows.map((row) => {
              const meta = projectMeta(row);
              const isSelected = selectedIds.has(row.id);
              return (
                <article
                  key={row.id}
                  className={`my-project-card${isSelected ? " selected" : ""}`}
                >
                  <div className="my-project-card-top">
                    <label className="my-project-select checkbox-field" title="Select project">
                      <input
                        type="checkbox"
                        checked={isSelected}
                        disabled={bulkDeleteBusy}
                        onChange={(event) => toggleSelectId(row.id, event.target.checked)}
                      />
                    </label>
                    <h2 className="my-project-name" title={meta.name}>
                      {meta.name}
                    </h2>
                  </div>
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
