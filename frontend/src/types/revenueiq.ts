export interface RevenueIQAnalyzeRequest {
  project_name?: string;
  country: string;
  land_use: string;
  mount_type: string;
  dc_kwp: number;
  annual_mwh: number;
  site_area_ha?: number;
  mean_slope_pct?: number | null;
  grid_distance_km?: number | null;
  terrain_grade?: string;
  wacc_pct?: number;
  project_lifetime_yr?: number;
  tariff_override_local_mwh?: number | null;
  capex_override_eur_kwp?: number | null;
  itc_rate?: number;
  lat?: number | null;
  lon?: number | null;
}

export interface RevenueIQAnalyzeResponse {
  success: boolean;
  errors: string[];
  local_currency: string;
  eur_fx_rate: number;
  capex_lo_eur: number;
  capex_hi_eur: number;
  capex_lo_local: number;
  capex_hi_local: number;
  itc_credit_eur: number;
  effective_capex_lo_eur: number;
  effective_capex_hi_eur: number;
  capex_breakdown: Record<
    string,
    { lo_eur: number; hi_eur: number; lo_local: number; hi_local: number }
  >;
  opex_lo_eur_yr: number;
  opex_hi_eur_yr: number;
  opex_lo_local_yr: number;
  opex_hi_local_yr: number;
  tariff_mode: string;
  tariff_label: string;
  tariff_lo_eur_mwh: number;
  tariff_hi_eur_mwh: number;
  tariff_lo_local_mwh: number;
  tariff_hi_local_mwh: number;
  revenue_yr1_lo_eur: number;
  revenue_yr1_hi_eur: number;
  revenue_25yr_lo_eur: number;
  revenue_25yr_hi_eur: number;
  lcoe_lo_eur_mwh: number;
  lcoe_hi_eur_mwh: number;
  payback_lo_yr: number | null;
  payback_hi_yr: number | null;
  irr_lo_pct: number | null;
  irr_hi_pct: number | null;
  npv_lo_eur: number | null;
  npv_hi_eur: number | null;
  sensitivity: Record<string, number>;
  viability: string;
  viability_note: string;
  economic_score: number;
  wacc_pct: number;
  screening_disclaimer: string;
}
