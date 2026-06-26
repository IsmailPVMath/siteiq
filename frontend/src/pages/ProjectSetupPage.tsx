import { FormEvent, useEffect, useMemo, useReducer, useState } from "react";
import type * as GeoJSON from "geojson";
import { AdvancedProjectOptions } from "../components/project-setup/AdvancedProjectOptions";
import { BoundaryWorkspace } from "../components/project-setup/BoundaryWorkspace";
import { InputMethodCards } from "../components/project-setup/InputMethodCards";
import { ProjectAssumptionsPanel } from "../components/project-setup/ProjectAssumptionsPanel";
import { ProjectDetailsCard } from "../components/project-setup/ProjectDetailsCard";
import { ProjectReadinessPanel } from "../components/project-setup/ProjectReadinessPanel";
import { parseCoordinates } from "../lib/coords";
import {
  computeBuildableArea,
  createProject,
  getProject,
  listProjects,
  parseBoundaryFile,
  searchLocation,
  updateProject,
} from "../lib/api";
import {
  draftReducer,
  draftToGateRequest,
  draftToProjectPayload,
  effectiveRings,
  gateRequestToDraft,
  geoJsonToParcels,
  parseTrackerStringOptions,
  projectRecordToDraft,
  restrictionsToGeoJson,
  ringsToGeoJson,
  validateDraft,
} from "../lib/projectSetup";
import type { GateAnalyzeRequest } from "../types/gate";
import type { InputMethod, SetupParcel } from "../types/projectSetup";
import type { RoadMode } from "../types/layoutConfig";

export type ScreeningFormValues = GateAnalyzeRequest;

interface Props {
  token: string;
  initial?: Partial<ScreeningFormValues>;
  onSubmit: (body: ScreeningFormValues) => void;
}

