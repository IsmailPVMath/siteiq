import type * as GeoJSON from "geojson";
import type { BoundaryPoint, GateAnalyzeRequest } from "../types/gate";
import { DEFAULT_LAYOUT_CONFIG } from "../types/layoutConfig";
import type {
  InputMethod,
  ProjectSetupDraft,
  SetupValidationIssue,
  SetupValidationResult,
  SetupParcel,
  WorkflowReadiness,
} from "../types/projectSetup";
import { PROJECT_SETUP_SCHEMA_VERSION } from "../types/projectSetup";
import type { ProjectPayload, ProjectRecord } from "./api";

export const DEFAULT_DRAFT: ProjectSetupDraft = {
  schema_version: PROJECT_SETUP_SCHEMA_VERSION,
  project_info: { name: "New project", client: "", notes: "" },
  location: { country: "Germany", state: "", city: "", lat: 48.1351, lon: 11.582 },
  geometry: {
    parcels: [],
    restrictions: [],
    buildable_area_geojson: null,
    buildable_area_ha: null,
    gross_area_ha: 25,
  },
  design_basis: {
    land_use: "Standard",
    mount_type: "Fixed Tilt",
    target_capacity_mwp: null,
    target_cod: "",
    currency: "EUR",
    coordinate_system: "WGS84",
    engineering_standard: "",
    design_standard: "",
    units: "metric",
  },
  assumptions: { ...DEFAULT_LAYOUT_CONFIG },
  input_method: "map",
  workflow_state: {
    readiness: emptyReadiness(),
  },
};

function emptyReadiness(): WorkflowReadiness {
  return {
    has_boundary: false,
    can_run_siteiq: false,
    can_run_terrainiq: false,
    can_run_layoutiq: false,
    can_run_yieldiq: false,
  };
}

export function effectiveRings(draft: ProjectSetupDraft): BoundaryPoint[][] {
  const enabled = draft.geometry.parcels.filter((p) => p.enabled && p.coords.length >= 3);
  if (enabled.length) return enabled.map((p) => p.coords);
  if (draft.geometry.site_boundary && draft.geometry.site_boundary.length >= 3) {
    return [draft.geometry.site_boundary];
  }
  return [];
}

export function ringsToGeoJson(rings: BoundaryPoint[][]): GeoJSON.GeoJSON | null {
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

export function restrictionsToGeoJson(polys: BoundaryPoint[][]): GeoJSON.GeoJSON | null {
  const rings = polys
    .filter((r) => r.length >= 3)
    .map((r) => {
      const c = r.map((p) => [p.lon, p.lat]);
      c.push([r[0].lon, r[0].lat]);
      return c;
    });
  if (!rings.length) return null;
  return { type: "MultiPolygon", coordinates: rings.map((r) => [r]) };
}

export function parseTrackerStringOptions(raw: string): number[] {
  const parsed = raw
    .split(/[,\s]+/)
    .map((v) => Number(v.trim()))
    .filter((v) => Number.isFinite(v) && v > 0);
  return parsed.length ? parsed : [...DEFAULT_LAYOUT_CONFIG.tracker_string_options];
}

export function validateDraft(draft: ProjectSetupDraft): SetupValidationResult {
  const issues: SetupValidationIssue[] = [];
  const name = draft.project_info.name.trim();
  if (!name) {
    issues.push({ level: "error", field: "name", message: "Project name is required." });
  }
  if (!draft.location.country.trim()) {
    issues.push({
      level: "warning",
      field: "country",
      message: "Country not set — will infer from location if possible.",
    });
  }
  const { lat, lon } = draft.location;
  if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
    issues.push({ level: "error", field: "location", message: "Valid coordinates are required." });
  } else if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
    issues.push({ level: "error", field: "location", message: "Coordinates are out of range." });
  }
  if (draft.geometry.gross_area_ha <= 0) {
    issues.push({ level: "error", field: "area_ha", message: "Gross area must be positive." });
  } else if (draft.geometry.gross_area_ha > 100_000) {
    issues.push({
      level: "warning",
      field: "area_ha",
      message: "Project area is unusually large — verify boundary.",
    });
  } else if (draft.geometry.gross_area_ha < 0.1) {
    issues.push({
      level: "warning",
      field: "area_ha",
      message: "Project area is very small — verify boundary.",
    });
  }

  const rings = effectiveRings(draft);
  const hasBoundary = rings.length > 0;
  if (!hasBoundary) {
    issues.push({
      level: "warning",
      field: "boundary",
      message:
        "No site boundary — only SiteIQ screening will run. TerrainIQ, LayoutIQ, and YieldIQ need a boundary.",
    });
  }

  const readiness: WorkflowReadiness = {
    has_boundary: hasBoundary,
    can_run_siteiq: Boolean(name && Number.isFinite(lat) && Number.isFinite(lon)),
    can_run_terrainiq: hasBoundary,
    can_run_layoutiq: hasBoundary,
    can_run_yieldiq: hasBoundary,
  };
  const modules_to_run = ["SiteIQ"];
  if (hasBoundary) modules_to_run.push("TerrainIQ", "LayoutIQ", "YieldIQ");

  return {
    valid: !issues.some((i) => i.level === "error"),
    issues,
    readiness,
    modules_to_run,
  };
}

