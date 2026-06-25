export type LandUse = "Standard" | "Agri-PV";

export interface BoundaryPoint {
  lat: number;
  lon: number;
}

export interface GateAnalyzeRequest {
  project_name: string;
  lat: number;
  lon: number;
  area_ha: number;
  land_use: LandUse;
  mount_type: string;
  country: string;
  boundary?: BoundaryPoint[];
  boundaries?: BoundaryPoint[][];
  run_layout: boolean;
}

export interface MetricBlock {
  success?: boolean;
  rating?: string;
  detail?: string;
  [key: string]: unknown;
}

export interface GateAnalyzeResponse {
  success: boolean;
  project_name: string;
  coordinates: { lat: number; lon: number };
  solar: MetricBlock;
  terrain: MetricBlock;
  flood: MetricBlock;
  regulatory: MetricBlock;
  capacity: MetricBlock;
  yield_configs: Record<string, unknown>;
  layout?: Record<string, unknown> | null;
  bom?: Record<string, string> | null;
  pvmath_score?: number | null;
  verdict: string;
  verdict_detail: string;
  errors: string[];
  api_version: string;
}

export interface MeResponse {
  user_id: string;
  email: string;
  is_admin: boolean;
  usage: {
    plan: string;
    mode: string;
    limit: number | null;
    total: number;
    per_app: Record<string, number>;
    remaining: number | null;
    at_limit: boolean;
  };
}
