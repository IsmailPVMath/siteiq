export type RoadMode = "auto" | "manual" | "off";
export type RowAlignment = "horizontal" | "boundary";

export interface LayoutElectricalConfig {
  module_h?: number;
  module_w?: number;
  module_wp?: number;
  modules_per_string?: number;
  inter_string_gap_m?: number;
  tracker_string_options?: number[];
  max_tracker_length_m?: number;
  rows_per_block?: number;
  block_gap_m?: number;
  road_mode?: RoadMode;
  road_preset?: string;
  exclude_tracker_slope?: boolean;
  tracker_slope_limit_pct?: number;
  slope_restriction_grid_m?: number;
}

export const DEFAULT_LAYOUT_CONFIG: Required<LayoutElectricalConfig> = {
  module_h: 2.094,
  module_w: 1.038,
  module_wp: 550,
  modules_per_string: 28,
  inter_string_gap_m: 0.5,
  tracker_string_options: [8, 7, 6, 5, 4, 3, 2, 1],
  max_tracker_length_m: 260,
  rows_per_block: 0,
  block_gap_m: 0.0,
  road_mode: "off",
  road_preset: "no_roads",
  exclude_tracker_slope: false,
  tracker_slope_limit_pct: 6.0,
  slope_restriction_grid_m: 20.0,
};

export const ROAD_PRESETS: { id: string; label: string; mode: RoadMode }[] = [
  { id: "sat_auto", label: "SAT auto — 2 rows + 5 m N-S gap", mode: "auto" },
  { id: "sat_wide", label: "Wide access — 2 rows + 8 m N-S gap", mode: "manual" },
  { id: "sat_single", label: "Single-row blocks — 1 row + 5 m gap", mode: "manual" },
  { id: "no_roads", label: "No access roads (strings only)", mode: "off" },
  { id: "custom", label: "Custom — set rows + N-S gap", mode: "manual" },
];

export function layoutPayloadFrom(
  input?: Partial<LayoutElectricalConfig>,
): LayoutElectricalConfig {
  return {
    module_h: input?.module_h ?? DEFAULT_LAYOUT_CONFIG.module_h,
    module_w: input?.module_w ?? DEFAULT_LAYOUT_CONFIG.module_w,
    module_wp: input?.module_wp ?? DEFAULT_LAYOUT_CONFIG.module_wp,
    modules_per_string: input?.modules_per_string ?? DEFAULT_LAYOUT_CONFIG.modules_per_string,
    inter_string_gap_m: input?.inter_string_gap_m ?? DEFAULT_LAYOUT_CONFIG.inter_string_gap_m,
    tracker_string_options:
      input?.tracker_string_options ?? DEFAULT_LAYOUT_CONFIG.tracker_string_options,
    max_tracker_length_m: input?.max_tracker_length_m ?? DEFAULT_LAYOUT_CONFIG.max_tracker_length_m,
    rows_per_block: input?.rows_per_block ?? DEFAULT_LAYOUT_CONFIG.rows_per_block,
    block_gap_m: input?.block_gap_m ?? DEFAULT_LAYOUT_CONFIG.block_gap_m,
    road_mode: input?.road_mode ?? DEFAULT_LAYOUT_CONFIG.road_mode,
    road_preset: input?.road_preset ?? DEFAULT_LAYOUT_CONFIG.road_preset,
    exclude_tracker_slope:
      input?.exclude_tracker_slope ?? DEFAULT_LAYOUT_CONFIG.exclude_tracker_slope,
    tracker_slope_limit_pct:
      input?.tracker_slope_limit_pct ?? DEFAULT_LAYOUT_CONFIG.tracker_slope_limit_pct,
    slope_restriction_grid_m:
      input?.slope_restriction_grid_m ?? DEFAULT_LAYOUT_CONFIG.slope_restriction_grid_m,
  };
}