export function draftToProjectPayload(draft: ProjectSetupDraft): ProjectPayload {
  const rings = effectiveRings(draft);
  const a = draft.assumptions;
  return {
    name: draft.project_info.name.trim() || "New project",
    center: { lat: draft.location.lat, lon: draft.location.lon },
    site_boundary_geojson: ringsToGeoJson(rings),
    restriction_polygons_geojson: restrictionsToGeoJson(draft.geometry.restrictions),
    buildable_area_geojson: draft.geometry.buildable_area_geojson,
    land_use: draft.design_basis.land_use,
    mount_type: draft.design_basis.mount_type,
    country: draft.location.country.trim(),
    workflow: {
      schema_version: PROJECT_SETUP_SCHEMA_VERSION,
      area_ha: draft.geometry.gross_area_ha,
      buildable_area_ha: draft.geometry.buildable_area_ha,
      client: draft.project_info.client,
      notes: draft.project_info.notes,
      state: draft.location.state,
      city: draft.location.city,
      target_capacity_mwp: draft.design_basis.target_capacity_mwp,
      target_cod: draft.design_basis.target_cod,
      currency: draft.design_basis.currency,
      coordinate_system: draft.design_basis.coordinate_system,
      engineering_standard: draft.design_basis.engineering_standard,
      design_standard: draft.design_basis.design_standard,
      units: draft.design_basis.units,
      input_method: draft.input_method,
      module_h: a.module_h,
      module_w: a.module_w,
      module_wp: a.module_wp,
      modules_per_string: a.modules_per_string,
      inter_string_gap_m: a.inter_string_gap_m,
      tracker_string_options: a.tracker_string_options,
      max_tracker_length_m: a.max_tracker_length_m,
      exclude_tracker_slope: a.exclude_tracker_slope,
      tracker_slope_limit_pct: a.tracker_slope_limit_pct,
      road_mode: a.road_mode,
      road_preset: a.road_preset,
      rows_per_block: a.rows_per_block,
      block_gap_m: a.block_gap_m,
    },
  };
}

export function draftToGateRequest(draft: ProjectSetupDraft): GateAnalyzeRequest {
  const rings = effectiveRings(draft);
  const primary = rings.length
    ? rings.reduce((a, b) => (b.length > a.length ? b : a))
    : undefined;
  const a = draft.assumptions;
  return {
    project_name: draft.project_info.name.trim() || "Site screening",
    lat: draft.location.lat,
    lon: draft.location.lon,
    area_ha: draft.geometry.gross_area_ha,
    land_use: draft.design_basis.land_use,
    mount_type: draft.design_basis.mount_type,
    country: draft.location.country.trim(),
    boundary: primary,
    boundaries: rings.length ? rings : undefined,
    restriction_polygons: draft.geometry.restrictions.length
      ? draft.geometry.restrictions
      : undefined,
    run_layout: false,
    module_h: a.module_h,
    module_w: a.module_w,
    module_wp: a.module_wp,
    modules_per_string: a.modules_per_string,
    inter_string_gap_m: a.inter_string_gap_m,
    tracker_string_options: a.tracker_string_options,
    max_tracker_length_m: a.max_tracker_length_m,
    exclude_tracker_slope: a.exclude_tracker_slope,
    tracker_slope_limit_pct: a.tracker_slope_limit_pct,
    road_mode: a.road_mode,
    road_preset: a.road_preset,
    rows_per_block: a.road_mode === "manual" && a.road_preset === "custom" ? a.rows_per_block : undefined,
    block_gap_m: a.road_mode === "manual" && a.road_preset === "custom" ? a.block_gap_m : undefined,
  };
}

