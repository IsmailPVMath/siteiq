export type WorkflowStep = "input" | "processing" | "output";

export const WORKFLOW_STEPS: { id: WorkflowStep; label: string }[] = [
  { id: "input", label: "Project input" },
  { id: "processing", label: "Screening" },
  { id: "output", label: "Results" },
];

/** Unified workflow — screening excludes terrain (TopoIQ only). */
export const PROCESSING_STAGES = [
  "Solar resource (PVGIS)",
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