export function ProjectSetupPage({ token, initial, onSubmit }: Props) {
  const [draft, dispatch] = useReducer(
    draftReducer,
    initial ? gateRequestToDraft(initial) : gateRequestToDraft({}),
  );
  const [trackerStringOptions, setTrackerStringOptions] = useState(
    (draft.assumptions.tracker_string_options ?? [8, 7, 6, 5]).join(","),
  );
  const [drawMode, setDrawMode] = useState<"site" | "restriction">("site");
  const [projects, setProjects] = useState<{ id: string; name: string }[]>([]);
  const [projectId, setProjectId] = useState("");
  const [coordPaste, setCoordPaste] = useState("");
  const [searchQ, setSearchQ] = useState("");
  const [searchResults, setSearchResults] = useState<
    { lat: number; lon: number; label: string }[]
  >([]);
  const [hint, setHint] = useState("");
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showBoundaryModal, setShowBoundaryModal] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});

  const validation = useMemo(() => validateDraft(draft), [draft]);
  const rings = useMemo(() => effectiveRings(draft), [draft]);
  const hasBoundary = rings.length > 0;

  const parcelGroups = useMemo(() => {
    const order: string[] = [];
    const buckets = new Map<string, SetupParcel[]>();
    for (const p of draft.geometry.parcels) {
      const g = p.layer_group || "Other";
      if (!buckets.has(g)) {
        buckets.set(g, []);
        order.push(g);
      }
      buckets.get(g)!.push(p);
    }
    return order.map((g) => {
      const items = buckets.get(g)!;
      const enabled = items.filter((p) => p.enabled).length;
      const area = items.reduce((sum, p) => sum + (p.area_ha || 0), 0);
      return { group: g, items, enabled, total: items.length, area };
    });
  }, [draft.geometry.parcels]);

  const overlayParcels = useMemo(
    () => draft.geometry.parcels.map((p) => ({ coords: p.coords, enabled: p.enabled })),
    [draft.geometry.parcels],
  );

  async function loadProjects(loadFirst = true) {
    try {
      const rows = await listProjects(token);
      setProjects(
        rows.map((r) => ({
          id: r.id,
          name: r.project_data?.name || `Project ${r.id.slice(0, 8)}`,
        })),
      );
      if (loadFirst && rows.length) {
        setProjectId(rows[0].id);
        dispatch({ type: "replace", draft: projectRecordToDraft(rows[0]) });
      }
    } catch {
      // projects optional
    }
  }

  async function saveProjectDraft() {
    setSaving(true);
    try {
      const payload = draftToProjectPayload(draft);
      const row = projectId
        ? await updateProject(token, projectId, payload)
        : await createProject(token, payload);
      setProjectId(row.id);
      setHint(projectId ? "Project updated." : "Project saved.");
      await loadProjects(false);
      return row.id;
    } catch (err) {
      setHint(err instanceof Error ? err.message : "Project save failed");
      return null;
    } finally {
      setSaving(false);
    }
  }

  async function loadSelectedProject(id: string) {
    if (!id) return;
    setBusy(true);
    try {
      const row = await getProject(token, id);
      setProjectId(row.id);
      dispatch({ type: "replace", draft: projectRecordToDraft(row) });
      setHint("Project loaded.");
    } catch (err) {
      setHint(err instanceof Error ? err.message : "Project load failed");
    } finally {
      setBusy(false);
    }
  }

  function applyPick(lat: number, lon: number) {
    dispatch({ type: "set_location", location: { lat: Number(lat.toFixed(6)), lon: Number(lon.toFixed(6)) } });
  }

  function applyPaste() {
    const parsed = parseCoordinates(coordPaste);
    if (!parsed) {
      setHint("Could not read coordinates — paste lat, lon or a Google Maps link.");
      return;
    }
    applyPick(parsed.lat, parsed.lon);
    setHint("Location updated from paste.");
  }

  async function runSearch() {
    if (!searchQ.trim()) return;
    setBusy(true);
    try {
      const { results } = await searchLocation(token, searchQ.trim());
      setSearchResults(results);
      if (!results.length) setHint("No results — try a city, region, or address.");
    } catch (err) {
      setHint(err instanceof Error ? err.message : "Search failed");
    } finally {
      setBusy(false);
    }
  }

  function pickSearchResult(r: { lat: number; lon: number; label: string }) {
    applyPick(r.lat, r.lon);
    const parts = r.label.split(",").map((s) => s.trim());
    const country = parts.length ? parts[parts.length - 1] : "";
    const city = parts.length > 1 ? parts[0] : "";
    dispatch({
      type: "set_location",
      location: {
        lat: r.lat,
        lon: r.lon,
        city: city || draft.location.city,
        country: draft.location.country || country,
      },
    });
    setSearchResults([]);
    setSearchQ(r.label);
    setHint("Location set from search.");
  }

  async function onBoundaryFile(file: File) {
    setBusy(true);
    setHint("");
    const name = file.name.toLowerCase();
    try {
      if (name.endsWith(".geojson") || name.endsWith(".json")) {
        const text = await file.text();
        const geo = JSON.parse(text) as GeoJSON.GeoJSON;
        const parcels = geoJsonToParcels(geo, file.name.replace(/\.[^.]+$/, ""));
        if (!parcels.length) throw new Error("No polygon found in GeoJSON");
        dispatch({ type: "set_parcels", parcels });
        dispatch({ type: "set_input_method", input_method: "geojson" });
        const best = parcels.reduce((a, b) => (b.coords.length > a.coords.length ? b : a));
        const clat = best.coords.reduce((s, p) => s + p.lat, 0) / best.coords.length;
        const clon = best.coords.reduce((s, p) => s + p.lon, 0) / best.coords.length;
        applyPick(clat, clon);
        setHint(`Loaded ${parcels.length} polygon(s) from GeoJSON.`);
        return;
      }
      const parsed = await parseBoundaryFile(token, file);
      const incoming: SetupParcel[] =
        parsed.parcels && parsed.parcels.length
          ? parsed.parcels.map((p) => ({
              id: p.id,
              name: p.name,
              layer_group: p.layer_group || "Parcels",
              area_ha: p.area_ha,
              coords: p.boundary,
              enabled: p.is_primary,
            }))
          : [
              {
                id: "kml_0",
                name: parsed.name,
                layer_group: "Parcels",
                area_ha: parsed.area_ha,
                coords: parsed.boundary,
                enabled: true,
              },
            ];
      if (!incoming.some((p) => p.enabled) && incoming.length) {
        incoming.reduce((a, b) => (b.area_ha > a.area_ha ? b : a)).enabled = true;
      }
      dispatch({ type: "set_parcels", parcels: incoming });
      dispatch({
        type: "set_input_method",
        input_method: name.endsWith(".kmz") ? "kmz" : "kml",
      });
      applyPick(parsed.lat, parsed.lon);
      if (!draft.project_info.name || draft.project_info.name === "New project") {
        dispatch({ type: "set_info", project_info: { name: parsed.name } });
      }
      const total = incoming.filter((p) => p.enabled).reduce((s, p) => s + p.area_ha, 0);
      if (total > 0) dispatch({ type: "set_gross_area", gross_area_ha: Number(total.toFixed(2)) });
      setHint(`Loaded ${incoming.length} parcel(s).`);
    } catch (err) {
      setHint(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  function selectInputMethod(method: InputMethod) {
    dispatch({ type: "set_input_method", input_method: method });
    if (method === "map") setDrawMode("site");
  }

  function submitNow() {
    void saveProjectDraft();
    const next = {
      ...draft,
      assumptions: {
        ...draft.assumptions,
        tracker_string_options: parseTrackerStringOptions(trackerStringOptions),
      },
    };
    onSubmit(draftToGateRequest(next));
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validation.valid) {
      setHint(validation.issues.find((i) => i.level === "error")?.message || "Fix errors before continuing.");
      return;
    }
    if (!hasBoundary) {
      setShowBoundaryModal(true);
      return;
    }
    submitNow();
  }

  useEffect(() => {
    void loadProjects(!initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const enabled = draft.geometry.parcels.filter((p) => p.enabled);
    if (!enabled.length) return;
    const total = enabled.reduce((sum, p) => sum + (p.area_ha || 0), 0);
    if (total > 0) dispatch({ type: "set_gross_area", gross_area_ha: Number(total.toFixed(2)) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.geometry.parcels]);

  useEffect(() => {
    if (!hasBoundary) {
      dispatch({ type: "set_buildable", buildable_area_geojson: null, buildable_area_ha: null });
      return;
    }
    const siteGeoJson = ringsToGeoJson(rings);
    if (!siteGeoJson) return;
    const timer = window.setTimeout(async () => {
      try {
        const preview = await computeBuildableArea(token, {
          site_boundary_geojson: siteGeoJson,
          restriction_polygons_geojson: restrictionsToGeoJson(draft.geometry.restrictions),
        });
        dispatch({
          type: "set_buildable",
          buildable_area_geojson: preview.buildable_area_geojson,
          buildable_area_ha: preview.buildable_area_ha,
        });
      } catch {
        dispatch({ type: "set_buildable", buildable_area_geojson: null, buildable_area_ha: null });
      }
    }, 250);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rings, draft.geometry.restrictions, token]);

  return (
    <div className="workflow-page project-setup-page">
      <div className="project-setup-head">
        <div>
          <h1>Project setup</h1>
          <p>
            Enter essential project details, choose how to define the site, then start the
            automated preliminary study.
          </p>
        </div>
        <div className="project-setup-save">
          <select value={projectId} onChange={(e) => void loadSelectedProject(e.target.value)}>
            <option value="">New project</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            className="btn btn-ghost"
            type="button"
            onClick={() => void saveProjectDraft()}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save draft"}
          </button>
        </div>
      </div>

      <form className="project-setup-form" onSubmit={handleSubmit}>
        <div className="project-setup-layout">
          <div className="project-setup-main">
            <ProjectDetailsCard
              draft={draft}
              onChange={(p) => dispatch({ type: "set_info", project_info: p })}
              onDesignChange={(p) => dispatch({ type: "set_design", design_basis: p })}
              onLocationChange={(p) => dispatch({ type: "set_location", location: p })}
              onAreaChange={(gross_area_ha) => dispatch({ type: "set_gross_area", gross_area_ha })}
            />

            <section className="setup-card">
              <h2>Input method</h2>
              <InputMethodCards selected={draft.input_method} onSelect={selectInputMethod} />
            </section>

            <BoundaryWorkspace
              draft={draft}
              inputMethod={draft.input_method}
              drawMode={drawMode}
              coordPaste={coordPaste}
              searchQ={searchQ}
              searchResults={searchResults}
              parcelGroups={parcelGroups}
              collapsedGroups={collapsedGroups}
              overlayParcels={overlayParcels}
              buildableAreaGeoJson={draft.geometry.buildable_area_geojson}
              busy={busy}
              onDrawModeChange={setDrawMode}
              onPick={applyPick}
              onSiteBoundaryChange={(b) => {
                dispatch({ type: "set_site_boundary", site_boundary: b });
                if (b && b.length >= 3) dispatch({ type: "set_input_method", input_method: "map" });
              }}
              onRestrictionsChange={(r) => dispatch({ type: "set_restrictions", restrictions: r })}
              onFileUpload={(f) => void onBoundaryFile(f)}
              onCoordPasteChange={setCoordPaste}
              onApplyPaste={applyPaste}
              onSearchChange={setSearchQ}
              onSearch={() => void runSearch()}
              onPickSearch={pickSearchResult}
              onLatLonChange={(lat, lon) => dispatch({ type: "set_location", location: { lat, lon } })}
              onToggleParcel={(id) => {
                dispatch({
                  type: "set_parcels",
                  parcels: draft.geometry.parcels.map((p) =>
                    p.id === id ? { ...p, enabled: !p.enabled } : p,
                  ),
                });
              }}
              onToggleGroup={(group, enabled) => {
                dispatch({
                  type: "set_parcels",
                  parcels: draft.geometry.parcels.map((p) =>
                    (p.layer_group || "Other") === group ? { ...p, enabled } : p,
                  ),
                });
              }}
              onToggleGroupCollapsed={(g) =>
                setCollapsedGroups((prev) => ({ ...prev, [g]: !prev[g] }))
              }
              onClearBoundary={() => {
                dispatch({
                  type: "patch",
                  patch: {
                    geometry: {
                      ...draft.geometry,
                      site_boundary: undefined,
                      parcels: [],
                      restrictions: [],
                      buildable_area_geojson: null,
                      buildable_area_ha: null,
                    },
                  },
                });
                setHint("Boundary cleared.");
              }}
            />

            <AdvancedProjectOptions
              draft={draft}
              trackerStringOptions={trackerStringOptions}
              onTrackerStringOptionsChange={setTrackerStringOptions}
              onDesignChange={(p) => dispatch({ type: "set_design", design_basis: p })}
              onInfoChange={(p) => dispatch({ type: "set_info", project_info: p })}
              onAssumptionsChange={(p) => dispatch({ type: "set_assumptions", assumptions: p })}
              onRoadModeChange={(mode, preset) =>
                dispatch({
                  type: "set_assumptions",
                  assumptions: { road_mode: mode as RoadMode, road_preset: preset },
                })
              }
            />
          </div>

          <aside className="project-setup-rail">
            <ProjectReadinessPanel validation={validation} />
            <ProjectAssumptionsPanel validation={validation} />
          </aside>
        </div>

        {hint ? <p className="hint hint-banner">{hint}</p> : null}

        <div className="project-setup-footer">
          <p className="hint">
            {hasBoundary
              ? `Ready — ${validation.modules_to_run.join(" → ")}`
              : "No boundary — SiteIQ screening only unless you add a boundary."}
          </p>
          <button className="btn btn-primary btn-lg" type="submit" disabled={busy || !validation.valid}>
            Start preliminary study →
          </button>
        </div>
      </form>

      {showBoundaryModal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-card">
            <h2>No site boundary yet</h2>
            <p>
              Without a boundary you can run <strong>SiteIQ screening only</strong>. TerrainIQ,
              LayoutIQ, and YieldIQ need a site boundary.
            </p>
            <div className="modal-actions">
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => setShowBoundaryModal(false)}
              >
                Add boundary
              </button>
              <button
                className="btn btn-primary"
                type="button"
                onClick={() => {
                  setShowBoundaryModal(false);
                  submitNow();
                }}
              >
                Continue with SiteIQ only
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