export function gateRequestToDraft(initial: Partial<GateAnalyzeRequest>): ProjectSetupDraft {
  const d = structuredClone(DEFAULT_DRAFT);
  if (initial.project_name) d.project_info.name = initial.project_name;
  if (initial.lat != null) d.location.lat = initial.lat;
  if (initial.lon != null) d.location.lon = initial.lon;
  if (initial.country) d.location.country = initial.country;
  if (initial.area_ha != null) d.geometry.gross_area_ha = initial.area_ha;
  if (initial.land_use) d.design_basis.land_use = initial.land_use;
  if (initial.mount_type) d.design_basis.mount_type = initial.mount_type;
  if (initial.boundary?.length) {
    d.geometry.site_boundary = initial.boundary;
    d.input_method = "map";
  }
  if (initial.module_h != null) d.assumptions.module_h = initial.module_h;
  if (initial.module_w != null) d.assumptions.module_w = initial.module_w;
  if (initial.module_wp != null) d.assumptions.module_wp = initial.module_wp;
  if (initial.modules_per_string != null) d.assumptions.modules_per_string = initial.modules_per_string;
  if (initial.inter_string_gap_m != null) d.assumptions.inter_string_gap_m = initial.inter_string_gap_m;
  if (initial.tracker_string_options) d.assumptions.tracker_string_options = initial.tracker_string_options;
  if (initial.max_tracker_length_m != null) d.assumptions.max_tracker_length_m = initial.max_tracker_length_m;
  if (initial.exclude_tracker_slope != null) d.assumptions.exclude_tracker_slope = initial.exclude_tracker_slope;
  if (initial.tracker_slope_limit_pct != null) d.assumptions.tracker_slope_limit_pct = initial.tracker_slope_limit_pct;
  if (initial.road_mode) d.assumptions.road_mode = initial.road_mode;
  if (initial.road_preset) d.assumptions.road_preset = initial.road_preset;
  if (initial.restriction_polygons) d.geometry.restrictions = initial.restriction_polygons;
  const v = validateDraft(d);
  d.workflow_state.readiness = v.readiness;
  return d;
}

export function projectRecordToDraft(row: ProjectRecord): ProjectSetupDraft {
  const p = row.project_data as ProjectPayload & Record<string, unknown>;
  const wf = (p.workflow || {}) as Record<string, unknown>;
  const d = structuredClone(DEFAULT_DRAFT);
  d.project_info.name = p.name || "New project";
  d.project_info.client = String(wf.client || "");
  d.project_info.notes = String(wf.notes || "");
  d.location.country = p.country || "";
  d.location.state = String(wf.state || "");
  d.location.city = String(wf.city || "");
  d.location.lat = p.center?.lat ?? d.location.lat;
  d.location.lon = p.center?.lon ?? d.location.lon;
  d.geometry.gross_area_ha = Number(wf.area_ha ?? d.geometry.gross_area_ha);
  d.geometry.buildable_area_ha =
    typeof wf.buildable_area_ha === "number" ? wf.buildable_area_ha : null;
  d.geometry.buildable_area_geojson = p.buildable_area_geojson ?? null;
  d.design_basis.land_use = (p.land_use as "Standard" | "Agri-PV") || "Standard";
  d.design_basis.mount_type = p.mount_type || "Fixed Tilt";
  if (wf.target_capacity_mwp != null) d.design_basis.target_capacity_mwp = Number(wf.target_capacity_mwp);
  d.design_basis.target_cod = String(wf.target_cod || "");
  d.design_basis.currency = String(wf.currency || "EUR");
  d.design_basis.coordinate_system = String(wf.coordinate_system || "WGS84");
  d.design_basis.engineering_standard = String(wf.engineering_standard || "");
  d.design_basis.design_standard = String(wf.design_standard || "");
  d.design_basis.units = (wf.units as "metric" | "imperial") || "metric";
  if (wf.input_method) d.input_method = wf.input_method as InputMethod;

  const site = p.site_boundary_geojson;
  if (site?.type === "Polygon" && Array.isArray((site as GeoJSON.Polygon).coordinates?.[0])) {
    const ring = (site as GeoJSON.Polygon).coordinates[0].slice(0, -1);
    d.geometry.site_boundary = ring.map(([lon, lat]) => ({ lon: Number(lon), lat: Number(lat) }));
  }

  if (typeof wf.module_h === "number") d.assumptions.module_h = wf.module_h;
  if (typeof wf.module_w === "number") d.assumptions.module_w = wf.module_w;
  if (typeof wf.module_wp === "number") d.assumptions.module_wp = wf.module_wp;
  if (typeof wf.modules_per_string === "number") d.assumptions.modules_per_string = wf.modules_per_string;
  if (typeof wf.inter_string_gap_m === "number") d.assumptions.inter_string_gap_m = wf.inter_string_gap_m;
  if (Array.isArray(wf.tracker_string_options)) d.assumptions.tracker_string_options = wf.tracker_string_options as number[];
  if (typeof wf.max_tracker_length_m === "number") d.assumptions.max_tracker_length_m = wf.max_tracker_length_m;
  if (typeof wf.exclude_tracker_slope === "boolean") d.assumptions.exclude_tracker_slope = wf.exclude_tracker_slope;
  if (typeof wf.tracker_slope_limit_pct === "number") d.assumptions.tracker_slope_limit_pct = wf.tracker_slope_limit_pct;
  if (typeof wf.road_mode === "string") d.assumptions.road_mode = wf.road_mode as typeof d.assumptions.road_mode;
  if (typeof wf.road_preset === "string") d.assumptions.road_preset = wf.road_preset;
  if (typeof wf.rows_per_block === "number") d.assumptions.rows_per_block = wf.rows_per_block;
  if (typeof wf.block_gap_m === "number") d.assumptions.block_gap_m = wf.block_gap_m;

  const v = validateDraft(d);
  d.workflow_state.readiness = v.readiness;
  return d;
}

