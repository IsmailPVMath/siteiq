import { useMemo, useState } from "react";
import {
  analyzeTopo,
  analyzeYield,
  downloadScreeningPdf,
  topoExportsZip,
  topoReportPdf,
} from "../lib/api";
import type { GateAnalyzeRequest, GateAnalyzeResponse } from "../types/gate";
import type { TopoIQAnalyzeRequest, TopoIQAnalyzeResponse, YieldIQAnalyzeResponse } from "../types/topoiq";

interface Props {
  token: string;
  result: GateAnalyzeResponse;
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
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState("");
  const [topoBusy, setTopoBusy] = useState(false);
  const [topoError, setTopoError] = useState("");
  const [topoResult, setTopoResult] = useState<TopoIQAnalyzeResponse | null>(null);
  const [topoPdfBusy, setTopoPdfBusy] = useState(false);
  const [topoZipBusy, setTopoZipBusy] = useState(false);
  const [yieldBusy, setYieldBusy] = useState(false);
  const [yieldError, setYieldError] = useState("");
  const [yieldResult, setYieldResult] = useState<YieldIQAnalyzeResponse | null>(null);

  const cap = result.capacity as Record<string, unknown>;
  const mwp = cap?.mwp_range as string | undefined;
  const mwh = cap?.mwh_range as string | undefined;
  const layout = result.layout as Record<string, unknown> | null | undefined;
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

