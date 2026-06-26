import type * as GeoJSON from "geojson";
import type { BoundaryPoint, LandUse } from "./gate";
import type { LayoutElectricalConfig, RoadMode } from "./layoutConfig";

export const PROJECT_SETUP_SCHEMA_VERSION = 1;

export type InputMethod =
  | "map"
  | "kml"
  | "kmz"
  | "geojson"
  | "shapefile"
  | "paste"
  | "import";

export type UnitsSystem = "metric" | "imperial";

export interface SetupParcel {
  id: string;
  name: string;
  layer_group: string;
  area_ha: number;
  coords: BoundaryPoint[];
  enabled: boolean;
}

export interface ProjectInfo {
  name: string;
  client: string;
  notes: string;
}

export interface ProjectLocation {
  country: string;
  state: string;
  city: string;
  lat: number;
  lon: number;
}

export interface ProjectGeometry {
  site_boundary?: BoundaryPoint[];
  parcels: SetupParcel[];
  restrictions: BoundaryPoint[][];
  buildable_area_geojson: GeoJSON.GeoJSON | null;
  buildable_area_ha: number | null;
  gross_area_ha: number;
}

export interface DesignBasis {
  land_use: LandUse;
  mount_type: string;
  target_capacity_mwp: number | null;
  target_cod: string;
  currency: string;
  coordinate_system: string;
  engineering_standard: string;
  design_standard: string;
  units: UnitsSystem;
}

export interface WorkflowReadiness {
  has_boundary: boolean;
  can_run_siteiq: boolean;
  can_run_terrainiq: boolean;
  can_run_layoutiq: boolean;
  can_run_yieldiq: boolean;
}

export interface ProjectSetupDraft {
  schema_version: number;
  project_info: ProjectInfo;
  location: ProjectLocation;
  geometry: ProjectGeometry;
  design_basis: DesignBasis;
  assumptions: LayoutElectricalConfig & {
    road_mode?: RoadMode;
    road_preset?: string;
    rows_per_block?: number;
    block_gap_m?: number;
  };
  input_method: InputMethod;
  workflow_state: {
    readiness: WorkflowReadiness;
  };
}

export interface SetupValidationIssue {
  level: "error" | "warning";
  field?: string;
  message: string;
}

export interface SetupValidationResult {
  valid: boolean;
  issues: SetupValidationIssue[];
  readiness: WorkflowReadiness;
  modules_to_run: string[];
}

export interface ProjectSetupValidateResponse {
  valid: boolean;
  issues: SetupValidationIssue[];
  readiness: WorkflowReadiness;
  modules_to_run: string[];
}
