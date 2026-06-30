import {
  DEFAULT_LAYOUT_CONFIG,
  roadParamsFromPreset,
  type RoadMode,
  type RowAlignment,
} from "../types/layoutConfig";
import type { LatLon } from "./alignmentGuide";
import type { GateAnalyzeRequest } from "../types/gate";
import type {
  LayoutLandCost,
  LayoutOptimizationMode,
  LayoutSweepRow,
} from "../types/workflow";

/** Persisted LayoutIQ sidebar + strategy inputs (saved with the project). */
export type AlignmentSource = "default" | "guide";

export interface LayoutIQSnapshot {
  optimization_mode: LayoutOptimizationMode;
  land_cost: LayoutLandCost;
  bifacial: boolean;
  allow_partial_strings: boolean;
  mount_type: "Fixed Tilt" | "Single-Axis Tracker" | "Compare FT & SAT";
  portrait: "all" | "1" | "2" | "3" | "4";
  row_alignment: RowAlignment;
  custom_gcr: string;
  custom_pitch: string;
  module_h: number;
  module_w: number;
  module_wp: number;
  modules_per_string: number;
  inter_string_gap_m: number;
  tracker_string_options: string;
  max_tracker_length_m: number;
  exclude_tracker_slope: boolean;
  tracker_slope_limit_pct: number;
  road_mode: RoadMode;
  road_preset: string;
  rows_per_block: number;
  block_gap_m: number;
  ns_gap_1_m: number;
  cols_per_block: number;
  ew_gap_m: number;
  azimuth_deg: number;
  azimuth_custom: boolean;
  alignment_source: AlignmentSource;
  alignment_guide: LatLon[];
  use_full_boundary: boolean;
  ignore_soft_constraints: boolean;
  prune_isolated_blocks: boolean;
  selected_layout_row: LayoutSweepRow | null;
}

export type LayoutIQSnapshotSource = Partial<LayoutIQSnapshot>;

function mountFromInput(mountType?: string): LayoutIQSnapshot["mount_type"] {
  if (mountType === "Single-Axis Tracker") return "Single-Axis Tracker";
  if (mountType === "Compare FT & SAT") return "Compare FT & SAT";
  return "Fixed Tilt";
}

/** Map legacy presets / road_repeat_m saves to PVCase-style column + band roads. */
function migrateLegacyRoadSettings(s: LayoutIQSnapshotSource): LayoutIQSnapshotSource {
  const preset = s.road_preset ?? DEFAULT_LAYOUT_CONFIG.road_preset;
  if (preset === "sat_single" || preset === "sat_dense") {
    return { ...s, road_preset: "sat_auto", ...roadParamsFromPreset("sat_auto") };
  }
  if (s.ns_gap_1_m === 0.6) {
    return { ...s, ns_gap_1_m: 0 };
  }
  if (preset === "sat_auto" || preset === "sat_wide" || preset === "sat_ew_100") {
    const hasNewFields =
      (s.cols_per_block ?? 0) > 0 ||
      (s.ns_gap_1_m ?? 0) > 0 ||
      ((s.rows_per_block ?? 0) > 2);
    if (!hasNewFields && ((s.rows_per_block === 1 || s.rows_per_block === 2) || (s as { road_repeat_m?: number }).road_repeat_m)) {
      return { ...s, ...roadParamsFromPreset(preset) };
    }
  }
  return s;
}

/** Defaults from project setup input when no saved LayoutIQ snapshot exists. */
export function layoutIQDefaultsFromInput(input?: GateAnalyzeRequest): LayoutIQSnapshotSource {
  if (!input) return {};
  return {
    mount_type: mountFromInput(input.mount_type),
    module_h: input.module_h,
    module_w: input.module_w,
    module_wp: input.module_wp,
    modules_per_string: input.modules_per_string,
    inter_string_gap_m: input.inter_string_gap_m,
    tracker_string_options: (input.tracker_string_options ?? DEFAULT_LAYOUT_CONFIG.tracker_string_options).join(
      ",",
    ),
    max_tracker_length_m: input.max_tracker_length_m,
    exclude_tracker_slope: input.exclude_tracker_slope,
    tracker_slope_limit_pct: input.tracker_slope_limit_pct,
    road_mode: input.road_mode,
    road_preset: input.road_preset,
    rows_per_block: input.rows_per_block,
    block_gap_m: input.block_gap_m,
    ns_gap_1_m: input.ns_gap_1_m,
    cols_per_block: input.cols_per_block,
    ew_gap_m: input.ew_gap_m,
  };
}

