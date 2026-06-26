import { draftToGateRequest, draftToProjectPayload, gateRequestToDraft, projectRecordToDraft } from "./projectSetup";
import type { ProjectPayload, ProjectRecord } from "./api";
import type { GateAnalyzeRequest } from "../types/gate";
import type { TopoIQAnalyzeResponse } from "../types/topoiq";
import type { OutputModuleStage, WorkflowScoreResponse, WorkflowScreenResponse } from "../types/workflow";

export interface WorkflowRestore {
  projectId: string;
  input: GateAnalyzeRequest;
  screening: WorkflowScreenResponse;
  lastStage: OutputModuleStage;
  topo?: TopoIQAnalyzeResponse | null;
  finalScore?: WorkflowScoreResponse | null;
}

export function buildWorkflowSavePayload(
  input: GateAnalyzeRequest,
  screening: WorkflowScreenResponse,
  lastStage: OutputModuleStage,
  topo?: TopoIQAnalyzeResponse | null,
  finalScore?: WorkflowScoreResponse | null,
): ProjectPayload {
  const draft = gateRequestToDraft(input);
  if (screening.project_name) draft.project_info.name = screening.project_name;
  const base = draftToProjectPayload(draft);
  return {
    ...base,
    workflow: {
      ...base.workflow,
      last_stage: lastStage,
      screening_snapshot: screening as unknown as Record<string, unknown>,
      topo_snapshot: (topo ?? null) as unknown as Record<string, unknown> | null,
      final_score_snapshot: (finalScore ?? null) as unknown as Record<string, unknown> | null,
      saved_at: new Date().toISOString(),
    },
  };
}

export function restoreWorkflowFromRecord(row: ProjectRecord): WorkflowRestore | null {
  const wf = (row.project_data?.workflow ?? {}) as Record<string, unknown>;
  const screening = wf.screening_snapshot as WorkflowScreenResponse | undefined;
  const lastStage = wf.last_stage as OutputModuleStage | undefined;
  if (!screening || !lastStage) return null;
  const input = draftToGateRequest(projectRecordToDraft(row));
  return {
    projectId: row.id,
    input,
    screening,
    lastStage,
    topo: (wf.topo_snapshot as TopoIQAnalyzeResponse | null) ?? null,
    finalScore: (wf.final_score_snapshot as WorkflowScoreResponse | null) ?? null,
  };
}
