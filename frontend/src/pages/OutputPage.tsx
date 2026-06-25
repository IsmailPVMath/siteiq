import { useEffect, useMemo, useState } from "react";
import {
  analyzeTopo,
  analyzeYield,
  topoExportsZip,
  topoReportPdf,
  workflowLayoutSweep,
  workflowScore,
} from "../lib/api";
import type { GateAnalyzeRequest } from "../types/gate";
import type { TopoIQAnalyzeRequest, TopoIQAnalyzeResponse, YieldIQAnalyzeResponse } from "../types/topoiq";
import type {
  LayoutSweepRow,
  WorkflowLayoutSweepResponse,
  WorkflowScoreResponse,
  WorkflowScreenResponse,
} from "../types/workflow";

interface Props {
  token: string;
  result: WorkflowScreenResponse;
  input?: GateAnalyzeRequest;
  onNewScreening: () => void;
  onEditInput: () => void;
}

function metric(label: string, rating?: string, detail?: string, extra?: string) {
  return (
    <div className="metric">
      <div className="label">{label}</div>
      <div className="value">{rating || "—"}</div>
      {detail ? <div className="sub">{detail}</div> : null}
      {extra ? <div className="sub">{extra}</div> : null}
    </div>
  );
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function OutputPage({ token, result, input, onNewScreening, onEditInput }: Props) {
  const [topoBusy, setTopoBusy] = useState(false);
  const [topoError, setTopoError] = useState("");
  const [topoResult, setTopoResult] = useState<TopoIQAnalyzeResponse | null>(null);
  const [topoPdfBusy, setTopoPdfBusy] = useState(false);
  const [topoZipBusy, setTopoZipBusy] = useState(false);
  const [yieldBusy, setYieldBusy] = useState(false);
  const [yieldError, setYieldError] = useState("");
  const [yieldResult, setYieldResult] = useState<YieldIQAnalyzeResponse | null>(null);
  const [finalScore, setFinalScore] = useState<WorkflowScoreResponse | null>(null);
  const [layoutBusy, setLayoutBusy] = useState(false);
  const [layoutError, setLayoutError] = useState("");
  const [layoutSweep, setLayoutSweep] = useState<WorkflowLayoutSweepResponse | null>(null);
  const [layoutFilter, setLayoutFilter] = useState<string>("all");

  const cap = result.capacity as Record<string, unknown>;
  const mwp = cap?.mwp_range as string | undefined;
  const mwh = cap?.mwh_range as string | undefined;
  const grid = result.grid as Record<string, unknown>;
  const nearest = grid?.nearest as Record<string, unknown> | undefined;
  const boundary = input?.boundary;
  const hasBoundary = Boolean(boundary && boundary.length >= 3);

  const topoPayload: TopoIQAnalyzeRequest | null = useMemo(() => {
    if (!hasBoundary || !boundary) return null;
    return {
      project_name: input?.project_name || result.project_name || "TopoIQ run",
      country: input?.country || "",
      land_use: input?.land_use || "Standard",
      polygons: [boundary.map((p) => ({ lat: p.lat, lon: p.lon }))],
      grid_m: 5,
      allow_coarsen: false,
      contour_minor: 0.5,
      contour_major: 1.0,
    };
  }, [boundary, hasBoundary, input, result.project_name]);

  const yieldPayload = useMemo(
    () => ({
      lat: result.coordinates.lat,
      lon: result.coordinates.lon,
      mount_type: input?.mount_type || "Fixed Tilt",
      gcr_1p: 0.35,
      gcr_2p: 0.42,
      soiling_loss: 2.0,
      other_loss: 6.0,
    }),
    [input?.mount_type, result.coordinates.lat, result.coordinates.lon],
  );

  async function refreshFinalScore(topo: TopoIQAnalyzeResponse) {
    const terrainScore = topo.terrain_drivers.terrain_score as number | undefined;
    if (terrainScore == null) return;
    try {
      const scored = await workflowScore(token, {
        score_components: result.score_components,
        terrain_score: terrainScore,
      });
      setFinalScore(scored);
    } catch {
      setFinalScore(null);
    }
  }

  async function handleRunTopo() {
    if (!topoPayload) return;
    setTopoBusy(true);
    setTopoError("");
    try {
      const topo = await analyzeTopo(token, topoPayload);
      setTopoResult(topo);
      await refreshFinalScore(topo);
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "TopoIQ analysis failed");
    } finally {
      setTopoBusy(false);
    }
  }

  useEffect(() => {
    if (topoPayload && !topoResult && !topoBusy) {
      void handleRunTopo();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topoPayload]);

  async function handleTopoPdf() {
    if (!topoPayload) return;
    setTopoPdfBusy(true);
    setTopoError("");
    try {
      const blob = await topoReportPdf(token, topoPayload);
      const safe = (topoPayload.project_name || "topoiq").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_terrain_report.pdf`);
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "Terrain PDF failed");
    } finally {
      setTopoPdfBusy(false);
    }
  }

  async function handleTopoZip() {
    if (!topoPayload) return;
    setTopoZipBusy(true);
    setTopoError("");
    try {
      const blob = await topoExportsZip(token, topoPayload);
      const safe = (topoPayload.project_name || "topoiq").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_topoiq_exports.zip`);
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "CAD ZIP failed");
    } finally {
      setTopoZipBusy(false);
    }
  }

  async function handleRunYield() {
    setYieldBusy(true);
    setYieldError("");
    try {
      setYieldResult(await analyzeYield(token, yieldPayload));
    } catch (err) {
      setYieldError(err instanceof Error ? err.message : "YieldIQ analysis failed");
    } finally {
      setYieldBusy(false);
    }
  }

  async function handleLayoutSweep() {
    if (!boundary || boundary.length < 3) return;
    setLayoutBusy(true);
    setLayoutError("");
    try {
      const res = await workflowLayoutSweep(token, { boundary, include_bom: false });
      setLayoutSweep(res);
      setLayoutFilter("all");
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : "Layout sweep failed");
    } finally {
      setLayoutBusy(false);
    }
  }

  const layoutRows: LayoutSweepRow[] = useMemo(() => {
    if (!layoutSweep?.rows) return [];
    if (layoutFilter === "all") return layoutSweep.rows.filter((r) => r.success);
    return layoutSweep.rows.filter((r) => r.success && r.config_key === layoutFilter);
  }, [layoutFilter, layoutSweep]);

  const layoutConfigKeys = useMemo(() => {
    if (!layoutSweep?.best_by_config) return [];
    return Object.keys(layoutSweep.best_by_config).sort();
  }, [layoutSweep]);

  const scorePill = finalScore?.pvmath_score;
  const verdictLabel = finalScore?.verdict ?? (hasBoundary ? "PENDING TOPOIQ" : "SCREENING ONLY");
  const verdictDetail =
    finalScore?.verdict_detail ??
    (hasBoundary
      ? "Run TopoIQ on your boundary to compute the PVMath score (terrain from grid, not pin sample)."
      : result.terrain_note);

  return (
    <div className="workflow-page">
      <div className="page-intro">
        <h1>Project results</h1>
        <p>{result.project_name}</p>
      </div>

      <div className="verdict-hero">
        <div className="verdict-score">
          {scorePill != null ? (
            <span className="score-pill">{scorePill}</span>
          ) : (
            <span className="score-pill score-pill-pending">—</span>
          )}
          <div>
            <strong>{verdictLabel}</strong>
            <p>{verdictDetail}</p>
          </div>
        </div>
        <div className="coord-pill">
          {result.coordinates.lat.toFixed(4)}°, {result.coordinates.lon.toFixed(4)}°
        </div>
      </div>

      <section className="module-card module-screen">
        <div className="module-head">
          <h2>Site screening</h2>
          <span className="module-tag">Step 1</span>
        </div>
        <p className="hint">{result.terrain_note}</p>
        <div className="metrics">
          {metric(
            "Solar",
            String(result.solar.rating ?? "—"),
            String(result.solar.detail ?? ""),
            result.solar.annual_ghi ? `${result.solar.annual_ghi} kWh/m²/yr` : undefined,
          )}
          {metric(
            "Flood",
            String(result.flood.risk ?? "—"),
            String(result.flood.detail ?? ""),
          )}
          {metric(
            "Grid proximity",
            String(grid.rating ?? "—"),
            String(grid.detail ?? ""),
            grid.found && nearest
              ? `${nearest.name ?? "Substation"} · ${grid.distance_km} km${
                  nearest.voltage ? ` · ${nearest.voltage}` : ""
                }`
              : grid.found === false
                ? `No OSM substation within ${grid.search_radius_km ?? "?"} km`
                : undefined,
          )}
          {metric(
            "Regulatory",
            String(result.regulatory.status ?? "—"),
            String(result.regulatory.note ?? ""),
          )}
          {metric("Capacity", mwp || "—", mwh ? `${mwh} MWh/yr (screening band)` : undefined)}
        </div>
        {grid.disclaimer ? <p className="module-note">{String(grid.disclaimer)}</p> : null}
      </section>

      {result.errors.length > 0 ? (
        <div className="error-banner" style={{ marginTop: "1rem" }}>
          {result.errors.join(" · ")}
        </div>
      ) : null}

      <section className="module-card module-topoiq">
        <div className="module-head">
          <h2>TopoIQ terrain</h2>
          <span className="module-tag">Step 2 · authoritative terrain</span>
        </div>
        {!hasBoundary ? (
          <p className="hint">
            Draw or upload a site boundary on Project input. Terrain slope and the PVMath
            terrain score come only from TopoIQ — not from site screening.
          </p>
        ) : (
          <>
            {topoBusy && !topoResult ? (
              <p className="hint">Running TopoIQ on your boundary grid…</p>
            ) : (
              <button
                className="btn btn-primary"
                type="button"
                onClick={() => void handleRunTopo()}
                disabled={topoBusy}
              >
                {topoBusy ? "Running TopoIQ…" : "Re-run TopoIQ"}
              </button>
            )}
            {topoResult ? (
              <>
                <div className="metrics module-metrics">
                  {metric("Elev Range", `${topoResult.elevation.z_range.toFixed(0)} m`)}
                  {metric("Mean Slope", `${topoResult.slope.mean.toFixed(1)}%`)}
                  {metric("Max Slope", `${topoResult.slope.max.toFixed(1)}%`)}
                  {metric(">5% Area", `${topoResult.slope.pct_over5.toFixed(1)}%`)}
                  {metric(">10% Area", `${topoResult.slope.pct_over10.toFixed(1)}%`)}
                  {metric(
                    "Terrain Score",
                    String(topoResult.terrain_drivers.terrain_score ?? "—"),
                    String(topoResult.terrain_drivers.terrain_score_label ?? ""),
                  )}
                </div>
                <div className="module-note">
                  <strong>Fixed Tilt:</strong> {topoResult.verdict_fixed.label} —{" "}
                  {topoResult.verdict_fixed.detail}
                  <br />
                  <strong>Single-Axis Tracker:</strong> {topoResult.verdict_tracker.label} —{" "}
                  {topoResult.verdict_tracker.detail}
                  <br />
                  <strong>Source:</strong> {topoResult.terrain_source_used}
                </div>
              </>
            ) : null}
            <div className="output-actions module-actions">
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => void handleTopoPdf()}
                disabled={topoPdfBusy || !topoResult}
              >
                {topoPdfBusy ? "Generating…" : "Terrain PDF"}
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => void handleTopoZip()}
                disabled={topoZipBusy || !topoResult}
              >
                {topoZipBusy ? "Preparing…" : "CAD ZIP"}
              </button>
            </div>
          </>
        )}
        {topoError ? <div className="error-banner">{topoError}</div> : null}
      </section>

      <section className="module-card module-yieldiq">
        <div className="module-head">
          <h2>YieldIQ yield matrix</h2>
          <span className="module-tag">Step 3</span>
        </div>
        <button
          className="btn btn-primary"
          type="button"
          onClick={() => void handleRunYield()}
          disabled={yieldBusy}
        >
          {yieldBusy ? "Running YieldIQ…" : "Run YieldIQ"}
        </button>
        {yieldResult ? (
          <div className="yield-table-wrap">
            <table className="yield-table">
              <thead>
                <tr>
                  <th>Configuration</th>
                  <th>Specific Yield</th>
                  <th>PR</th>
                  <th>GCR</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(yieldResult.configs).map(([cfg, payload]) => (
                  <tr key={cfg}>
                    <td>{payload.display_name}</td>
                    <td>{Number(payload.spec_y).toFixed(0)} kWh/kWp/yr</td>
                    <td>{payload.pr != null ? `${Number(payload.pr).toFixed(1)}%` : "—"}</td>
                    <td>{Number(payload.gcr).toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="module-note">{yieldResult.disclosure}</p>
          </div>
        ) : null}
        {yieldError ? <div className="error-banner">{yieldError}</div> : null}
      </section>

      <section className="module-card module-layout">
        <div className="module-head">
          <h2>LayoutIQ — capacity vs pitch</h2>
          <span className="module-tag">Step 4</span>
        </div>
        {!hasBoundary ? (
          <p className="hint">Draw a site boundary to run the layout sweep.</p>
        ) : (
          <>
            <p className="hint">
              Sweeps Fixed Tilt 1P–4P and Single-Axis Tracker 1P–2P across increasing row pitch
              (GCR decreases as pitch increases). Pick a configuration before YieldIQ.
            </p>
            {!topoResult ? (
              <p className="module-note">TopoIQ should finish first — layout uses your boundary polygon.</p>
            ) : null}
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => void handleLayoutSweep()}
              disabled={layoutBusy}
            >
              {layoutBusy ? "Running layout sweep…" : "Run layout sweep"}
            </button>
            {layoutSweep && layoutConfigKeys.length > 0 ? (
              <div className="layout-matrix">
                <div className="layout-filter-row">
                  <button
                    type="button"
                    className={`btn btn-ghost btn-sm${layoutFilter === "all" ? " active" : ""}`}
                    onClick={() => setLayoutFilter("all")}
                  >
                    All
                  </button>
                  {layoutConfigKeys.map((key) => (
                    <button
                      key={key}
                      type="button"
                      className={`btn btn-ghost btn-sm${layoutFilter === key ? " active" : ""}`}
                      onClick={() => setLayoutFilter(key)}
                    >
                      {layoutSweep.best_by_config[key]?.label ?? key}
                    </button>
                  ))}
                </div>
                {layoutFilter !== "all" && layoutSweep.best_by_config[layoutFilter] ? (
                  <p className="module-note">
                    Best for this config:{" "}
                    <strong>{layoutSweep.best_by_config[layoutFilter].dc_kwp} MWp</strong> at pitch{" "}
                    {layoutSweep.best_by_config[layoutFilter].pitch_m} m (GCR{" "}
                    {layoutSweep.best_by_config[layoutFilter].gcr})
                  </p>
                ) : null}
                <table className="yield-table">
                  <thead>
                    <tr>
                      <th>Configuration</th>
                      <th>Pitch (m)</th>
                      <th>GCR</th>
                      <th>Modules</th>
                      <th>DC (MWp)</th>
                      <th>MW/ha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {layoutRows.map((row) => (
                      <tr key={`${row.config_key}-${row.pitch_m}`}>
                        <td>{row.label}</td>
                        <td>{row.pitch_m}</td>
                        <td>{row.gcr.toFixed(2)}</td>
                        <td>{row.total_modules?.toLocaleString() ?? "—"}</td>
                        <td>{row.dc_kwp?.toLocaleString() ?? "—"}</td>
                        <td>{row.mw_per_ha != null ? row.mw_per_ha.toFixed(2) : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="module-note">
                  {layoutSweep.row_count} pitch steps across {layoutSweep.config_count} mount/portrait
                  combinations. Interactive map + layout DXF — next phase.
                </p>
              </div>
            ) : null}
          </>
        )}
        {layoutError ? <div className="error-banner">{layoutError}</div> : null}
      </section>

      <div className="output-actions">
        <button className="btn btn-ghost" type="button" onClick={onEditInput}>
          ← Edit input
        </button>
        <button className="btn btn-primary" type="button" onClick={onNewScreening}>
          New project
        </button>
      </div>

      <details className="raw-json">
        <summary>Technical JSON</summary>
        <pre>{JSON.stringify({ screening: result, topo: topoResult, score: finalScore, layoutSweep }, null, 2)}</pre>
      </details>

      <p className="disclaimer footer-note">
        Screening-grade only — not bankable. Terrain from TopoIQ grid only. Data: PVGIS (JRC),
        routed public DEM, OpenStreetMap.
      </p>
    </div>
  );
}
