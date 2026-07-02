import { useCallback, useState } from "react";
import type { RevenueIQAnalyzeRequest, RevenueIQAnalyzeResponse } from "../types/revenueiq";

const COMPONENT_LABELS: Record<string, string> = {
  pv_modules: "PV modules",
  inverters: "Inverters / power conversion",
  mounting_structure: "Mounting structure",
  dc_cabling: "DC cabling + combiner",
  ac_cabling: "AC cabling + MV transformer",
  civil_works: "Civil works / earthworks",
  grid_connection: "Grid connection",
  engineering: "Engineering (FEED, detailed)",
  permitting: "Permitting + development",
  commissioning: "Commissioning + testing",
};

function fmtMoney(lo: number, hi: number, currency: string, fx: number): string {
  if (currency === "INR") {
    return `₹${(lo / 1e7).toFixed(1)}–${(hi / 1e7).toFixed(1)} Cr (€${(lo / 1e6).toFixed(2)}–${(hi / 1e6).toFixed(2)} M)`;
  }
  if (currency === "USD") {
    return `$${(lo / 1e6).toFixed(2)}–${(hi / 1e6).toFixed(2)} M (€${(lo / fx / 1e6).toFixed(2)}–${(hi / fx / 1e6).toFixed(2)} M)`;
  }
  if (currency === "EUR") {
    return `€${(lo / 1e6).toFixed(2)}–${(hi / 1e6).toFixed(2)} M`;
  }
  return `${currency} ${(lo / 1e6).toFixed(2)}–${(hi / 1e6).toFixed(2)} M`;
}

function viabilityClass(v: string): string {
  const u = v.toUpperCase();
  if (u === "STRONG") return "revenue-viability-strong";
  if (u === "THIN") return "revenue-viability-thin";
  return "revenue-viability-marginal";
}

export interface RevenueIQPageProps {
  locked: boolean;
  busy: boolean;
  error: string;
  result: RevenueIQAnalyzeResponse | null;
  country: string;
  baseRequest: Omit<
    RevenueIQAnalyzeRequest,
    "wacc_pct" | "project_lifetime_yr" | "tariff_override_local_mwh" | "capex_override_eur_kwp" | "itc_rate"
  >;
  onAnalyze: (overrides: Partial<RevenueIQAnalyzeRequest>) => Promise<void>;
}

