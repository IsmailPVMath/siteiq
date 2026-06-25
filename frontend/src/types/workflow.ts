export type WorkflowStep = "input" | "processing" | "output";

export const WORKFLOW_STEPS: { id: WorkflowStep; label: string }[] = [
  { id: "input", label: "Project input" },
  { id: "processing", label: "Screening" },
  { id: "output", label: "Results" },
];

export const PROCESSING_STAGES = [
  "Solar resource (PVGIS)",
  "Terrain & slope",
  "Flood screening",
  "Regulatory guidance",
  "Capacity estimate",
  "Yield cross-check",
] as const;
