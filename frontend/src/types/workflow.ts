import type * as GeoJSON from "geojson";
import type { LayoutElectricalConfig, RowAlignment } from "./layoutConfig";

export type WorkflowStep = "input" | "processing" | "output" | "projects";

/** Connected pipeline visible across the preliminary study workflow. */
export type PipelineStage = "setup" | "siteiq" | "terrainiq" | "layoutiq" | "yieldiq";

export interface PipelineModule {
  id: PipelineStage;
  label: string;
  future?: boolean;
}

export const PIPELINE_MODULES: PipelineModule[] = [
  { id: "setup", label: "Project setup" },
  { id: "siteiq", label: "SiteIQ" },
  { id: "terrainiq", label: "TerrainIQ" },
  { id: "layoutiq", label: "LayoutIQ" },
  { id: "yieldiq", label: "YieldIQ" },
];

export type OutputModuleStage = "screen" | "topo" | "layout" | "yield";

export function pipelineFromOutputModule(stage: OutputModuleStage): PipelineStage {
  const map: Record<OutputModuleStage, PipelineStage> = {
    screen: "siteiq",
    topo: "terrainiq",
    layout: "layoutiq",
    yield: "yieldiq",
  };
  return map[stage];
}

export function outputModuleFromPipeline(stage: PipelineStage): OutputModuleStage | null {
  const map: Partial<Record<PipelineStage, OutputModuleStage>> = {
    siteiq: "screen",
    terrainiq: "topo",
    layoutiq: "layout",
    yieldiq: "yield",
  };
  return map[stage] ?? null;
}

/** @deprecated Use WorkflowPipeline — kept for legacy references */
export const WORKFLOW_STEPS: { id: WorkflowStep; label: string }[] = [
  { id: "input", label: "Project input" },
  { id: "processing", label: "Screening" },
  { id: "output", label: "Results" },
];

/** Unified workflow — screening excludes terrain (TerrainIQ only). */
export const PROCESSING_STAGES = [
  "Solar resource (PVGIS)",
  "Grid proximity (OSM)",
  "Flood screening",
  "Regulatory guidance",
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

export interface WorkflowLayoutSweepRequest extends LayoutElectricalConfig {
  boundary?: { lat: number; lon: number }[];
  boundaries?: { lat: number; lon: number }[][];
  restriction_polygons?: { lat: number; lon: number }[][];
  restriction_geojson?: GeoJSON.GeoJSON;
  include_bom?: boolean;
  optimization_mode?: LayoutOptimizationMode;
  land_cost?: LayoutLandCost;
  country?: string;
  lat?: number;
  bifacial?: boolean;
  custom_gcr?: number;
  custom_pitch_m?: number;
  mount_filter?: "all" | "fixed" | "sat";
  portrait_filter?: number[];
  row_alignment?: RowAlignment;
  azimuth?: number;
  allow_partial_strings?: boolean;
  ignore_soft_constraints?: boolean;
  constraint_layers?: Record<string, GeoJSON.FeatureCollection>;
  setbacks_m?: Record<string, number>;
  prune_isolated_blocks?: boolean;
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
  layout_params?: Record<string, unknown>;
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
  dc_mwp?: number;
  mw_per_ha?: number | null;
  is_recommended?: boolean;
  bom?: Record<string, string>;
}

export interface WorkflowLayoutDetailRequest extends LayoutElectricalConfig {
  project_name?: string;
  boundary?: { lat: number; lon: number }[];
  boundaries?: { lat: number; lon: number }[][];
  restriction_polygons?: { lat: number; lon: number }[][];
  restriction_geojson?: GeoJSON.GeoJSON;
  config_key: string;
  pitch_m: number;
  setback_m?: number;
  azimuth?: number;
  ignore_soft_constraints?: boolean;
  constraint_layers?: Record<string, GeoJSON.FeatureCollection>;
  setbacks_m?: Record<string, number>;
  prune_isolated_blocks?: boolean;
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
  total_strings?: number;
  total_tracker_units?: number;
  area_ha: number;
  dc_kwp: number;
  dc_mwp?: number;
  mw_per_ha?: number | null;
  ref_lat: number;
  ref_lon: number;
  geojson: GeoJSON.GeoJSON;
}

export interface WorkflowTerrainMeshRequest {
  boundary?: { lat: number; lon: number }[];
  boundaries?: { lat: number; lon: number }[][];
  grid_m?: number;
  max_vertices?: number;
  mask_geojson?: GeoJSON.GeoJSON | null;
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
  mount_type?: string;
  area_ha?: number;
  boundary?: { lat: number; lon: number }[];
  boundaries?: { lat: number; lon: number }[][];
  screening?: Record<string, unknown>;
  topo?: Record<string, unknown> | null;
  score?: Record<string, unknown> | null;
  layout_row?: LayoutSweepRow | null;
  yield_result?: Record<string, unknown> | null;
  selected_yield_mwh?: number | null;
  selected_config_key?: string | null;
  selected_dc_kwp?: number | null;
  location_label?: string;
  drawn_by?: string;
  revision?: string;
}

export interface WorkflowProjectPackageRequest extends WorkflowPvmathReportRequest, LayoutElectricalConfig {
  boundaries?: { lat: number; lon: number }[][];
  boundary?: { lat: number; lon: number }[];
  restriction_polygons?: { lat: number; lon: number }[][];
  restriction_geojson?: GeoJSON.GeoJSON;
  constraint_layers?: Record<string, GeoJSON.FeatureCollection>;
  config_key: string;
  pitch_m: number;
  allow_partial_strings?: boolean;
  row_alignment?: "horizontal" | "boundary";
  prune_isolated_blocks?: boolean;
  ignore_soft_constraints?: boolean;
  setbacks_m?: Record<string, number>;
  include_terrain?: boolean;
  topo_grid_m?: number;
  topo_allow_coarsen?: boolean;
  contour_minor?: number;
  contour_major?: number;
  mask_geojson?: GeoJSON.GeoJSON;
}

export interface ConstraintSummaryItem {
  category: string;
  label: string;
  feature_count: number;
  setback_m: number;
  excluded_ha: number;
  style: Record<string, string>;
}

export interface WorkflowGisAnalysisRequest {
  boundary?: { lat: number; lon: number }[];
  boundaries?: { lat: number; lon: number }[][];
  restriction_polygons_geojson?: GeoJSON.GeoJSON | null;
  setbacks_m?: Record<string, number>;
  constraint_layers?: Record<string, GeoJSON.FeatureCollection>;
  include_grid?: boolean;
}

export interface WorkflowGisAnalysisResponse {
  success: boolean;
  error?: string;
  coordinates?: { lat: number; lon: number };
  site_area_ha: number;
  buildable_area_ha: number;
  buildable_pct: number;
  site_boundary_geojson?: GeoJSON.GeoJSON | null;
  buildable_area_geojson?: GeoJSON.GeoJSON | null;
  excluded_area_geojson?: GeoJSON.GeoJSON | null;
  constraint_layers: Record<string, GeoJSON.FeatureCollection>;
  layer_styles: Record<string, { color: string; fillColor: string }>;
  constraint_summary: ConstraintSummaryItem[];
  feature_counts: Record<string, number>;
  setbacks_m: Record<string, number>;
  grid?: Record<string, unknown> | null;
  sources: string[];
  disclaimer: string;
  note: string;
}
