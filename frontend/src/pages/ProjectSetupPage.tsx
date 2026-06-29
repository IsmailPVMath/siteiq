import { FormEvent, useEffect, useMemo, useReducer, useRef, useState } from "react";
import type * as GeoJSON from "geojson";
import { BoundaryWorkspace } from "../components/project-setup/BoundaryWorkspace";
import { InputMethodCards } from "../components/project-setup/InputMethodCards";
import { ProjectAssumptionsPanel } from "../components/project-setup/ProjectAssumptionsPanel";
import { ProjectDetailsCard } from "../components/project-setup/ProjectDetailsCard";
import { ProjectReadinessPanel } from "../components/project-setup/ProjectReadinessPanel";
import { assumedEnvelopeMatches, parseCoordinates, polygonAreaHa, squareBoundaryFromPin } from "../lib/coords";
import {
  computeBuildableArea,
  createProject,
  getProject,
  listProjects,
  parseBoundaryFile,
  reverseGeocode,
  searchLocation,
  updateProject,
} from "../lib/api";
import {
  DEFAULT_DRAFT,
  draftReducer,
  hasSurveyedBoundary,
  draftToGateRequest,
  draftToProjectPayload,
  effectiveRings,
  gateRequestToDraft,
  geoJsonToParcels,
  projectRecordToDraft,
  restrictionsToGeoJson,
  ringsToGeoJson,
  validateDraft,
} from "../lib/projectSetup";
import type { GateAnalyzeRequest } from "../types/gate";
import type { InputMethod, SetupParcel } from "../types/projectSetup";

export type ScreeningFormValues = GateAnalyzeRequest;

interface Props {
  token: string;
  initial?: Partial<ScreeningFormValues>;
  initialProjectId?: string;
  onOpenProjects?: () => void;
  onSubmit: (body: ScreeningFormValues) => void;
}