export function mergeLayoutIQSnapshot(
  saved?: LayoutIQSnapshotSource | null,
  input?: GateAnalyzeRequest,
): LayoutIQSnapshot {
  const fromInput = layoutIQDefaultsFromInput(input);
  const s = migrateLegacyRoadSettings(saved ?? {});
  return {
    optimization_mode: s.optimization_mode ?? "balanced",
    land_cost: s.land_cost ?? "auto",
    bifacial: s.bifacial ?? false,
    allow_partial_strings: s.allow_partial_strings ?? false,
    mount_type: s.mount_type ?? fromInput.mount_type ?? "Fixed Tilt",
    portrait: s.portrait ?? "2",
    row_alignment: s.row_alignment ?? "horizontal",
    custom_gcr: s.custom_gcr ?? "",
    custom_pitch: s.custom_pitch ?? "",
    module_h: s.module_h ?? fromInput.module_h ?? DEFAULT_LAYOUT_CONFIG.module_h,
    module_w: s.module_w ?? fromInput.module_w ?? DEFAULT_LAYOUT_CONFIG.module_w,
    module_wp: s.module_wp ?? fromInput.module_wp ?? DEFAULT_LAYOUT_CONFIG.module_wp,
    modules_per_string:
      s.modules_per_string ?? fromInput.modules_per_string ?? DEFAULT_LAYOUT_CONFIG.modules_per_string,
    inter_string_gap_m:
      s.inter_string_gap_m ?? fromInput.inter_string_gap_m ?? DEFAULT_LAYOUT_CONFIG.inter_string_gap_m,
    tracker_string_options:
      s.tracker_string_options ??
      fromInput.tracker_string_options ??
      DEFAULT_LAYOUT_CONFIG.tracker_string_options.join(","),
    max_tracker_length_m:
      s.max_tracker_length_m ?? fromInput.max_tracker_length_m ?? DEFAULT_LAYOUT_CONFIG.max_tracker_length_m,
    exclude_tracker_slope:
      s.exclude_tracker_slope ??
      fromInput.exclude_tracker_slope ??
      DEFAULT_LAYOUT_CONFIG.exclude_tracker_slope,
    tracker_slope_limit_pct:
      s.tracker_slope_limit_pct ??
      fromInput.tracker_slope_limit_pct ??
      DEFAULT_LAYOUT_CONFIG.tracker_slope_limit_pct,
    road_mode: s.road_mode ?? fromInput.road_mode ?? DEFAULT_LAYOUT_CONFIG.road_mode,
    road_preset: s.road_preset ?? fromInput.road_preset ?? DEFAULT_LAYOUT_CONFIG.road_preset,
    rows_per_block: s.rows_per_block ?? fromInput.rows_per_block ?? DEFAULT_LAYOUT_CONFIG.rows_per_block,
    block_gap_m: s.block_gap_m ?? fromInput.block_gap_m ?? DEFAULT_LAYOUT_CONFIG.block_gap_m,
    ns_gap_1_m: s.ns_gap_1_m ?? fromInput.ns_gap_1_m ?? DEFAULT_LAYOUT_CONFIG.ns_gap_1_m,
    cols_per_block: s.cols_per_block ?? fromInput.cols_per_block ?? DEFAULT_LAYOUT_CONFIG.cols_per_block,
    ew_gap_m: s.ew_gap_m ?? fromInput.ew_gap_m ?? DEFAULT_LAYOUT_CONFIG.ew_gap_m,
    azimuth_deg: s.azimuth_deg ?? 180,
    azimuth_custom: s.azimuth_custom ?? false,
    alignment_source: s.alignment_source === "guide" ? "guide" : "default",
    alignment_guide: Array.isArray(s.alignment_guide) ? s.alignment_guide : [],
    use_full_boundary: s.use_full_boundary ?? false,
    ignore_soft_constraints: s.ignore_soft_constraints ?? true,
    prune_isolated_blocks: s.prune_isolated_blocks ?? true,
    selected_layout_row: s.selected_layout_row ?? null,
  };
}

/** Sync top-level workflow module/road fields so project setup also reflects saved LayoutIQ inputs. */
export function layoutIQToWorkflowFields(s: LayoutIQSnapshot): Record<string, unknown> {
  const trackerOpts = s.tracker_string_options
    .split(/[,\s]+/)
    .map((v) => Number(v.trim()))
    .filter((v) => Number.isFinite(v) && v > 0);
  return {
    module_h: s.module_h,
    module_w: s.module_w,
    module_wp: s.module_wp,
    modules_per_string: s.modules_per_string,
    inter_string_gap_m: s.inter_string_gap_m,
    tracker_string_options: trackerOpts.length ? trackerOpts : DEFAULT_LAYOUT_CONFIG.tracker_string_options,
    max_tracker_length_m: s.max_tracker_length_m,
    exclude_tracker_slope: s.exclude_tracker_slope,
    tracker_slope_limit_pct: s.tracker_slope_limit_pct,
    road_mode: s.road_mode,
    road_preset: s.road_preset,
    rows_per_block: s.rows_per_block,
    block_gap_m: s.block_gap_m,
    ns_gap_1_m: s.ns_gap_1_m,
    cols_per_block: s.cols_per_block,
    ew_gap_m: s.ew_gap_m,
  };
}

