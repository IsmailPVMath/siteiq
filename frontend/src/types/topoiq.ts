export interface TopoIQAnalyzeRequest {
  project_name: string;
  country: string;
  land_use: "Standard" | "Agri-PV";
  polygons: Array<Array<{ lat: number; lon: number }>>;
  grid_m?: number;
  allow_coarsen?: boolean;
  contour_minor?: number;
  contour_major?: number;
  mask_geojson?: unknown;
}

export type TerrainDriverKind = "positive" | "warn" | "neutral";

export interface TerrainDrivers {
  terrain_score: number;
  terrain_score_label: string;
  drivers: Array<[string, string, TerrainDriverKind]>;
  why_bullets: Array<[TerrainDriverKind, string]>;
}

export interface TopoIQAnalyzeResponse {
  project_name: string;
  country: string;
  land_use: string;
  area_ha: number;
  grid_m_requested: number;
  grid_m_used: number;
  grid_points: number;
  dem_zoom: number;
  tile_count: number;
  terrain_source_used: string;
  terrain_source: Record<string, unknown>;
  elevation: {
    z_min: number;
    z_max: number;
    z_range: number;
    center_elev: number;
  };
  slope: {
    mean: number;
    max: number;
    pct_over5: number;
    pct_over10: number;
    bins?: number[];
  };
  extras: Record<string, unknown>;
  verdict_fixed: { label: string; detail: string };
  verdict_tracker: { label: string; detail: string };
  terrain_drivers: TerrainDrivers;
  contour_minor: number;
  contour_major: number;
  disclaimer: string;
  bbox: { lat_c: number; lon_c: number };
  route_note?: string | null;
}

export interface YieldIQAnalyzeRequest {
  lat: number;
  lon: number;
  mount_type: string;
  gcr_1p?: number;
  gcr_2p?: number;
  soiling_loss?: number;
  other_loss?: number;
}

export interface YieldConfig {
  display_name: string;
  spec_y: number;
  pr?: number | null;
  gcr: number;
  shading: number;
  total_loss: number;
  monthly: number[];
  [key: string]: unknown;
}

export interface YieldIQAnalyzeResponse {
  lat: number;
  lon: number;
  mount_type: string;
  raddatabase?: string | null;
  configs: Record<string, YieldConfig>;
  cross_ref_bundle: Record<string, number | null>;
  disclosure: string;
}
