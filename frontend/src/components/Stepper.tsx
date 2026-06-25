import type { WorkflowStep } from "../types/workflow";
import { WORKFLOW_STEPS } from "../types/workflow";

interface Props {
  current: WorkflowStep;
}

export function Stepper({ current }: Props) {
  const idx = WORKFLOW_STEPS.findIndex((s) => s.id === current);

  return (
    <nav className="stepper" aria-label="Workflow progress">
      {WORKFLOW_STEPS.map((step, i) => {
        const done = i < idx;
        const active = i === idx;
        return (
          <div
            key={step.id}
            className={`stepper-item${active ? " active" : ""}${done ? " done" : ""}`}
          >
            <div className="stepper-dot">{done ? "✓" : i + 1}</div>
            <span className="stepper-label">{step.label}</span>
            {i < WORKFLOW_STEPS.length - 1 ? <div className="stepper-line" /> : null}
          </div>
        );
      })}
    </nav>
  );
}
