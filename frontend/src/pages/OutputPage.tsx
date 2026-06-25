import { useState } from "react";
import { downloadScreeningPdf } from "../lib/api";
import type { GateAnalyzeResponse } from "../types/gate";

interface Props {
  token: string;
  result: GateAnalyzeResponse;
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

export function OutputPage({ token, result, onNewScreening, onEditInput }: Props) {
  const [pdfBusy, setPdfBusy] = useState(false);
  const [pdfError, setPdfError] = useState("");

  const cap = result.capacity as Record<string, unknown>;
  const mwp = cap?.mwp_range as string | undefined;
  const mwh = cap?.mwh_range as string | undefined;
  const layout = result.layout as Record<string, unknown> | null | undefined;

  async function handlePdf() {
    setPdfBusy(true);
    setPdfError("");
    try {
      const blob = await downloadScreeningPdf(token, result);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      const safe = (result.project_name || "screening").replace(/\s+/g, "_");
      a.href = url;
      a.download = `PVMath_${safe}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setPdfError(err instanceof Error ? err.message : "PDF download failed");
    } finally {
      setPdfBusy(false);
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