  async function handlePdf() {
    setPdfBusy(true);
    setPdfError("");
    try {
      const blob = await downloadScreeningPdf(token, result);
      const safe = (result.project_name || "screening").replace(/\s+/g, "_");
      saveBlob(blob, `PVMath_${safe}.pdf`);
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : "PDF download failed");
    } finally {
      setPdfBusy(false);
    }
  }

  async function handleRunTopo() {
    if (!topoPayload) return;
    setTopoBusy(true);
    setTopoError("");
    try {
      setTopoResult(await analyzeTopo(token, topoPayload));
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "TopoIQ analysis failed");
    } finally {
      setTopoBusy(false);
    }
  }

  async function handleTopoPdf() {
    if (!topoPayload) return;
    setTopoPdfBusy(true);
    setTopoError("");
    try {
      const blob = await topoReportPdf(token, topoPayload);
      const safe = (topoPayload.project_name || "topoiq").replace(/\s+/g, "_");
      saveBlob(blob, `${safe}_terrain_report.pdf`);
    } catch (err) {
      setTopoError(err instanceof Error ? err.message : "TopoIQ PDF download failed");
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
      setTopoError(err instanceof Error ? err.message : "TopoIQ CAD ZIP download failed");
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

  return (
    <div className="workflow-page">
      <div className="page-intro">
        <h1>Screening results</h1>
        <p>{result.project_name}</p>
      </div>

      <div className="verdict-hero">
        <div className="verdict-score">
          {result.pvmath_score != null ? (
            <span className="score-pill">{result.pvmath_score}</span>
          ) : null}
          <div>
            <strong>{result.verdict}</strong>
            <p>{result.verdict_detail}</p>
          </div>
        </div>
        <div className="coord-pill">
          {result.coordinates.lat.toFixed(4)}°, {result.coordinates.lon.toFixed(4)}°
        </div>
      </div>

      <div className="metrics">
        {metric(
          "Solar",
          String(result.solar.rating ?? "—"),
          String(result.solar.detail ?? ""),
          result.solar.annual_ghi
            ? `${result.solar.annual_ghi} kWh/m²/yr`
            : undefined,
        )}
        {metric(
          "Terrain",
          String(result.terrain.rating ?? "—"),
          String(result.terrain.detail ?? ""),
          `${result.terrain.boundary_sampled ? "Boundary sample" : "Pin sample"}${
            result.terrain.terrain_source_used
              ? ` · ${String(result.terrain.terrain_source_used)}`
              : ""
          }`,
        )}
        {metric(
          "Flood",
          String(result.flood.risk ?? "—"),
          String(result.flood.detail ?? ""),
        )}
        {metric(
          "Regulatory",
          String(result.regulatory.status ?? "—"),
          String(result.regulatory.note ?? ""),
        )}
        {metric("Capacity", mwp || "—", mwh ? `${mwh} MWh/yr (screening)` : undefined)}
        {layout
          ? metric(
              "Layout",
              `${layout.total_modules ?? "—"} modules`,
              layout.dc_kwp ? `${layout.dc_kwp} MWp DC (indicative)` : undefined,
            )
          : null}
      </div>

      {result.errors.length > 0 ? (
        <div className="error-banner" style={{ marginTop: "1rem" }}>
          {result.errors.join(" · ")}
        </div>
      ) : null}
      {pdfError ? <div className="error-banner">{pdfError}</div> : null}

      <section className="module-card module-topoiq">
        <div className="module-head">
          <h2>TopoIQ terrain analysis</h2>
          <span className="module-tag">Module 02</span>
        </div>
        {!hasBoundary ? (
          <p className="hint">
            TopoIQ requires a site boundary polygon. Go to Project input and draw the site boundary on
            the map (or upload KML/KMZ), then rerun screening.
          </p>
        ) : (
          <>
            <button
              className="btn btn-primary"
              type="button"
              onClick={() => void handleRunTopo()}
              disabled={topoBusy}
            >
              {topoBusy ? "Running TopoIQ…" : "Run TopoIQ"}
            </button>
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
                    String((topoResult.terrain_drivers.terrain_score as number | undefined) ?? "—"),
                    String(
                      (topoResult.terrain_drivers.terrain_score_label as string | undefined) ?? "",
                    ),
                  )}
                </div>
                <div className="module-note">
                  <strong>Fixed Tilt:</strong> {topoResult.verdict_fixed.label} -{" "}
                  {topoResult.verdict_fixed.detail}
                  <br />
                  <strong>Single-Axis Tracker:</strong> {topoResult.verdict_tracker.label} -{" "}
                  {topoResult.verdict_tracker.detail}
                  <br />
                  <strong>Terrain source:</strong> {topoResult.terrain_source_used}
                </div>
              </>
            ) : null}
            <div className="output-actions module-actions">
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => void handleTopoPdf()}
                disabled={topoPdfBusy || !hasBoundary}
              >
                {topoPdfBusy ? "Generating Terrain PDF…" : "Download Terrain PDF"}
              </button>
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => void handleTopoZip()}
                disabled={topoZipBusy || !hasBoundary}
              >
                {topoZipBusy ? "Preparing CAD ZIP…" : "Download CAD ZIP"}
              </button>
            </div>
          </>
        )}
        {topoError ? <div className="error-banner">{topoError}</div> : null}
      </section>

      <section className="module-card module-yieldiq">
        <div className="module-head">
          <h2>YieldIQ energy yield analysis</h2>
          <span className="module-tag">Module 03</span>
        </div>
        <p className="hint">
          Uses site pin coordinates with PVGIS 4-configuration comparison (1P/2P Fixed Tilt and
          Single-Axis Tracker).
        </p>
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

      <div className="output-actions">
        <button className="btn btn-ghost" type="button" onClick={onEditInput}>
          ← Edit input
        </button>
        <button
          className="btn btn-ghost"
          type="button"
          onClick={() => void handlePdf()}
          disabled={pdfBusy}
        >
          {pdfBusy ? "Generating PDF…" : "Download PDF"}
        </button>
        <button className="btn btn-primary" type="button" onClick={onNewScreening}>
          New screening
        </button>
      </div>

      <details className="raw-json">
        <summary>Technical JSON (for engineers)</summary>
        <pre>{JSON.stringify(result, null, 2)}</pre>
      </details>

      <p className="disclaimer footer-note">
        Screening-grade only — not bankable. Data: PVGIS (JRC), routed public DEM source,
        OpenStreetMap.
      </p>
    </div>
  );
}
