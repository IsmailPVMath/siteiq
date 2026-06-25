import type { GateAnalyzeResponse } from "../types/gate";

interface Props {
  result: GateAnalyzeResponse | null;
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

export function ResultsPanel({ result }: Props) {
  if (!result) {
    return (
      <div className="card">
        <h2>Results</h2>
        <p className="hint">Run an analysis to see solar, terrain, regulatory, and verdict.</p>
      </div>
    );
  }

  const cap = result.capacity as Record<string, unknown>;
  const mwp = cap?.mwp_range as string | undefined;
  const mwh = cap?.mwh_range as string | undefined;

  return (
    <div className="card">
      <h2>Results — {result.project_name}</h2>
      <div className="verdict">
        <strong>{result.verdict}</strong>
        <p style={{ margin: "0.4rem 0 0" }}>{result.verdict_detail}</p>
        {result.pvmath_score != null ? (
          <p className="hint">PVMath score: {result.pvmath_score}</p>
        ) : null}
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
        )}
        {metric(
          "Flood",
          String(result.flood.rating ?? result.flood.risk ?? "—"),
          String(result.flood.detail ?? ""),
        )}
        {metric(
          "Regulatory",
          String(result.regulatory.status ?? result.regulatory.rating ?? "—"),
          String(result.regulatory.note ?? result.regulatory.summary ?? ""),
        )}
        {metric("Capacity", mwp || "—", mwh ? `${mwh} MWh/yr (screening)` : undefined)}
      </div>

      {result.errors.length > 0 ? (
        <div className="error-banner" style={{ marginTop: "1rem" }}>
          {result.errors.join(" · ")}
        </div>
      ) : null}

      <details style={{ marginTop: "1rem" }}>
        <summary className="hint" style={{ cursor: "pointer" }}>
          Raw JSON response
        </summary>
        <pre
          style={{
            fontSize: "0.72rem",
            overflow: "auto",
            background: "#f8faf8",
            padding: "0.75rem",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}
        >
          {JSON.stringify(result, null, 2)}
        </pre>
      </details>
    </div>
  );
}
