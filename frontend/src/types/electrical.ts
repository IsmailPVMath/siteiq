/** LayoutIQ electrical screening — module/inverter selection and results. */

export interface ElectricalScreeningConfig {
  electrical_module?: string;
  electrical_inverter?: string;
  system_voltage_v?: number;
  electrical_dc_ac_ratio?: number;
  strings_per_combiner?: number;
  tmy_t2m?: number[];
}

export interface ElectricalBomSection {
  module_model?: string;
  inverter_model?: string;
  inverter_count?: number;
  system_voltage_V?: number;
  modules_per_string?: number;
  total_strings?: number;
  dc_ac_ratio?: number;
  dc_string_cable_mm2?: number;
  dc_string_cable_m?: number;
  dc_main_cable_mm2?: number | null;
  dc_main_cable_m?: number | null;
  ac_lv_cable_mm2?: number;
  ac_lv_cable_m?: number;
  string_combiners?: number;
  Voc_max_string_V?: number;
  Vmp_op_string_V?: number;
  voc_margin_pct?: number;
  voc_margin_low?: boolean;
}

export interface ElectricalResult {
  string_sizing: Record<string, unknown>;
  cables: Record<string, unknown>;
  electrical_bom: ElectricalBomSection;
  disclaimer?: string;
}

export interface WorkflowLayoutElectricalResponse {
  success: boolean;
  dc_kwp: number;
  electrical: ElectricalResult;
  bom: Record<string, unknown>;
  warnings: string[];
}

export interface CuratedModuleLayoutSpec {
  name: string;
  Wp: number;
  module_h_m: number;
  module_w_m: number;
  bifacial?: boolean;
}

export interface EquipmentCuratedResponse {
  modules: CuratedModuleLayoutSpec[];
  module_names: string[];
  inverter_names: string[];
}

export interface EquipmentSearchHit {
  name: string;
  Wp?: number;
  Voc?: number;
  Vmp?: number;
  Isc?: number;
  type?: string;
  Paco_kW?: number;
  Vdcmax?: number;
  Mppt_low?: number;
  Mppt_high?: number;
  source?: string;
}

export const DEFAULT_ELECTRICAL_MODULE = "Jinko Tiger Neo N-type 620Wp";
export const DEFAULT_ELECTRICAL_INVERTER_CENTRAL = "Sungrow SG3125HV-30 (3.125 MW, 1500V)";
export const DEFAULT_ELECTRICAL_INVERTER_STRING = "Huawei SUN2000-196KTL (196 kW, 1500V)";

export function defaultInverterForMount(mountType: string): string {
  const t = mountType.toLowerCase();
  if (t.includes("tracker") || t.startsWith("sat")) {
    return DEFAULT_ELECTRICAL_INVERTER_CENTRAL;
  }
  return DEFAULT_ELECTRICAL_INVERTER_STRING;
}

export function electricalPayloadFrom(
  input?: Partial<ElectricalScreeningConfig>,
): ElectricalScreeningConfig {
  return {
    electrical_module: input?.electrical_module ?? DEFAULT_ELECTRICAL_MODULE,
    electrical_inverter: input?.electrical_inverter,
    system_voltage_v: input?.system_voltage_v ?? 1500,
    electrical_dc_ac_ratio: input?.electrical_dc_ac_ratio ?? 1.2,
    strings_per_combiner: input?.strings_per_combiner ?? 12,
    tmy_t2m: input?.tmy_t2m,
  };
}