export function ProjectSetupPage({ token, initial, initialProjectId, onOpenProjects, onSubmit }: Props) {
  const [draft, dispatch] = useReducer(
    draftReducer,
    initial ? gateRequestToDraft(initial) : gateRequestToDraft({}),
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
  const [hintIsError, setHintIsError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showBoundaryModal, setShowBoundaryModal] = useState(false);
  const [hasUserLocation, setHasUserLocation] = useState(!!initial?.lat && !!initial?.lon);
  const [collapsedGroups, setCollapsedGroups] = useState<Record<string, boolean>>({});
  const lastGeocodedRef = useRef<string>("");

  function defaultCollapsedForParcels(parcels: SetupParcel[]) {
    const groups = Array.from(new Set(parcels.map((p) => p.layer_group || "Other")));
    return Object.fromEntries(groups.map((g, i) => [g, i > 0]));
  }

  function expandAllGroups() {
    const groups = Array.from(new Set(draft.geometry.parcels.map((p) => p.layer_group || "Other")));
    setCollapsedGroups(Object.fromEntries(groups.map((g) => [g, false])));
  }

  function collapseAllGroups() {
    const groups = Array.from(new Set(draft.geometry.parcels.map((p) => p.layer_group || "Other")));
    setCollapsedGroups(Object.fromEntries(groups.map((g) => [g, true])));
  }

  useEffect(() => {
    if (!initialProjectId) return;
    setProjectId(initialProjectId);
    if (initial) return;
    void (async () => {
      setBusy(true);
      try {
        const row = await getProject(token, initialProjectId);
        dispatch({ type: "replace", draft: projectRecordToDraft(row) });
        setHasUserLocation(true);
        setHint("Project loaded.");
      } catch (err) {
        setHint(err instanceof Error ? err.message : "Project load failed");
        setHintIsError(true);
      } finally {
        setBusy(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialProjectId, token, initial]);

  const validation = useMemo(() => validateDraft(draft), [draft]);
  const rings = useMemo(() => effectiveRings(draft), [draft]);
  const hasBoundary = rings.length > 0;

  const boundaryAreaHa = useMemo(() => {
    if (!hasBoundary) return null;
    const enabled = draft.geometry.parcels.filter((p) => p.enabled && p.coords.length >= 3);
    if (enabled.length) {
      const total = enabled.reduce(
        (sum, p) => sum + (p.area_ha > 0 ? p.area_ha : polygonAreaHa(p.coords)),
        0,
      );
      return total > 0 ? Number(total.toFixed(2)) : null;
    }
    if (draft.geometry.site_boundary && draft.geometry.site_boundary.length >= 3) {
      const ha = polygonAreaHa(draft.geometry.site_boundary);
      return ha > 0 ? ha : null;
    }
    const ringAreas = rings.map((ring) => polygonAreaHa(ring)).filter((ha) => ha > 0);
    if (!ringAreas.length) return null;
    return Number(ringAreas.reduce((sum, ha) => sum + ha, 0).toFixed(2));
  }, [draft.geometry.parcels, draft.geometry.site_boundary, hasBoundary, rings]);

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
    () => draft.geometry.parcels.map((p) => ({ id: p.id, coords: p.coords, enabled: p.enabled })),
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
    setHintIsError(false);
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
      const msg = err instanceof Error ? err.message : "Project save failed";
      setHint(msg);
      setHintIsError(true);
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
      setHasUserLocation(true);
      setHint("Project loaded.");
    } catch (err) {
      setHint(err instanceof Error ? err.message : "Project load failed");
    } finally {
      setBusy(false);
    }
  }

  function startNewProject() {
    setProjectId("");
    lastGeocodedRef.current = "";
    setHasUserLocation(false);
    setCoordPaste("");
    setSearchQ("");
    setSearchResults([]);
    dispatch({ type: "replace", draft: structuredClone(DEFAULT_DRAFT) });
    setCollapsedGroups({});
    setHint("New project started.");
    setHintIsError(false);
  }

  function onProjectSelect(id: string) {
    if (!id) {
      startNewProject();
      return;
    }
    void loadSelectedProject(id);
  }

  function applyPick(lat: number, lon: number) {
    setHasUserLocation(true);
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
    setHasUserLocation(true);
    applyPick(r.lat, r.lon);
    const parts = r.label.split(",").map((s) => s.trim());
    const country = parts.length ? parts[parts.length - 1] : "";
    const city = parts.length > 1 ? parts[0] : "";
    dispatch({
      type: "set_location",
      location: {
        lat: r.lat,
        lon: r.lon,
        label: r.label,
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
        setCollapsedGroups(defaultCollapsedForParcels(parcels));
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
      setCollapsedGroups(defaultCollapsedForParcels(incoming));
      dispatch({ type: "set_input_method", input_method: "kml" });
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

  async function submitNow() {
    await saveProjectDraft();
    onSubmit(draftToGateRequest(draft));
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validation.valid) {
      setHint(validation.issues.find((i) => i.level === "error")?.message || "Fix errors before continuing.");
      return;
    }
    if (!hasBoundary) {
      setShowBoundaryModal(true);
      return;
    }
    await submitNow();
  }

  useEffect(() => {
    void loadProjects(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Auto reverse-geocode whenever the location changes — fill country/state/city
  // so the user never has to type administrative details manually.
  useEffect(() => {
    const { lat, lon } = draft.location;
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
    const key = `${lat.toFixed(4)},${lon.toFixed(4)}`;
    if (key === lastGeocodedRef.current) return;
    const timer = window.setTimeout(async () => {
      try {
        const parts = await reverseGeocode(token, lat, lon);
        lastGeocodedRef.current = key;
        dispatch({
          type: "set_location",
          location: {
            label: parts.label || draft.location.label,
            country: parts.country || draft.location.country,
            state: parts.state || draft.location.state,
            city: parts.city || draft.location.city,
          },
        });
      } catch {
        // Non-fatal — user can still type details manually.
      }
    }, 600);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.location.lat, draft.location.lon, token]);

  useEffect(() => {
    if (hasSurveyedBoundary(draft)) return;

    const areaHa = draft.geometry.gross_area_ha;
    const { lat, lon } = draft.location;

    if (!hasUserLocation || areaHa <= 0) {
      if (draft.geometry.assumed_boundary) {
        dispatch({
          type: "set_site_boundary",
          site_boundary: undefined,
          assumed_boundary: false,
        });
      }
      return;
    }

    if (assumedEnvelopeMatches(draft.geometry.site_boundary, lat, lon, areaHa)) return;

    const square = squareBoundaryFromPin(lat, lon, areaHa);
    if (square.length < 4) return;
    dispatch({ type: "set_assumed_envelope", site_boundary: square, gross_area_ha: areaHa });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    hasUserLocation,
    draft.location.lat,
    draft.location.lon,
    draft.geometry.gross_area_ha,
    draft.geometry.parcels,
    draft.geometry.assumed_boundary,
    draft.geometry.site_boundary,
  ]);

  useEffect(() => {
    const enabled = draft.geometry.parcels.filter((p) => p.enabled);
    if (!enabled.length) return;
    const total = enabled.reduce(
      (sum, p) => sum + (p.area_ha > 0 ? p.area_ha : polygonAreaHa(p.coords)),
      0,
    );
    if (total > 0) dispatch({ type: "set_gross_area", gross_area_ha: Number(total.toFixed(2)) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.geometry.parcels]);

  useEffect(() => {
    if (draft.geometry.parcels.some((p) => p.enabled && p.coords.length >= 3)) return;
    const boundary = draft.geometry.site_boundary;
    if (!boundary || boundary.length < 3) return;
    const ha = polygonAreaHa(boundary);
    if (ha > 0) dispatch({ type: "set_gross_area", gross_area_ha: ha });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft.geometry.site_boundary, draft.geometry.parcels]);

  useEffect(() => {
    if (boundaryAreaHa == null || boundaryAreaHa <= 0) return;
    dispatch({ type: "set_gross_area", gross_area_ha: boundaryAreaHa });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boundaryAreaHa]);

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
          {onOpenProjects ? (
            <button className="btn btn-ghost btn-sm" type="button" onClick={onOpenProjects}>
              My projects
            </button>
          ) : null}
          <select value={projectId} onChange={(e) => onProjectSelect(e.target.value)}>
            <option value="">New project</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <form className="project-setup-form" onSubmit={handleSubmit}>
        <div className="project-setup-layout">
          <div className="project-setup-main">
            <ProjectDetailsCard
              draft={draft}
              onChange={(p) => dispatch({ type: "set_info", project_info: p })}
              onDesignChange={(p) => dispatch({ type: "set_design", design_basis: p })}
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
                dispatch({
                  type: "set_site_boundary",
                  site_boundary: b,
                  assumed_boundary: false,
                });
                if (b && b.length >= 3) {
                  setHasUserLocation(true);
                  dispatch({ type: "set_input_method", input_method: "map" });
                }
              }}
              onRestrictionsChange={(r) => dispatch({ type: "set_restrictions", restrictions: r })}
              onFileUpload={(f) => void onBoundaryFile(f)}
              onCoordPasteChange={setCoordPaste}
              onApplyPaste={applyPaste}
              onSearchChange={setSearchQ}
              onSearch={() => void runSearch()}
              onPickSearch={pickSearchResult}
              onLatLonChange={(lat, lon) => {
                setHasUserLocation(true);
                dispatch({ type: "set_location", location: { lat, lon } });
              }}
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
              onRemoveParcel={(id) => {
                const next = draft.geometry.parcels.filter((p) => p.id !== id);
                dispatch({ type: "set_parcels", parcels: next });
                setHint(next.length ? "Parcel removed." : "All parcels removed.");
              }}
              onRemoveGroup={(group) => {
                const next = draft.geometry.parcels.filter(
                  (p) => (p.layer_group || "Other") !== group,
                );
                dispatch({ type: "set_parcels", parcels: next });
                setHint(`Removed ${group} layer.`);
              }}
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
                      assumed_boundary: false,
                    },
                  },
                });
                setCollapsedGroups({});
                setHint("Boundary cleared.");
              }}
              onExpandAllGroups={expandAllGroups}
              onCollapseAllGroups={collapseAllGroups}
              onRemoveOverlayParcels={(ids) => {
                const next = draft.geometry.parcels.filter((p) => !ids.includes(p.id));
                dispatch({ type: "set_parcels", parcels: next });
                setHint(
                  next.length
                    ? `Removed ${ids.length} layer(s) from map.`
                    : "All parcels removed.",
                );
              }}
              hasBoundary={hasBoundary}
              hasUserLocation={hasUserLocation}
              assumedBoundary={draft.geometry.assumed_boundary}
              boundaryAreaHa={boundaryAreaHa}
              grossAreaHa={draft.geometry.gross_area_ha}
              locationLabel={draft.location.label}
              onAreaChange={(gross_area_ha) => dispatch({ type: "set_gross_area", gross_area_ha })}
            />

          </div>

          <aside className="project-setup-rail">
            <ProjectReadinessPanel validation={validation} />
            <ProjectAssumptionsPanel validation={validation} />
          </aside>
        </div>

        {hint ? (
          hintIsError ? (
            <div className="error-banner">{hint}</div>
          ) : (
            <p className="hint hint-banner">{hint}</p>
          )
        ) : null}

        <div className="project-setup-footer">
          <p className="hint">
            {draft.geometry.assumed_boundary
              ? `Assumed square envelope — ${validation.modules_to_run.join(" → ")}`
              : hasBoundary
                ? `Ready — ${validation.modules_to_run.join(" → ")}`
                : "No boundary — enter pin + area for full workflow, or continue with SiteIQ only."}
          </p>
          <div className="project-setup-footer-actions">
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => void saveProjectDraft()}
              disabled={saving || busy}
            >
              {saving ? "Saving…" : "Save"}
            </button>
            <button className="btn btn-primary btn-lg" type="submit" disabled={busy || !validation.valid}>
              Start preliminary study →
            </button>
          </div>
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