export function parseLayoutIQSnapshot(raw: unknown): LayoutIQSnapshot | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  const mount =
    o.mount_type === "Single-Axis Tracker"
      ? "Single-Axis Tracker"
      : o.mount_type === "Compare FT & SAT"
        ? "Compare FT & SAT"
        : "Fixed Tilt";
  const portrait = String(o.portrait ?? "2");
  const validPortrait = ["all", "1", "2", "3", "4"].includes(portrait)
    ? (portrait as LayoutIQSnapshot["portrait"])
    : "2";
  const rowAlign = o.row_alignment === "boundary" ? "boundary" : "horizontal";
  const opt = String(o.optimization_mode ?? "balanced");
  const validOpt = ["high_energy", "balanced", "land_optimized", "custom"].includes(opt)
    ? (opt as LayoutOptimizationMode)
    : "balanced";
  const land = String(o.land_cost ?? "auto");
  const validLand = ["auto", "cheap", "balanced", "expensive"].includes(land)
    ? (land as LayoutLandCost)
    : "auto";
  const roadMode = o.road_mode === "auto" || o.road_mode === "manual" || o.road_mode === "off"
    ? o.road_mode
    : "off";
  return mergeLayoutIQSnapshot({
    optimization_mode: validOpt,
    land_cost: validLand,
    bifacial: Boolean(o.bifacial),
    allow_partial_strings: Boolean(o.allow_partial_strings),
    mount_type: mount,
    portrait: validPortrait,
    row_alignment: rowAlign,
    custom_gcr: String(o.custom_gcr ?? ""),
    custom_pitch: String(o.custom_pitch ?? ""),
    module_h: Number(o.module_h) || DEFAULT_LAYOUT_CONFIG.module_h,
    module_w: Number(o.module_w) || DEFAULT_LAYOUT_CONFIG.module_w,
    module_wp: Number(o.module_wp) || DEFAULT_LAYOUT_CONFIG.module_wp,
    modules_per_string: Number(o.modules_per_string) || DEFAULT_LAYOUT_CONFIG.modules_per_string,
    inter_string_gap_m: Number(o.inter_string_gap_m) ?? DEFAULT_LAYOUT_CONFIG.inter_string_gap_m,
    tracker_string_options: String(o.tracker_string_options ?? DEFAULT_LAYOUT_CONFIG.tracker_string_options.join(",")),
    max_tracker_length_m: Number(o.max_tracker_length_m) || DEFAULT_LAYOUT_CONFIG.max_tracker_length_m,
    exclude_tracker_slope: Boolean(o.exclude_tracker_slope),
    tracker_slope_limit_pct: Number(o.tracker_slope_limit_pct) ?? DEFAULT_LAYOUT_CONFIG.tracker_slope_limit_pct,
    road_mode: roadMode,
    road_preset: String(o.road_preset ?? DEFAULT_LAYOUT_CONFIG.road_preset),
    rows_per_block: Number(o.rows_per_block) || 0,
    block_gap_m: Number(o.block_gap_m) || 0,
    ns_gap_1_m: Number(o.ns_gap_1_m) || 0,
    cols_per_block: Number(o.cols_per_block) || 0,
    ew_gap_m: Number(o.ew_gap_m) || 0,
    azimuth_deg: Number(o.azimuth_deg) || 180,
    azimuth_custom: Boolean(o.azimuth_custom),
    alignment_source: o.alignment_source === "guide" ? "guide" : "default",
    alignment_guide: Array.isArray(o.alignment_guide)
      ? (o.alignment_guide as LatLon[]).filter(
          (p) => p && Number.isFinite(p.lat) && Number.isFinite(p.lon),
        )
      : [],
    use_full_boundary: Boolean(o.use_full_boundary),
    ignore_soft_constraints: o.ignore_soft_constraints !== false,
    prune_isolated_blocks: o.prune_isolated_blocks !== false,
    selected_layout_row: (o.selected_layout_row as LayoutSweepRow | null) ?? null,
  });
}
