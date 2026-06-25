import { FormEvent, useEffect, useMemo, useState } from "react";
import type * as GeoJSON from "geojson";
import { SiteMap, type OverlayParcel } from "../components/SiteMap";
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
import type { BoundaryPoint, GateAnalyzeRequest, LandUse } from "../types/gate";
import {
  DEFAULT_LAYOUT_CONFIG,
  ROAD_PRESETS,
  type RoadMode,
} from "../types/layoutConfig";

export type ScreeningFormValues = GateAnalyzeRequest;

interface Parcel {
  id: string;
  name: string;
  layer_group: string;
  area_ha: number;
  coords: BoundaryPoint[];
  enabled: boolean;
}

interface Props {
  token: string;
  initial?: Partial<ScreeningFormValues>;
  onSubmit: (body: ScreeningFormValues) => void;
}

const DEFAULTS: ScreeningFormValues = {
  project_name: "New project",
  lat: 48.1351,
  lon: 11.582,
  area_ha: 25,
  land_use: "Standard",
  mount_type: "Fixed Tilt",
  country: "Germany",
  run_layout: false,
};

export function InputPage({ token, initial, onSubmit }: Props) {
  const [projectName, setProjectName] = useState(
    initial?.project_name ?? DEFAULTS.project_name,
  );
  const [lat, setLat] = useState(initial?.lat ?? DEFAULTS.lat);
  const [lon, setLon] = useState(initial?.lon ?? DEFAULTS.lon);
  const [areaHa, setAreaHa] = useState(initial?.area_ha ?? DEFAULTS.area_ha);
  const [country, setCountry] = useState(initial?.country ?? DEFAULTS.country);
  const [landUse, setLandUse] = useState<LandUse>(initial?.land_use ?? DEFAULTS.land_use);
  const [mountType, setMountType] = useState(initial?.mount_type ?? DEFAULTS.mount_type);
  const [moduleH, setModuleH] = useState(initial?.module_h ?? DEFAULT_LAYOUT_CONFIG.module_h);
  const [moduleW, setModuleW] = useState(initial?.module_w ?? DEFAULT_LAYOUT_CONFIG.module_w);
  const [moduleWp, setModuleWp] = useState(initial?.module_wp ?? DEFAULT_LAYOUT_CONFIG.module_wp);
  const [modulesPerString, setModulesPerString] = useState(
    initial?.modules_per_string ?? DEFAULT_LAYOUT_CONFIG.modules_per_string,
  );
  const [interStringGap, setInterStringGap] = useState(
    initial?.inter_string_gap_m ?? DEFAULT_LAYOUT_CONFIG.inter_string_gap_m,
  );
  const [trackerStringOptions, setTrackerStringOptions] = useState(
    (initial?.tracker_string_options ?? DEFAULT_LAYOUT_CONFIG.tracker_string_options).join(","),
  );
  const [maxTrackerLength, setMaxTrackerLength] = useState(
    initial?.max_tracker_length_m ?? DEFAULT_LAYOUT_CONFIG.max_tracker_length_m,
  );
  const [excludeTrackerSlope, setExcludeTrackerSlope] = useState(
    initial?.exclude_tracker_slope ?? DEFAULT_LAYOUT_CONFIG.exclude_tracker_slope,
  );
  const [trackerSlopeLimit, setTrackerSlopeLimit] = useState(
    initial?.tracker_slope_limit_pct ?? DEFAULT_LAYOUT_CONFIG.tracker_slope_limit_pct,
  );
  const [roadMode, setRoadMode] = useState<RoadMode>(
    initial?.road_mode ?? DEFAULT_LAYOUT_CONFIG.road_mode,
  );
  const [roadPreset, setRoadPreset] = useState(
    initial?.road_preset ?? DEFAULT_LAYOUT_CONFIG.road_preset,
  );
  const [rowsPerBlock, setRowsPerBlock] = useState(
    initial?.rows_per_block ?? DEFAULT_LAYOUT_CONFIG.rows_per_block,
  );
  const [blockGapM, setBlockGapM] = useState(
    initial?.block_gap_m ?? DEFAULT_LAYOUT_CONFIG.block_gap_m,
  );
  const [siteBoundary, setSiteBoundary] = useState<BoundaryPoint[] | undefined>(
    initial?.boundary,
  );
  const [parcels, setParcels] = useState<Parcel[]>([]);
  const [restrictions, setRestrictions] = useState<BoundaryPoint[][]>([]);
  const [buildableGeoJson, setBuildableGeoJson] = useState<GeoJSON.GeoJSON | null>(null);
  const [buildableAreaHa, setBuildableAreaHa] = useState<number | null>(null);
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

  const enabledParcels = useMemo(
    () => parcels.filter((p) => p.enabled && p.coords.length >= 3),
    [parcels],
  );

  const parcelGroups = useMemo(() => {
    const order: string[] = [];
    const buckets = new Map<string, Parcel[]>();
    for (const p of parcels) {
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
  }, [parcels]);

  // Effective rings used for analysis: enabled KML parcels, else the drawn boundary.
  const effectiveRings: BoundaryPoint[][] = useMemo(() => {
    if (enabledParcels.length) return enabledParcels.map((p) => p.coords);
    if (siteBoundary && siteBoundary.length >= 3) return [siteBoundary];
    return [];
  }, [enabledParcels, siteBoundary]);

  const hasBoundary = effectiveRings.length > 0;

  function parseTrackerStringOptions() {
    const parsed = trackerStringOptions
      .split(/[,\s]+/)
      .map((v) => Number(v.trim()))
      .filter((v) => Number.isFinite(v) && v > 0);
    return parsed.length ? parsed : DEFAULT_LAYOUT_CONFIG.tracker_string_options;
  }

  const overlayParcels: OverlayParcel[] = useMemo(
    () => parcels.map((p) => ({ coords: p.coords, enabled: p.enabled })),
    [parcels],
  );

  function ringsToGeoJson(rings: BoundaryPoint[][]): GeoJSON.GeoJSON | null {
    const polys = rings
      .filter((r) => r.length >= 3)
      .map((r) => {
        const c = r.map((p) => [p.lon, p.lat]);
        c.push([r[0].lon, r[0].lat]);
        return [c];
      });
    if (!polys.length) return null;
    if (polys.length === 1) return { type: "Polygon", coordinates: polys[0] };
    return { type: "MultiPolygon", coordinates: polys };
  }

  function restrictionsToGeoJson(polys: BoundaryPoint[][]): GeoJSON.GeoJSON | null {
    const rings = polys
      .filter((r) => r.length >= 3)
      .map((r) => {
        const c = r.map((p) => [p.lon, p.lat]);
        c.push([r[0].lon, r[0].lat]);
        return c;
      });
    if (!rings.length) return null;
    return {
      type: "MultiPolygon",
      coordinates: rings.map((r) => [r]),
    };
  }

  function toProjectPayload() {
    return {
      name: projectName.trim() || "New project",
      center: { lat, lon },
      site_boundary_geojson: ringsToGeoJson(effectiveRings),
      restriction_polygons_geojson: restrictionsToGeoJson(restrictions),
      buildable_area_geojson: buildableGeoJson,
      land_use: landUse,
      mount_type: mountType,
      country: country.trim(),
      workflow: {
        area_ha: Number(areaHa),
        run_layout: false,
        buildable_area_ha: buildableAreaHa,
        module_h: moduleH,
        module_w: moduleW,
        module_wp: moduleWp,
        modules_per_string: modulesPerString,
        inter_string_gap_m: interStringGap,
        tracker_string_options: parseTrackerStringOptions(),
        max_tracker_length_m: maxTrackerLength,
        exclude_tracker_slope: excludeTrackerSlope,
        tracker_slope_limit_pct: trackerSlopeLimit,
        road_mode: roadMode,
        road_preset: roadPreset,
        rows_per_block: rowsPerBlock,
        block_gap_m: blockGapM,
      },
    };
  }

  function applyProjectRecord(row: any) {
    const payload = row?.project_data || {};
    const center = payload.center || {};
    if (typeof center.lat === "number" && typeof center.lon === "number") {
      applyPick(center.lat, center.lon);
    }
    setProjectName(payload.name || "New project");
    setCountry(payload.country || "");
    setLandUse((payload.land_use || "Standard") as LandUse);
    setMountType(payload.mount_type || "Fixed Tilt");
    if (payload.workflow?.area_ha) {
      setAreaHa(Number(payload.workflow.area_ha));
    }
    const wf = payload.workflow || {};
    if (typeof wf.module_h === "number") setModuleH(Number(wf.module_h));
    if (typeof wf.module_w === "number") setModuleW(Number(wf.module_w));
    if (typeof wf.module_wp === "number") setModuleWp(Number(wf.module_wp));
    if (typeof wf.modules_per_string === "number") {
      setModulesPerString(Number(wf.modules_per_string));
    }
    if (typeof wf.inter_string_gap_m === "number") {
      setInterStringGap(Number(wf.inter_string_gap_m));
    }
    if (Array.isArray(wf.tracker_string_options)) {
      setTrackerStringOptions(wf.tracker_string_options.join(","));
    }
    if (typeof wf.max_tracker_length_m === "number") {
      setMaxTrackerLength(Number(wf.max_tracker_length_m));
    }
    if (typeof wf.exclude_tracker_slope === "boolean") {
      setExcludeTrackerSlope(Boolean(wf.exclude_tracker_slope));
    }
    if (typeof wf.tracker_slope_limit_pct === "number") {
      setTrackerSlopeLimit(Number(wf.tracker_slope_limit_pct));
    }
    if (typeof wf.road_mode === "string") setRoadMode(wf.road_mode as RoadMode);
    if (typeof wf.road_preset === "string") setRoadPreset(wf.road_preset);
    if (typeof wf.rows_per_block === "number") setRowsPerBlock(Number(wf.rows_per_block));
    if (typeof wf.block_gap_m === "number") setBlockGapM(Number(wf.block_gap_m));
    setParcels([]);
    const site = payload.site_boundary_geojson;
    if (site?.type === "Polygon" && Array.isArray(site.coordinates?.[0])) {
      setSiteBoundary(
        site.coordinates[0]
          .slice(0, -1)
          .map((p: number[]) => ({ lon: Number(p[0]), lat: Number(p[1]) })),
      );
    } else if (site?.type === "MultiPolygon" && Array.isArray(site.coordinates)) {
      const rings: BoundaryPoint[][] = site.coordinates
        .map((poly: number[][][]) =>
          (poly?.[0] || []).slice(0, -1).map((p: number[]) => ({
            lon: Number(p[0]),
            lat: Number(p[1]),
          })),
        )
        .filter((r: BoundaryPoint[]) => r.length >= 3);
      if (rings.length > 1) {
        setSiteBoundary(undefined);
        setParcels(
          rings.map((coords, i) => ({
            id: `saved_${i}`,
            name: `Parcel ${i + 1}`,
            layer_group: "Parcels",
            area_ha: 0,
            coords,
            enabled: true,
          })),
        );
      } else {
        setSiteBoundary(rings[0]);
      }
    } else {
      setSiteBoundary(undefined);
    }
    const restr = payload.restriction_polygons_geojson;
    if (restr?.type === "MultiPolygon" && Array.isArray(restr.coordinates)) {
      setRestrictions(
        restr.coordinates
          .map((poly: number[][][]) =>
            (poly?.[0] || []).slice(0, -1).map((p: number[]) => ({
              lon: Number(p[0]),
              lat: Number(p[1]),
            })),
          )
          .filter((r: BoundaryPoint[]) => r.length >= 3),
      );
    } else {
      setRestrictions([]);
    }
    setBuildableGeoJson(payload.buildable_area_geojson || null);
    setBuildableAreaHa(
      typeof payload.workflow?.buildable_area_ha === "number"
        ? Number(payload.workflow.buildable_area_ha)
        : null,
    );
  }

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
        applyProjectRecord(rows[0]);
      }
    } catch {
      // Keep input form usable even if projects endpoint is not available.
    }
  }

  async function saveProjectDraft() {
    setSaving(true);
    try {
      const payload = toProjectPayload();
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
      applyProjectRecord(row);
      setHint("Project loaded.");
    } catch (err) {
      setHint(err instanceof Error ? err.message : "Project load failed");
    } finally {
      setBusy(false);
    }
  }

  function applyPick(newLat: number, newLon: number) {
    setLat(Number(newLat.toFixed(6)));
    setLon(Number(newLon.toFixed(6)));
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
    setHint("");
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
    if (!country && r.label) {
      const parts = r.label.split(",").map((s) => s.trim());
      if (parts.length) setCountry(parts[parts.length - 1]);
    }
    setSearchResults([]);
    setSearchQ(r.label);
    setHint("Location set from search.");
  }

  async function onKmlFile(file: File | null) {
    if (!file) return;
    setBusy(true);
    setHint("");
    try {
      const parsed = await parseBoundaryFile(token, file);
      const incoming: Parcel[] =
        parsed.parcels && parsed.parcels.length
          ? parsed.parcels.map((p) => ({
              id: p.id,
              name: p.name,
              layer_group: p.layer_group || "Other",
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
      // Fall back to enabling the largest parcel if the heuristic disabled all.
      if (!incoming.some((p) => p.enabled) && incoming.length) {
        const largest = incoming.reduce((a, b) => (b.area_ha > a.area_ha ? b : a));
        largest.enabled = true;
      }
      setParcels(incoming);
      setSiteBoundary(undefined);
      applyPick(parsed.lat, parsed.lon);
      if (!projectName || projectName === DEFAULTS.project_name) {
        setProjectName(parsed.name);
      }
      const enabledCount = incoming.filter((p) => p.enabled).length;
      setHint(
        `Loaded ${incoming.length} parcel${incoming.length === 1 ? "" : "s"} from KML/KMZ — ` +
          `${enabledCount} selected. Tick/untick parcels to include them in the analysis.`,
      );
    } catch (err) {
      setHint(err instanceof Error ? err.message : "KML upload failed");
    } finally {
      setBusy(false);
    }
  }

  function toggleParcel(id: string) {
    setParcels((prev) => prev.map((p) => (p.id === id ? { ...p, enabled: !p.enabled } : p)));
  }

  function removeParcel(id: string) {
    setParcels((prev) => prev.filter((p) => p.id !== id));
  }

  function setGroupEnabled(group: string, enabled: boolean) {
    setParcels((prev) =>
      prev.map((p) => ((p.layer_group || "Other") === group ? { ...p, enabled } : p)),
    );
  }

  function removeGroup(group: string) {
    setParcels((prev) => prev.filter((p) => (p.layer_group || "Other") !== group));
  }

  function toggleGroupCollapsed(group: string) {
    setCollapsedGroups((prev) => ({ ...prev, [group]: !prev[group] }));
  }

  function clearBoundary() {
    setSiteBoundary(undefined);
    setParcels([]);
    setRestrictions([]);
    setBuildableGeoJson(null);
    setBuildableAreaHa(null);
    setHint("Boundary cleared — using pin location only.");
  }

  useEffect(() => {
    void loadProjects(!initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep gross area in sync with the enabled KML parcels.
  useEffect(() => {
    if (!enabledParcels.length) return;
    const total = enabledParcels.reduce((sum, p) => sum + (p.area_ha || 0), 0);
    if (total > 0) setAreaHa(Number(total.toFixed(2)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabledParcels]);

  useEffect(() => {
    if (!hasBoundary) {
      setBuildableGeoJson(null);
      setBuildableAreaHa(null);
      return;
    }
    const siteGeoJson = ringsToGeoJson(effectiveRings);
    if (!siteGeoJson) return;
    const timer = window.setTimeout(async () => {
      try {
        const preview = await computeBuildableArea(token, {
          site_boundary_geojson: siteGeoJson,
          restriction_polygons_geojson: restrictionsToGeoJson(restrictions),
        });
        setBuildableGeoJson(preview.buildable_area_geojson);
        setBuildableAreaHa(preview.buildable_area_ha);
      } catch {
        setBuildableGeoJson(null);
        setBuildableAreaHa(null);
      }
    }, 250);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveRings, restrictions, token]);

  function submitNow() {
    void saveProjectDraft();
    const rings = effectiveRings;
    const primary = rings.length
      ? rings.reduce((a, b) => (b.length > a.length ? b : a))
      : undefined;
    onSubmit({
      project_name: projectName.trim() || "Site screening",
      lat,
      lon,
      area_ha: Number(areaHa),
      land_use: landUse,
      mount_type: mountType,
      country: country.trim(),
      boundary: primary,
      boundaries: rings.length ? rings : undefined,
      restriction_polygons: restrictions.length ? restrictions : undefined,
      run_layout: false,
      module_h: moduleH,
      module_w: moduleW,
      module_wp: moduleWp,
      modules_per_string: modulesPerString,
      inter_string_gap_m: interStringGap,
      tracker_string_options: parseTrackerStringOptions(),
      max_tracker_length_m: maxTrackerLength,
      exclude_tracker_slope: excludeTrackerSlope,
      tracker_slope_limit_pct: trackerSlopeLimit,
      road_mode: roadMode,
      road_preset: roadPreset,
      rows_per_block: roadMode === "manual" && roadPreset === "custom" ? rowsPerBlock : undefined,
      block_gap_m: roadMode === "manual" && roadPreset === "custom" ? blockGapM : undefined,
    });
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!hasBoundary) {
      setShowBoundaryModal(true);
      return;
    }
    submitNow();
  }

  return (
    <div className="workflow-page">
      <div className="page-intro">
        <h1>Project input</h1>
        <p>
          Upload a KML/KMZ or draw the site boundary, then run the unified workflow
          (screening → TopoIQ terrain → LayoutIQ → YieldIQ).
        </p>
      </div>

      <form className="card card-wide" onSubmit={handleSubmit}>
        <section className="form-section">
          <h2>Saved projects</h2>
          <div className="paste-row">
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
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </section>

        <section className="form-section">
          <h2>Project</h2>
          <div className="field">
            <label htmlFor="project">Project name</label>
            <input
              id="project"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
            />
          </div>
        </section>

        <section className="form-section">
          <h2>Site boundary</h2>

          <div className="field kml-upload-field">
            <label htmlFor="kml">Upload KML / KMZ boundary</label>
            <input
              id="kml"
              type="file"
              accept=".kml,.kmz"
              onChange={(e) => void onKmlFile(e.target.files?.[0] ?? null)}
            />
            <p className="hint">
              Upload a KML/KMZ to load all site parcels, or draw a boundary on the map below.
            </p>
          </div>

          {parcels.length > 0 ? (
            <div className="parcel-manager">
              <div className="parcel-manager-head">
                <strong>
                  Site parcels — {enabledParcels.length}/{parcels.length} selected
                </strong>
                <button
                  className="btn btn-ghost btn-sm"
                  type="button"
                  onClick={clearBoundary}
                >
                  Clear all
                </button>
              </div>
              <div className="parcel-groups">
                {parcelGroups.map((grp) => {
                  const collapsed = !!collapsedGroups[grp.group];
                  const allOn = grp.enabled === grp.total;
                  return (
                    <div
                      key={grp.group}
                      className={`parcel-group${grp.enabled === 0 ? " group-off" : ""}`}
                    >
                      <div className="parcel-group-head">
                        <input
                          type="checkbox"
                          checked={allOn}
                          ref={(el) => {
                            if (el) el.indeterminate = grp.enabled > 0 && !allOn;
                          }}
                          onChange={() => setGroupEnabled(grp.group, !allOn)}
                          aria-label={`Toggle ${grp.group}`}
                        />
                        <button
                          type="button"
                          className="parcel-group-toggle"
                          onClick={() => toggleGroupCollapsed(grp.group)}
                          aria-expanded={!collapsed}
                        >
                          <span className="parcel-caret">{collapsed ? "▸" : "▾"}</span>
                          <span className="parcel-group-name">{grp.group}</span>
                          <span className="parcel-group-meta">
                            {grp.enabled}/{grp.total} · {grp.area.toFixed(1)} ha
                          </span>
                        </button>
                        <button
                          className="parcel-remove"
                          type="button"
                          aria-label={`Remove group ${grp.group}`}
                          onClick={() => removeGroup(grp.group)}
                        >
                          ✕
                        </button>
                      </div>
                      {!collapsed ? (
                        <ul className="parcel-list">
                          {grp.items.map((p) => (
                            <li key={p.id} className={p.enabled ? "parcel-on" : "parcel-off"}>
                              <label className="parcel-check">
                                <input
                                  type="checkbox"
                                  checked={p.enabled}
                                  onChange={() => toggleParcel(p.id)}
                                />
                                <span className="parcel-name">{p.name}</span>
                                <span className="parcel-area">
                                  {p.area_ha > 0 ? `${p.area_ha} ha` : `${p.coords.length} pts`}
                                </span>
                              </label>
                              <button
                                className="parcel-remove"
                                type="button"
                                aria-label={`Remove ${p.name}`}
                                onClick={() => removeParcel(p.id)}
                              >
                                ✕
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}

          <div className="field">
            <label htmlFor="search">Search location</label>
            <div className="paste-row">
              <input
                id="search"
                value={searchQ}
                onChange={(e) => setSearchQ(e.target.value)}
                placeholder="Munich, Germany or project address"
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void runSearch();
                  }
                }}
              />
              <button className="btn btn-ghost" type="button" onClick={() => void runSearch()}>
                Search
              </button>
            </div>
            {searchResults.length > 0 ? (
              <ul className="search-results">
                {searchResults.map((r) => (
                  <li key={`${r.lat}-${r.lon}-${r.label}`}>
                    <button type="button" onClick={() => pickSearchResult(r)}>
                      {r.label}
                    </button>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>

          <div className="field">
            <label htmlFor="paste">Or paste coordinates / Google Maps link</label>
            <div className="paste-row">
              <input
                id="paste"
                value={coordPaste}
                onChange={(e) => setCoordPaste(e.target.value)}
                placeholder="48.1351, 11.5820"
              />
              <button className="btn btn-ghost" type="button" onClick={applyPaste}>
                Apply
              </button>
            </div>
          </div>

          <div className="paste-row">
            <select value={drawMode} onChange={(e) => setDrawMode(e.target.value as "site" | "restriction")}>
              <option value="site">Draw site boundary</option>
              <option value="restriction">Draw restriction polygon</option>
            </select>
          </div>
          <SiteMap
            lat={lat}
            lon={lon}
            siteBoundary={siteBoundary}
            restrictions={restrictions}
            overlayParcels={overlayParcels}
            buildableAreaGeoJson={buildableGeoJson}
            drawMode={drawMode}
            onPick={applyPick}
            onSiteBoundaryChange={setSiteBoundary}
            onRestrictionsChange={setRestrictions}
          />
          <p className="hint">Click map or drag pin to set site centre.</p>
          {buildableAreaHa != null ? (
            <p className="hint">
              Buildable area: <strong>{buildableAreaHa} ha</strong> (site minus restrictions).
            </p>
          ) : null}

          <div className="grid-2">
            <div className="field">
              <label htmlFor="lat">Latitude</label>
              <input
                id="lat"
                type="number"
                step="any"
                value={lat}
                onChange={(e) => setLat(Number(e.target.value))}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="lon">Longitude</label>
              <input
                id="lon"
                type="number"
                step="any"
                value={lon}
                onChange={(e) => setLon(Number(e.target.value))}
                required
              />
            </div>
          </div>
        </section>

        <section className="form-section">
          <h2>Site parameters</h2>
          <div className="grid-3">
            <div className="field">
              <label htmlFor="area">Gross area (ha)</label>
              <input
                id="area"
                type="number"
                step="any"
                min="0.1"
                value={areaHa}
                onChange={(e) => setAreaHa(Number(e.target.value))}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="country">Country</label>
              <input
                id="country"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="land">Land use</label>
              <select
                id="land"
                value={landUse}
                onChange={(e) => setLandUse(e.target.value as LandUse)}
              >
                <option value="Standard">Standard Ground Mount</option>
                <option value="Agri-PV">Agri-PV (Dual Use)</option>
              </select>
            </div>
          </div>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="mount">Mounting system (yield reference)</label>
              <select
                id="mount"
                value={mountType}
                onChange={(e) => setMountType(e.target.value)}
              >
                <option value="Fixed Tilt">Fixed Tilt</option>
                <option value="Single-Axis Tracker">Single-Axis Tracker</option>
              </select>
            </div>
          </div>
        </section>

        <details className="form-section layout-advanced">
          <summary>
            <h2>Module &amp; electrical (LayoutIQ)</h2>
          </summary>
          <p className="hint">
            Defaults: 550 Wp module, 28 modules/string, 500 mm between strings. Access roads:
            5 m N-S gap after every 2 tracker rows (no E-W roads).
          </p>
          <div className="grid-3">
            <div className="field">
              <label htmlFor="module-h">Module height (m)</label>
              <input
                id="module-h"
                type="number"
                step="0.001"
                min="1"
                value={moduleH}
                onChange={(e) => setModuleH(Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="module-w">Module width (m)</label>
              <input
                id="module-w"
                type="number"
                step="0.001"
                min="0.5"
                value={moduleW}
                onChange={(e) => setModuleW(Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="module-wp">Module power (Wp)</label>
              <input
                id="module-wp"
                type="number"
                step="5"
                min="200"
                max="1000"
                value={moduleWp}
                onChange={(e) => setModuleWp(Number(e.target.value))}
              />
            </div>
          </div>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="mps">Modules per string</label>
              <input
                id="mps"
                type="number"
                min="8"
                max="50"
                value={modulesPerString}
                onChange={(e) => setModulesPerString(Number(e.target.value))}
              />
            </div>
            <div className="field">
              <label htmlFor="string-gap">Gap between strings (m)</label>
              <input
                id="string-gap"
                type="number"
                step="0.05"
                min="0"
                max="2"
                value={interStringGap}
                onChange={(e) => setInterStringGap(Number(e.target.value))}
              />
            </div>
          </div>
          <div className="grid-2">
            <div className="field">
              <label htmlFor="tracker-strings">Tracker string options</label>
              <input
                id="tracker-strings"
                value={trackerStringOptions}
                onChange={(e) => setTrackerStringOptions(e.target.value)}
                placeholder="8,7,6,5"
              />
              <p className="hint">Allowed tracker units, e.g. 8S, 7S, 6S, 5S.</p>
            </div>
            <div className="field">
              <label htmlFor="max-tracker-length">Max tracker length (m)</label>
              <input
                id="max-tracker-length"
                type="number"
                step="1"
                min="20"
                max="500"
                value={maxTrackerLength}
                onChange={(e) => setMaxTrackerLength(Number(e.target.value))}
              />
              <p className="hint">Example: 260 m for 1P, 180 m for Agri-PV products.</p>
            </div>
          </div>
          <label className="checkbox-field layout-bifacial">
            <input
              type="checkbox"
              checked={excludeTrackerSlope}
              onChange={(e) => setExcludeTrackerSlope(e.target.checked)}
            />
            Exclude tracker placement where TopoIQ slope is above
          </label>
          <div className="field">
            <label htmlFor="tracker-slope-limit">Tracker slope limit (%)</label>
            <input
              id="tracker-slope-limit"
              type="number"
              step="0.5"
              min="0.5"
              max="30"
              value={trackerSlopeLimit}
              onChange={(e) => setTrackerSlopeLimit(Number(e.target.value))}
              disabled={!excludeTrackerSlope}
            />
          </div>
          <div className="layout-road-tabs">
            <div className="layout-road-tab-row">
              <button
                type="button"
                className={`btn btn-ghost btn-sm${roadMode === "auto" ? " active" : ""}`}
                onClick={() => {
                  setRoadMode("auto");
                  setRoadPreset("sat_auto");
                }}
              >
                Auto
              </button>
              <button
                type="button"
                className={`btn btn-ghost btn-sm${roadMode === "manual" || roadMode === "off" ? " active" : ""}`}
                onClick={() => setRoadMode("manual")}
              >
                Presets
              </button>
            </div>
            {roadMode === "auto" ? (
              <p className="hint sidebar-hint">
                Two tracker rows, then 5 m N-S access gap (no E-W roads).
              </p>
            ) : (
              <div className="field">
                <label htmlFor="road-preset">Access road preset</label>
                <select
                  id="road-preset"
                  value={roadPreset}
                  onChange={(e) => {
                    const id = e.target.value;
                    setRoadPreset(id);
                    if (id === "no_roads") setRoadMode("off");
                    else if (id !== "custom") setRoadMode("manual");
                    else setRoadMode("manual");
                  }}
                >
                  {ROAD_PRESETS.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.label}
                    </option>
                  ))}
                  <option value="custom">Custom rows + gap</option>
                </select>
              </div>
            )}
            {(roadMode === "manual" || roadMode === "off") && roadPreset === "custom" ? (
              <div className="grid-2">
                <div className="field">
                  <label htmlFor="rows-block">Rows per block</label>
                  <input
                    id="rows-block"
                    type="number"
                    min="1"
                    max="10"
                    value={rowsPerBlock}
                    onChange={(e) => setRowsPerBlock(Number(e.target.value))}
                  />
                </div>
                <div className="field">
                  <label htmlFor="block-gap">N-S block gap (m)</label>
                  <input
                    id="block-gap"
                    type="number"
                    step="0.5"
                    min="0"
                    max="20"
                    value={blockGapM}
                    onChange={(e) => setBlockGapM(Number(e.target.value))}
                  />
                </div>
              </div>
            ) : null}
          </div>
        </details>

        {hint ? <p className="hint hint-banner">{hint}</p> : null}

        <div className="form-actions">
          <button className="btn btn-primary btn-lg" type="submit" disabled={busy}>
            Continue to screening →
          </button>
        </div>
      </form>

      {showBoundaryModal ? (
        <div className="modal-overlay" role="dialog" aria-modal="true">
          <div className="modal-card">
            <h2>No site boundary yet</h2>
            <p>
              Without a site boundary you can run <strong>screening only</strong>. TopoIQ
              terrain analysis and LayoutIQ both need a drawn or uploaded boundary.
            </p>
            <p>Draw a polygon on the map, upload a KML/KMZ, or continue with screening only.</p>
            <div className="modal-actions">
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => setShowBoundaryModal(false)}
              >
                Draw / upload boundary
              </button>
              <button
                className="btn btn-primary"
                type="button"
                onClick={() => {
                  setShowBoundaryModal(false);
                  submitNow();
                }}
              >
                Continue with screening only
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
