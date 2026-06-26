import type { PipelineModule, PipelineStage } from "../types/workflow";
import { PIPELINE_MODULES } from "../types/workflow";

interface Props {
  current: PipelineStage;
  interactive?: boolean;
  unlocked?: PipelineStage[];
  completed?: Partial<Record<PipelineStage, boolean>>;
  onNavigate?: (stage: PipelineStage) => void;
}

export function WorkflowPipeline({
  current,
  interactive = false,
  unlocked,
  completed = {},
  onNavigate,
}: Props) {
  const currentIdx = PIPELINE_MODULES.findIndex((m) => m.id === current);
  const unlockedSet = new Set(unlocked ?? PIPELINE_MODULES.filter((m) => !m.future).map((m) => m.id));

  return (
    <div className="workflow-pipeline-wrap">
      <div className="workflow-pipeline-head">
        <span className="workflow-mode-badge">Preliminary study</span>
        <span className="workflow-pipeline-hint">Automated screening workflow</span>
      </div>
      <nav className="workflow-pipeline" aria-label="PVMath workflow">
        {PIPELINE_MODULES.map((mod: PipelineModule, i) => {
          const done = completed[mod.id] || (i < currentIdx && !mod.future);
          const active = mod.id === current;
          const reachable =
            !mod.future && interactive && onNavigate && unlockedSet.has(mod.id);
          return (
            <div key={mod.id} className="workflow-pipeline-segment">
              <button
                type="button"
                className={`workflow-pipeline-node${active ? " active" : ""}${
                  done ? " done" : ""
                }${mod.future ? " future" : ""}${reachable ? "" : " locked"}`}
                disabled={!reachable}
                onClick={() => reachable && onNavigate?.(mod.id)}
                aria-current={active ? "step" : undefined}
                title={mod.future ? "Coming soon" : undefined}
              >
                <span className="workflow-pipeline-dot">
                  {done && !active ? "✓" : mod.future ? "·" : i + 1}
                </span>
                <span className="workflow-pipeline-label">
                  {mod.label}
                  {mod.future ? <span className="workflow-future-tag">Soon</span> : null}
                </span>
              </button>
              {i < PIPELINE_MODULES.length - 1 ? (
                <div
                  className={`workflow-pipeline-connector${
                    i < currentIdx || completed[PIPELINE_MODULES[i + 1].id] ? " done" : ""
                  }`}
                  aria-hidden
                />
              ) : null}
            </div>
          );
        })}
      </nav>
    </div>
  );
}
