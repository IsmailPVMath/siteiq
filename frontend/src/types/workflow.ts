import type * as GeoJSON from "geojson";

export type WorkflowStep = "input" | "processing" | "output";

export const WORKFLOW_STEPS: { id: WorkflowStep; label: string }[] = [
  { id: "input", label: "Project input" },
  { id: "processing", label: "Screening" },
  { id: "output", label: "Results" },
];

/** Unified workflow — screening excludes terrain (TopoIQ only). */
export const PROCESSING_STAGES = [
  "Solar resource (PVGIS)",
  "Grid proximity (OSM)",
  "Flood screening",
  "Regulatory guidance",
  "Capacity estimate",
] as const;

export interface WorkflowScreenRequest {
  project_name: string;
  lat: number;
  lon: number;
  area_ha: number;
  land_use: "Standard" | "Agri-PV";
  mount_type: string;
  country: string;
}

export interface WorkflowScreenResponse {
  success: boolean;
  project_name: string;
  coordinates: { lat: number; lon: number };
  solar: Record<string, unknown>;
  flood: Record<string, unknown>;
  grid: Record<string, unknown>;
  regulatory: Record<string, unknown>;
  capacity: Record<string, unknown>;
  score_components: Record<string, number>;
  terrain_note: string;
  errors: string[];
}

export interface WorkflowScoreResponse {
  pvmath_score: number;
  verdict: string;
  components: Record<string, number>;
  verdict_detail: string;
}

export interface LayoutMatrixConfig {
  config_key: string;
  label: string;
  n_portrait: number;
  pitch_m?: number;
  success: boolean;
  error?: string;
  layout?: {
    total_modules: number;
    total_rows: number;
    area_ha: number;
    dc_kwp: number;
    mw_per_ha?: number | null;
  };
  bom?: Record<string, string>;
}

export interface WorkflowLayoutMatrixResponse {
  configs: LayoutMatrixConfig[];
}

export type LayoutOptimizationMode = "high_energy" | "balanced" | "land_optimized" | "custom";
export type LayoutLandCost = "auto" | "cheap" | "balanced" | "expensive";

export interface WorkflowLayoutSweepRequest {
  boundary?: { lat: number; lon: number }[];
  boundaries?: { lat: number; lon: number }[][];
  include_bom?: boolean;
  optimization_mode?: LayoutOptimizationMode;
  land_cost?: LayoutLandCost;
  country?: string;
  lat?: number;
  bifacial?: boolean;
  custom_gcr?: number;
  custom_pitch_m?: number;
}

export interface GcrGuidanceEntry {
  config_key: string;
  recommended_gcr: number;
  recommended_pitch_m: number;
  gcr_typical_min: number;
  gcr_typical_max: number;
  pitch_m_min: number;
  pitch_m_max: number;
  balanced_default_gcr: number;
  land_cost: string;
}

export interface LayoutSweepStrategy {
  optimization_mode: LayoutOptimizationMode;
  land_cost_input: LayoutLandCost;
  land_cost_resolved: string;
  country: string;
  latitude: number | null;
  bifacial: boolean;
  mode_label: string;
  land_cost_label: string;
  note: string;
}

export interface WorkflowLayoutSweepResponse {
  rows: LayoutSweepRow[];
  best_by_config: Record<string, LayoutSweepRow>;
  recommended_by_config: Record<string, LayoutSweepRow>;
  gcr_guidance: Record<string, GcrGuidanceEntry>;
  strategy: LayoutSweepStrategy;
  config_count: number;
  row_count: number;
}

export interface LayoutSweepRow {
  config_key: string;
  label: string;
  mount_type: string;
  n_portrait: number;
  pitch_m: number;
  gcr: number;
  success: boolean;
  error?: string;
  total_modules?: number;
  total_rows?: number;
  area_ha?: number;
  dc_kwp?: number;
  mw_per_ha?: number | null;
  is_recommended?: boolean;
  bom?: Record<string, string>;
}

export interface WorkflowLayoutDetailRequest {
  project_name?: string;
  boundary?: { lat: number; lon: number }[];
  boundaries?: { lat: number; lon: number }[][];
  config_key: string;
  pitch_m: number;
  module_h?: number;
  module_w?: number;
  module_wp?: number;
  setback_m?: number;
  azimuth?: number;
}

export interface WorkflowLayoutDetailResponse {
  config_key: string;
  label: string;
  mount_type: string;
  n_portrait: number;
  pitch_m: number;
  gcr: number;
  total_modules: number;
  total_rows: number;
  area_ha: number;
  dc_kwp: number;
  ref_lat: number;
  ref_lon: number;
  geojson: GeoJSON.GeoJSON;
}

export interface WorkflowTerrainMeshRequest {
  boundary?: { lat: number; lon: number }[];
  boundaries?: { lat: number; lon: number }[][];
  grid_m?: number;
  max_vertices?: number;
}

export interface WorkflowTerrainMeshResponse {
  vertices: number[][];
  faces: number[][];
  elevations: number[];
  slopes: number[];
  origin: { lat: number; lon: number; elevation_m: number };
  bbox: Record<string, number>;
  grid_m_used: number;
  terrain_source_used: string;
  z_min: number;
  z_max: number;
  slope_mean: number;
}

export interface WorkflowPvmathReportRequest {
  project_name: string;
  country?: string;
  lat?: number;
  lon?: number;
  land_use?: string;
  screening?: Record<string, unknown>;
  topo?: Record<string, unknown> | null;
  score?: Record<string, unknown> | null;
  layout_row?: LayoutSweepRow | null;
  yield_result?: Record<string, unknown> | null;
  selected_yield_mwh?: number | null;
}

export interface WorkflowProjectPackageRequest extends WorkflowPvmathReportRequest {
  boundaries?: { lat: number; lon: number }[][];
  boundary?: { lat: number; lon: number }[];
  config_key: string;
  pitch_m: number;
}
