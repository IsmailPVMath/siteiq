import type { YieldConfig, YieldIQAnalyzeResponse } from "../types/terrainiq";

const CONFIG_ORDER = ["1P Fixed", "2P Fixed", "1P Tracker", "2P Tracker"] as const;

interface Props {
  result: YieldIQAnalyzeResponse;
  selectedConfigKey?: string | null;
  selectedDcKwp?: number | null;
  mountFilter?: "all" | "fixed" | "sat";
}

function fmtLoss(val: unknown): string {
  if (val == null || val === "") return "—";
  const n = Number(val);
  if (!Number.isFinite(n)) return "—";
  return `${Math.abs(n).toFixed(1)}%`;
}

function fmtNum(val: unknown, digits = 0): string {
  if (val == null || val === "") return "—";
  const n = Number(val);
  if (!Number.isFinite(n)) return "—";
  return n.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function configMatchesFilter(key: string, mountFilter: Props["mountFilter"]): boolean {
  if (!mountFilter || mountFilter === "all") return true;
  const tracker = key.includes("Tracker");
  return mountFilter === "sat" ? tracker : !tracker;
}

export function YieldResultsPanel({
  result,
  selectedConfigKey,
  selectedDcKwp,
  mountFilter = "all",
}: Props) {
  const configs = result.configs;
  const visibleKeys = CONFIG_ORDER.filter(
    (k) => configs[k] && configMatchesFilter(k, mountFilter),
  );

  const bestKey = visibleKeys.reduce<string | null>((best, key) => {
    if (!best) return key;
    const a = configs[best];
    const b = configs[key];
    const mwhA = selectedDcKwp ? (selectedDcKwp * Number(a.spec_y)) / 1000 : Number(a.spec_y);
    const mwhB = selectedDcKwp ? (selectedDcKwp * Number(b.spec_y)) / 1000 : Number(b.spec_y);
    return mwhB > mwhA ? key : best;
  }, null);

  const bestCfg = bestKey ? configs[bestKey] : null;
  const solar = result.solar_resource ?? {};
  const cross = result.cross_ref_bundle ?? {};

  const fixed1p = configs["1P Fixed"];
  const tracker1p = configs["1P Tracker"];
  const fixed2p = configs["2P Fixed"];
  const tracker2p = configs["2P Tracker"];

  const selectedCfg = selectedConfigKey ? configs[selectedConfigKey] : null;
  const selectedMwh =
    selectedDcKwp && selectedCfg
      ? (selectedDcKwp * Number(selectedCfg.spec_y)) / 1000
      : null;

  return (
    <div className="yield-results-panel">
      {selectedCfg && selectedMwh != null ? (
        <div className="selected-yield-summary">
          <strong>Selected layout estimate:</strong> {selectedMwh.toFixed(0)} MWh/yr at{" "}
          {Number(selectedCfg.spec_y).toFixed(0)} kWh/kWp/yr
        </div>
      ) : null}

      <div className="yield-section">
        <h3>Solar resource</h3>
        <div className="yield-metrics-row">
          <div className="yield-metric">
            <span className="label">GHI (horizontal)</span>
            <span className="value">{fmtNum(solar.ghi)} kWh/m²/yr</span>
          </div>
          <div className="yield-metric">
            <span className="label">DNI (direct normal)</span>
            <span className="value">{fmtNum(solar.dni)} kWh/m²/yr</span>
          </div>
          <div className="yield-metric">
            <span className="label">DHI (diffuse horizontal)</span>
            <span className="value">{fmtNum(solar.dhi)} kWh/m²/yr</span>
          </div>
        </div>
      </div>

      <div className="yield-section">
        <h3>Performance — plane-of-array irradiance</h3>
        <div className="yield-metrics-row">
          {fixed1p && configMatchesFilter("1P Fixed", mountFilter) ? (
            <div className="yield-metric">
              <span className="label">POA — Fixed Tilt (1P)</span>
              <span className="value">{fmtNum(fixed1p.h_y ?? fixed1p.annual_ghi)} kWh/m²/yr</span>
            </div>
          ) : null}
          {tracker1p && configMatchesFilter("1P Tracker", mountFilter) ? (
            <div className="yield-metric">
              <span className="label">POA — Single-Axis Tracker (1P)</span>
              <span className="value">{fmtNum(tracker1p.h_y ?? tracker1p.annual_ghi)} kWh/m²/yr</span>
            </div>
          ) : null}
        </div>
      </div>

      {bestCfg && bestKey ? (
        <div className="yield-section">
          <h3>
            Losses breakdown — {bestKey}
            {bestKey === selectedConfigKey ? " (selected)" : " (best specific yield)"}
          </h3>
          <div className="yield-metrics-row">
            <div className="yield-metric">
              <span className="label">Shading</span>
              <span className="value">{fmtLoss(bestCfg.shading)}</span>
            </div>
            <div className="yield-metric">
              <span className="label">Temperature</span>
              <span className="value">{fmtLoss(bestCfg.l_tg)}</span>
            </div>
            <div className="yield-metric">
              <span className="label">Soiling</span>
              <span className="value">{fmtLoss(bestCfg.soiling_loss)}</span>
            </div>
            <div className="yield-metric">
              <span className="label">Total loss</span>
              <span className="value">{fmtLoss(bestCfg.l_total ?? bestCfg.total_loss)}</span>
            </div>
          </div>
          <p className="module-note">
            Temperature is PVGIS physics-based. Total loss combines shading, soiling, system losses,
            temperature, AOI, and spectral where available.
          </p>
        </div>
      ) : null}

      <div className="yield-section">
        <h3>Configuration comparison</h3>
        <div className="yield-table-wrap">
          <table className="yield-table yield-table-wide">
            <thead>
              <tr>
                <th>Configuration</th>
                <th>GCR</th>
                <th>Shading</th>
                <th>Total loss</th>
                <th>POA irr.</th>
                <th>Specific yield</th>
                <th>Annual MWh</th>
                <th>PR</th>
                <th>CF</th>
              </tr>
            </thead>
            <tbody>
              {visibleKeys.map((key) => {
                const row = configs[key] as YieldConfig;
                const isBest = key === bestKey;
                const isSelected = key === selectedConfigKey;
                const mwh =
                  selectedDcKwp != null
                    ? (selectedDcKwp * Number(row.spec_y)) / 1000
                    : null;
                return (
                  <tr
                    key={key}
                    className={
                      isSelected ? "layout-row-selected" : isBest ? "layout-row-recommended" : ""
                    }
                  >
                    <td>
                      {row.display_name ?? key}
                      {isBest ? <span className="layout-rec-badge">Best</span> : null}
                      {isSelected ? <span className="layout-rec-badge layout-sel-badge">Sel.</span> : null}
                    </td>
                    <td>{Number(row.gcr).toFixed(2)}</td>
                    <td>{fmtLoss(row.shading)}</td>
                    <td>{fmtLoss(row.l_total ?? row.total_loss)}</td>
                    <td>{fmtNum(row.h_y, 0)}</td>
                    <td>
                      <strong>{Number(row.spec_y).toFixed(0)}</strong> kWh/kWp/yr
                    </td>
                    <td>{mwh != null ? fmtNum(mwh, 0) : "—"}</td>
                    <td>{row.pr != null ? `${Number(row.pr).toFixed(1)}%` : "—"}</td>
                    <td>{row.cf != null ? `${Number(row.cf).toFixed(1)}%` : "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {cross.screening_fixed != null || cross.screening_tracker != null ? (
        <div className="yield-cross-ref">
          <strong>Cross-module yield reference</strong>
          <p>
            SiteIQ screening vs YieldIQ analysis (1P): Fixed{" "}
            {cross.screening_fixed != null ? `${fmtNum(cross.screening_fixed, 0)}` : "—"} →{" "}
            {cross.analysis_fixed != null ? `${fmtNum(cross.analysis_fixed, 0)}` : "—"} kWh/kWp/yr
            {cross.screening_fixed && cross.analysis_fixed
              ? ` (${(((cross.analysis_fixed - cross.screening_fixed) / cross.screening_fixed) * 100).toFixed(1)}%)`
              : ""}
            {" · "}
            Tracker{" "}
            {cross.screening_tracker != null ? `${fmtNum(cross.screening_tracker, 0)}` : "—"} →{" "}
            {cross.analysis_tracker != null ? `${fmtNum(cross.analysis_tracker, 0)}` : "—"} kWh/kWp/yr
            {cross.screening_tracker && cross.analysis_tracker
              ? ` (${(((cross.analysis_tracker - cross.screening_tracker) / cross.screening_tracker) * 100).toFixed(1)}%)`
              : ""}
          </p>
        </div>
      ) : null}

      {(fixed1p && tracker1p) || (fixed2p && tracker2p) ? (
        <div className="yield-section">
          <h3>Tracker gain</h3>
          <div className="yield-metrics-row">
            {fixed1p && tracker1p && configMatchesFilter("1P Tracker", mountFilter) ? (
              <div className="yield-metric">
                <span className="label">Tracker gain (1P)</span>
                <span className="value">
                  +{(Number(tracker1p.spec_y) - Number(fixed1p.spec_y)).toFixed(0)} kWh/kWp/yr (
                  {(((Number(tracker1p.spec_y) - Number(fixed1p.spec_y)) / Number(fixed1p.spec_y)) * 100).toFixed(1)}%)
                </span>
              </div>
            ) : null}
            {fixed2p && tracker2p && configMatchesFilter("2P Tracker", mountFilter) ? (
              <div className="yield-metric">
                <span className="label">Tracker gain (2P)</span>
                <span className="value">
                  +{(Number(tracker2p.spec_y) - Number(fixed2p.spec_y)).toFixed(0)} kWh/kWp/yr (
                  {(((Number(tracker2p.spec_y) - Number(fixed2p.spec_y)) / Number(fixed2p.spec_y)) * 100).toFixed(1)}%)
                </span>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      {mountFilter === "sat" ? (
        <p className="yield-optimal-tilt">
          Single-Axis Tracker: modules follow the sun on a horizontal N–S axis (0° axis tilt) —
          fixed optimal tilt does not apply. PVGIS two-axis irradiance is used for the tracker yield.
        </p>
      ) : fixed1p?.optimal_tilt != null || fixed2p?.optimal_tilt != null ? (
        <p className="yield-optimal-tilt">
          Optimal tilt (PVGIS):{" "}
          {fixed1p?.optimal_tilt != null ? `1P Fixed: ${fixed1p.optimal_tilt}°` : ""}
          {fixed1p?.optimal_tilt != null && fixed2p?.optimal_tilt != null ? " | " : ""}
          {fixed2p?.optimal_tilt != null ? `2P Fixed: ${fixed2p.optimal_tilt}°` : ""}
        </p>
      ) : null}

      {(() => {
        const chartCfg = selectedCfg ?? bestCfg;
        const monthly = chartCfg?.monthly;
        if (!Array.isArray(monthly) || monthly.length !== 12) return null;
        const max = Math.max(...monthly.map((v) => Number(v) || 0), 1);
        const months = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];
        return (
          <div className="yield-section">
            <h3>
              Monthly specific yield
              {chartCfg?.display_name ? ` — ${chartCfg.display_name}` : ""}
            </h3>
            <div className="yield-month-chart" role="img" aria-label="Monthly specific yield">
              {monthly.map((v, i) => {
                const val = Number(v) || 0;
                return (
                  <div className="yield-month-col" key={i}>
                    <div className="yield-month-bar-track">
                      <div
                        className="yield-month-bar"
                        style={{ height: `${(val / max) * 100}%` }}
                        title={`${months[i]}: ${val.toFixed(0)} kWh/kWp`}
                      />
                    </div>
                    <span className="yield-month-label">{months[i]}</span>
                  </div>
                );
              })}
            </div>
            <p className="hint">
              Specific yield (kWh/kWp) per month for the selected configuration. Full PVsyst-style
              loss waterfall and shading scene come in detailed YieldIQ.
            </p>
          </div>
        );
      })()}

      <p className="module-note">{result.disclosure}</p>
      {result.raddatabase ? (
        <p className="hint">PVGIS radiation database: {result.raddatabase}</p>
      ) : null}
    </div>
  );
}