/** Parse GeoJSON file client-side into parcels. */
export function geoJsonToParcels(geo: GeoJSON.GeoJSON, baseName: string): SetupParcel[] {
  const polys: BoundaryPoint[][] = [];
  function addRing(ring: number[][]) {
    const pts = ring.slice(0, -1).map(([lon, lat]) => ({ lon: Number(lon), lat: Number(lat) }));
    if (pts.length >= 3) polys.push(pts);
  }
  if (geo.type === "Polygon") {
    addRing(geo.coordinates[0] as number[][]);
  } else if (geo.type === "MultiPolygon") {
    for (const poly of geo.coordinates) addRing(poly[0] as number[][]);
  } else if (geo.type === "Feature") {
    return geoJsonToParcels(geo.geometry as GeoJSON.GeoJSON, baseName);
  } else if (geo.type === "FeatureCollection") {
    const out: SetupParcel[] = [];
    geo.features.forEach((f, i) => {
      out.push(...geoJsonToParcels(f.geometry as GeoJSON.GeoJSON, f.properties?.name || `Parcel ${i + 1}`));
    });
    return out;
  }
  return polys.map((coords, i) => ({
    id: `geo_${i}`,
    name: polys.length === 1 ? baseName : `${baseName} ${i + 1}`,
    layer_group: "GeoJSON",
    area_ha: 0,
    coords,
    enabled: true,
  }));
}

export type DraftAction =
  | { type: "replace"; draft: ProjectSetupDraft }
  | { type: "patch"; patch: Partial<ProjectSetupDraft> }
  | { type: "set_info"; project_info: Partial<ProjectSetupDraft["project_info"]> }
  | { type: "set_location"; location: Partial<ProjectSetupDraft["location"]> }
  | { type: "set_design"; design_basis: Partial<ProjectSetupDraft["design_basis"]> }
  | { type: "set_assumptions"; assumptions: Partial<ProjectSetupDraft["assumptions"]> }
  | { type: "set_input_method"; input_method: InputMethod }
  | { type: "set_parcels"; parcels: SetupParcel[] }
  | { type: "set_site_boundary"; site_boundary?: BoundaryPoint[] }
  | { type: "set_restrictions"; restrictions: BoundaryPoint[][] }
  | { type: "set_buildable"; buildable_area_geojson: GeoJSON.GeoJSON | null; buildable_area_ha: number | null }
  | { type: "set_gross_area"; gross_area_ha: number };

export function draftReducer(state: ProjectSetupDraft, action: DraftAction): ProjectSetupDraft {
  let next: ProjectSetupDraft;
  switch (action.type) {
    case "replace":
      next = action.draft;
      break;
    case "patch":
      next = { ...state, ...action.patch };
      break;
    case "set_info":
      next = { ...state, project_info: { ...state.project_info, ...action.project_info } };
      break;
    case "set_location":
      next = { ...state, location: { ...state.location, ...action.location } };
      break;
    case "set_design":
      next = { ...state, design_basis: { ...state.design_basis, ...action.design_basis } };
      break;
    case "set_assumptions":
      next = { ...state, assumptions: { ...state.assumptions, ...action.assumptions } };
      break;
    case "set_input_method":
      next = { ...state, input_method: action.input_method };
      break;
    case "set_parcels":
      next = { ...state, geometry: { ...state.geometry, parcels: action.parcels, site_boundary: undefined } };
      break;
    case "set_site_boundary":
      next = {
        ...state,
        geometry: { ...state.geometry, site_boundary: action.site_boundary, parcels: [] },
      };
      break;
    case "set_restrictions":
      next = { ...state, geometry: { ...state.geometry, restrictions: action.restrictions } };
      break;
    case "set_buildable":
      next = {
        ...state,
        geometry: {
          ...state.geometry,
          buildable_area_geojson: action.buildable_area_geojson,
          buildable_area_ha: action.buildable_area_ha,
        },
      };
      break;
    case "set_gross_area":
      next = { ...state, geometry: { ...state.geometry, gross_area_ha: action.gross_area_ha } };
      break;
    default:
      next = state;
  }
  const v = validateDraft(next);
  return { ...next, workflow_state: { readiness: v.readiness } };
}
