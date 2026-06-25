import { useEffect, useMemo, useState } from "react";
import {
  analyzeTopo,
  analyzeYield,
  topoExportsZip,
  topoReportPdf,
  workflowLayoutDetail,
  workflowLayoutDxf,
  workflowLayoutSweep,
  workflowScore,
  workflowTerrainMesh,
} from "../lib/api";
import { LayoutPreviewMap } from "../components/LayoutPreviewMap";
import { Terrain3DView } from "../components/Terrain3DView";
import type { GateAnalyzeRequest } from "../types/gate";
import type { TopoIQAnalyzeRequest, TopoIQAnalyzeResponse, YieldIQAnalyzeResponse } from "../types/topoiq";
import type {
  LayoutSweepRow,
  WorkflowLayoutDetailResponse,
  WorkflowLayoutSweepResponse,
  WorkflowScoreResponse,
  WorkflowScreenResponse,
  WorkflowTerrainMeshResponse,
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
  const [selectedLayoutRow, setSelectedLayoutRow] = useState<LayoutSweepRow | null>(null);
  const [layoutDetailBusy, setLayoutDetailBusy] = useState(false);
  const [layoutDxfBusy, setLayoutDxfBusy] = useState(false);
  const [layoutDetail, setLayoutDetail] = useState<WorkflowLayoutDetailResponse | null>(null);
  const [terrain3DBusy, setTerrain3DBusy] = useState(false);
  const [terrain3D, setTerrain3D] = useState<WorkflowTerrainMeshResponse | null>(null);

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

  const selectedYieldConfigKey = useMemo(() => {
    if (!selectedLayoutRow) return null;
    const tracker = selectedLayoutRow.mount_type === "Single-Axis Tracker";
    const portraitGroup = selectedLayoutRow.n_portrait === 1 ? "1P" : "2P";
    return `${portraitGroup} ${tracker ? "Tracker" : "Fixed"}`;
  }, [selectedLayoutRow]);

  const yieldPayload = useMemo(() => {
    const selectedGcr = selectedLayoutRow?.gcr;
    const selectedIs1P = selectedLayoutRow?.n_portrait === 1;
    return {
      lat: result.coordinates.lat,
      lon: result.coordinates.lon,
      mount_type: selectedLayoutRow?.mount_type || input?.mount_type || "Fixed Tilt",
      gcr_1p: selectedIs1P && selectedGcr ? selectedGcr : 0.35,
      gcr_2p: !selectedIs1P && selectedGcr ? selectedGcr : 0.42,
      soiling_loss: 2.0,
      other_loss: 6.0,
    };
  }, [input?.mount_type, result.coordinates.lat, result.coordinates.lon, selectedLayoutRow]);

  const selectedYieldConfig = selectedYieldConfigKey
    ? yieldResult?.configs[selectedYieldConfigKey]
    : null;
  const selectedAnnualMwh =
    selectedLayoutRow?.dc_kwp && selectedYieldConfig?.spec_y
      ? (selectedLayoutRow.dc_kwp * selectedYieldConfig.spec_y) / 1000
      : null;

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
      setSelectedLayoutRow(null);
      setLayoutDetail(null);
      setTerrain3D(null);
      setYieldResult(null);
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : "Layout sweep failed");
    } finally {
      setLayoutBusy(false);
    }
  }

  function selectedLayoutPayload(row = selectedLayoutRow) {
    if (!boundary || !row) return null;
    return {
      project_name: result.project_name || "LayoutIQ",
      boundary,
      config_key: row.config_key,
      pitch_m: row.pitch_m,
    };
  }

  async function handleLayoutDetail(row = selectedLayoutRow) {
    const payload = selectedLayoutPayload(row);
    if (!payload) return;
    setLayoutDetailBusy(true);
    setLayoutError("");
    try {
      setLayoutDetail(await workflowLayoutDetail(token, payload));
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : "Layout preview failed");
    } finally {
      setLayoutDetailBusy(false);
    }
  }

  async function handleLayoutDxf() {
    const payload = selectedLayoutPayload();
    if (!payload) return;
    setLayoutDxfBusy(true);
    setLayoutError("");
    try {
      const blob = await workflowLayoutDxf(token, payload);
      const safe = (payload.project_name || "LayoutIQ").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_${payload.config_key}_${payload.pitch_m}m_layout.dxf`);
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : "Layout DXF failed");
    } finally {
      setLayoutDxfBusy(false);
    }
  }

  async function handleTerrain3D() {
    if (!boundary || boundary.length < 3) return;
    setTerrain3DBusy(true);
    setLayoutError("");
    try {
      setTerrain3D(await workflowTerrainMesh(token, { boundary, grid_m: 20, max_vertices: 12000 }));
    } catch (err) {
      setLayoutError(err instanceof Error ? err.message : "3D terrain failed");
    } finally {
      setTerrain3DBusy(false);
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
                      <th>Yield input</th>
                    </tr>
                  </thead>
                  <tbody>
                    {layoutRows.map((row) => (
                      <tr
                        key={`${row.config_key}-${row.pitch_m}`}
                        className={
                          selectedLayoutRow?.config_key === row.config_key &&
                          selectedLayoutRow?.pitch_m === row.pitch_m
                            ? "layout-row-selected"
                            : ""
                        }
                      >
                        <td>{row.label}</td>
                        <td>{row.pitch_m}</td>
                        <td>{row.gcr.toFixed(2)}</td>
                        <td>{row.total_modules?.toLocaleString() ?? "—"}</td>
                        <td>{row.dc_kwp?.toLocaleString() ?? "—"}</td>
                        <td>{row.mw_per_ha != null ? row.mw_per_ha.toFixed(2) : "—"}</td>
                        <td>
                          <button
                            type="button"
                            className="btn btn-ghost btn-sm"
                            onClick={() => {
                              setSelectedLayoutRow(row);
                              setLayoutDetail(null);
                              setTerrain3D(null);
                              setYieldResult(null);
                              void handleLayoutDetail(row);
                            }}
                          >
                            {selectedLayoutRow?.config_key === row.config_key &&
                            selectedLayoutRow?.pitch_m === row.pitch_m
                              ? "Selected"
                              : "Select"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="module-note">
                  {layoutSweep.row_count} pitch steps across {layoutSweep.config_count} mount/portrait
                  combinations. Select one row, then run YieldIQ for its GCR and mount type.
                </p>
                {selectedLayoutRow ? (
                  <div className="layout-preview-panel">
                    <div className="layout-preview-head">
                      <div>
                        <strong>Selected web layout</strong>
                        <p>
                          {selectedLayoutRow.label} · {selectedLayoutRow.pitch_m} m pitch · GCR{" "}
                          {selectedLayoutRow.gcr.toFixed(2)}
                        </p>
                      </div>
                      <div className="layout-preview-actions">
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => void handleLayoutDetail()}
                          disabled={layoutDetailBusy}
                        >
                          {layoutDetailBusy ? "Loading preview…" : "Refresh preview"}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => void handleLayoutDxf()}
                          disabled={layoutDxfBusy}
                        >
                          {layoutDxfBusy ? "Preparing DXF…" : "Download layout DXF"}
                        </button>
                        <button
                          type="button"
                          className="btn btn-ghost btn-sm"
                          onClick={() => void handleTerrain3D()}
                          disabled={terrain3DBusy}
                        >
                          {terrain3DBusy ? "Building 3D…" : "3D terrain"}
                        </button>
                      </div>
                    </div>
                    {layoutDetail ? (
                      <>
                        <LayoutPreviewMap
                          center={{ lat: result.coordinates.lat, lon: result.coordinates.lon }}
                          layoutGeoJson={layoutDetail.geojson}
                        />
                        <p className="module-note">
                          Preview contains {layoutDetail.total_rows.toLocaleString()} PV rows and{" "}
                          {layoutDetail.total_modules.toLocaleString()} modules. DXF uses the same
                          row polygons in local metric coordinates.
                        </p>
                      </>
                    ) : (
                      <p className="module-note">
                        {layoutDetailBusy ? "Generating row polygons…" : "Select or refresh to load row polygons."}
                      </p>
                    )}
                    {terrain3D ? (
                      <>
                        <Terrain3DView mesh={terrain3D} />
                        <p className="module-note">
                          3D terrain uses a coarse TopoIQ DEM mesh from {terrain3D.terrain_source_used}.
                          PV row draping and shading-object ray tracing are the next graphics layer.
                        </p>
                      </>
                    ) : null}
                  </div>
                ) : null}
              </div>
            ) : null}
          </>
        )}
        {layoutError ? <div className="error-banner">{layoutError}</div> : null}
      </section>

      <section className="module-card module-yieldiq">
        <div className="module-head">
          <h2>YieldIQ — selected layout yield</h2>
          <span className="module-tag">Step 5</span>
        </div>
        {selectedLayoutRow ? (
          <p className="hint">
            Using {selectedLayoutRow.label}, {selectedLayoutRow.pitch_m} m pitch, GCR{" "}
            {selectedLayoutRow.gcr.toFixed(2)}, and {selectedLayoutRow.dc_kwp?.toLocaleString()} kWp
            DC from LayoutIQ.
          </p>
        ) : (
          <p className="hint">Select a LayoutIQ row first to run YieldIQ with the chosen pitch and GCR.</p>
        )}
        <button
          className="btn btn-primary"
          type="button"
          onClick={() => void handleRunYield()}
          disabled={yieldBusy || !selectedLayoutRow}
        >
          {yieldBusy ? "Running YieldIQ…" : "Run YieldIQ for selected layout"}
        </button>
        {yieldResult ? (
          <div className="yield-table-wrap">
            {selectedYieldConfig && selectedAnnualMwh != null ? (
              <div className="selected-yield-summary">
                <strong>Selected layout estimate:</strong>{" "}
                {selectedAnnualMwh.toFixed(0)} MWh/yr at{" "}
                {Number(selectedYieldConfig.spec_y).toFixed(0)} kWh/kWp/yr.
              </div>
            ) : null}
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
            <p className="module-note">
              {yieldResult.disclosure} For FT 3P/4P, YieldIQ uses the selected GCR through the
              fixed-tilt PVGIS profile while LayoutIQ keeps the exact portrait count for capacity.
            </p>
          </div>
        ) : null}
        {yieldError ? <div className="error-banner">{yieldError}</div> : null}
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
        <pre>
          {JSON.stringify(
            { screening: result, topo: topoResult, score: finalScore, layoutSweep, layoutDetail },
            null,
            2,
          )}
        </pre>
      </details>

      <p className="disclaimer footer-note">
        Screening-grade only — not bankable. Terrain from TopoIQ grid only. Data: PVGIS (JRC),
        routed public DEM, OpenStreetMap.
      </p>
    </div>
  );
}