export function RevenueIQPage({
  locked,
  busy,
  error,
  result,
  country,
  baseRequest: _baseRequest,
  onAnalyze,
}: RevenueIQPageProps) {
  const isUS = /united states|usa|america|^us$/i.test(country);
  const [assumptionsOpen, setAssumptionsOpen] = useState(false);
  const [capexOpen, setCapexOpen] = useState(true);
  const [wacc, setWacc] = useState(result?.wacc_pct ?? 6.5);
  const [lifetime, setLifetime] = useState(25);
  const [tariffOverride, setTariffOverride] = useState("");
  const [capexOverride, setCapexOverride] = useState("");
  const [itcRate, setItcRate] = useState(isUS ? 0.3 : 0);

  const recalc = useCallback(() => {
    void onAnalyze({
      wacc_pct: wacc,
      project_lifetime_yr: lifetime,
      tariff_override_local_mwh: tariffOverride ? Number(tariffOverride) : null,
      capex_override_eur_kwp: capexOverride ? Number(capexOverride) : null,
      itc_rate: isUS ? itcRate : 0,
    });
  }, [onAnalyze, wacc, lifetime, tariffOverride, capexOverride, itcRate, isUS]);

  if (locked) {
    return (
      <div className="module-card module-revenueiq">
        <div className="module-head">
          <h2>RevenueIQ — economic screening</h2>
          <span className="module-tag">Locked</span>
        </div>
        <div className="locked-card">
          <p>
            Run LayoutIQ first to get installed capacity. RevenueIQ needs it to compute CAPEX and IRR.
          </p>
        </div>
      </div>
    );
  }

  const cur = result?.local_currency ?? "EUR";
  const fx = result?.eur_fx_rate ?? 1;

  return (
    <div className="module-card module-revenueiq">
      <div className="module-head">
        <h2>RevenueIQ — economic screening</h2>
        <span className="module-tag">Step 5</span>
      </div>
      <p className="hint">
        Indicative CAPEX, OPEX, revenue, and project finance KPIs from LayoutIQ + YieldIQ inputs. All figures
        are screening bands — not bankable.
      </p>

      {busy && !result ? (
        <p className="hint">Running RevenueIQ automatically…</p>
      ) : null}


      {result?.success ? (
        <>
          <div className={`revenue-viability-card ${viabilityClass(result.viability)}`}>
            <span className="revenue-viability-label">{result.viability}</span>
            <p className="revenue-viability-note">{result.viability_note}</p>
          </div>

          <div className="yield-metric-grid revenue-kpi-grid">
            <div className="yield-metric-card">
              <span className="yield-metric-label">LCOE</span>
              <strong>
                €{result.lcoe_lo_eur_mwh}–{result.lcoe_hi_eur_mwh}/MWh
              </strong>
            </div>
            <div className="yield-metric-card">
              <span className="yield-metric-label">Payback</span>
              <strong>
                {result.payback_lo_yr ?? "—"}–{result.payback_hi_yr ?? "—"} yr
              </strong>
            </div>
            <div className="yield-metric-card">
              <span className="yield-metric-label">Project IRR</span>
              <strong>
                {result.irr_lo_pct ?? "—"}–{result.irr_hi_pct ?? "—"}%
              </strong>
            </div>
            <div className="yield-metric-card">
              <span className="yield-metric-label">NPV @ {result.wacc_pct}% WACC</span>
              <strong>
                €{(result.npv_lo_eur ?? 0) / 1e6}–{(result.npv_hi_eur ?? 0) / 1e6} M
              </strong>
            </div>
          </div>

          <details open={capexOpen} onToggle={(e) => setCapexOpen((e.target as HTMLDetailsElement).open)}>
            <summary className="collapsible-summary">CAPEX breakdown</summary>
            <div className="table-scroll">
              <table className="data-table compact">
                <thead>
                  <tr>
                    <th>Component</th>
                    <th>Low</th>
                    <th>High</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(COMPONENT_LABELS).map(([key, label]) => {
                    const row = result.capex_breakdown[key];
                    if (!row) return null;
                    return (
                      <tr key={key}>
                        <td>{label}</td>
                        <td>€{(row.lo_eur / 1e3).toFixed(0)} k</td>
                        <td>€{(row.hi_eur / 1e3).toFixed(0)} k</td>
                      </tr>
                    );
                  })}
                  <tr>
                    <td>
                      <strong>Gross total CAPEX</strong>
                    </td>
                    <td colSpan={2}>{fmtMoney(result.capex_lo_eur, result.capex_hi_eur, cur, fx)}</td>
                  </tr>
                  {result.itc_credit_eur > 0 ? (
                    <>
                      <tr>
                        <td>ITC credit (30%)</td>
                        <td colSpan={2}>
                          −{fmtMoney(result.itc_credit_eur, result.itc_credit_eur, cur, fx)}
                        </td>
                      </tr>
                      <tr>
                        <td>
                          <strong>Effective CAPEX</strong>
                        </td>
                        <td colSpan={2}>
                          {fmtMoney(
                            result.effective_capex_lo_eur,
                            result.effective_capex_hi_eur,
                            cur,
                            fx,
                          )}
                        </td>
                      </tr>
                    </>
                  ) : null}
                </tbody>
              </table>
            </div>
          </details>

          <details open={assumptionsOpen} onToggle={(e) => setAssumptionsOpen((e.target as HTMLDetailsElement).open)}>
            <summary className="collapsible-summary">Assumptions (editable)</summary>
            <div className="assumptions-grid">
              <label>
                WACC (%)
                <input
                  type="number"
                  step="0.1"
                  value={wacc}
                  onChange={(e) => setWacc(Number(e.target.value))}
                />
              </label>
              <label>
                Project lifetime (yr)
                <input
                  type="number"
                  min={1}
                  max={40}
                  value={lifetime}
                  onChange={(e) => setLifetime(Number(e.target.value))}
                />
              </label>
              <label>
                Tariff override ({cur}/MWh)
                <input
                  type="number"
                  placeholder={`Default: ${result.tariff_lo_local_mwh}–${result.tariff_hi_local_mwh}`}
                  value={tariffOverride}
                  onChange={(e) => setTariffOverride(e.target.value)}
                />
              </label>
              <label>
                CAPEX override (€/kWp)
                <input
                  type="number"
                  placeholder="Model default"
                  value={capexOverride}
                  onChange={(e) => setCapexOverride(e.target.value)}
                />
              </label>
              {isUS ? (
                <label>
                  ITC rate (0–1)
                  <input
                    type="number"
                    step="0.01"
                    min={0}
                    max={1}
                    value={itcRate}
                    onChange={(e) => setItcRate(Number(e.target.value))}
                  />
                </label>
              ) : null}
            </div>
            <button className="btn btn-primary" type="button" onClick={recalc} disabled={busy}>
              {busy ? "Recalculating…" : "Recalculate"}
            </button>
          </details>

          <div className="table-scroll">
            <h3 className="subsection-title">Sensitivity (±10% → IRR Δpp)</h3>
            <table className="data-table compact">
              <thead>
                <tr>
                  <th>Variable</th>
                  <th>IRR impact</th>
                  <th>Flag</th>
                </tr>
              </thead>
              <tbody>
                {(
                  [
                    ["yield", "Energy yield"],
                    ["capex", "Total CAPEX"],
                    ["tariff", "Tariff / PPA rate"],
                    ["opex", "OPEX"],
                  ] as const
                ).map(([key, label]) => {
                  const delta = result.sensitivity[key] ?? 0;
                  return (
                    <tr key={key}>
                      <td>{label}</td>
                      <td>{delta.toFixed(1)} pp</td>
                      <td>{delta > 3 ? "Key Risk Factor" : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {error ? <div className="error-banner">{error}</div> : null}

      <p className="disclaimer footer-note">{result?.screening_disclaimer ?? ""}</p>
    </div>
  );
}
