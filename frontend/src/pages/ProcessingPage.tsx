import { useEffect, useState } from "react";
import { PROCESSING_STAGES } from "../types/workflow";

interface Props {
  projectName: string;
}

export function ProcessingPage({ projectName }: Props) {
  const [stageIndex, setStageIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setStageIndex((i) => Math.min(i + 1, PROCESSING_STAGES.length - 1));
    }, 4500);
    return () => window.clearInterval(timer);
  }, []);

  return (
    <div className="workflow-page workflow-page-center">
      <div className="processing-card card">
        <div className="processing-spinner" aria-hidden />
        <h1>Running site screening</h1>
        <p className="processing-project">{projectName}</p>
        <p className="hint">
          Fetching PVGIS solar data, flood heuristic, and regulatory pointers. Terrain
          slope is assessed separately in TopoIQ on your boundary.
        </p>

        <ol className="processing-list">
          {PROCESSING_STAGES.map((label, i) => {
            const state =
              i < stageIndex ? "done" : i === stageIndex ? "active" : "pending";
            return (
              <li key={label} className={`processing-step ${state}`}>
                <span className="processing-step-icon">
                  {state === "done" ? "✓" : state === "active" ? "…" : ""}
                </span>
                {label}
              </li>
            );
          })}
        </ol>

        <p className="disclaimer">
          Screening-grade outputs only — not bankable engineering.
        </p>
      </div>
    </div>
  );
}
