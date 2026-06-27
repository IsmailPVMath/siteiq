import { draftToGateRequest, draftToProjectPayload, gateRequestToDraft, projectRecordToDraft } from "./projectSetup";
import type { ProjectPayload, ProjectRecord } from "./api";
import type { GateAnalyzeRequest } from "../types/gate";
import type { TerrainIQAnalyzeResponse } from "../types/terrainiq";
import type { OutputModuleStage, WorkflowScoreResponse, WorkflowScreenResponse } from "../types/workflow";

export interface WorkflowRestore {
  projectId: string;
  input: GateAnalyzeRequest;
  screening: WorkflowScreenResponse;
  lastStage: OutputModuleStage;
  topo?: TerrainIQAnalyzeResponse | null;
  finalScore?: WorkflowScoreResponse | null;
  gisSetbacks?: Record<string, number> | null;
}

export function slimTopoSnapshot(topo: TerrainIQAnalyzeResponse | null | undefined): Record<string, unknown> | null {
  if (!topo) return null;
  const { extras: _extras, terrain_source: _ts, ...rest } = topo as TerrainIQAnalyzeResponse & {
    extras?: unknown;
    terrain_source?: unknown;
  };
  return rest as unknown as Record<string, unknown>;
}

export function buildWorkflowSavePayload(
  input: GateAnalyzeRequest,
  screening: WorkflowScreenResponse,
  lastStage: OutputModuleStage,
  topo?: TerrainIQAnalyzeResponse | null,
  finalScore?: WorkflowScoreResponse | null,
  gisSetbacks?: Record<string, number> | null,
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
      topo_snapshot: slimTopoSnapshot(topo),
      final_score_snapshot: (finalScore ?? null) as unknown as Record<string, unknown> | null,
      gis_setbacks_m: gisSetbacks ?? null,
      saved_at: new Date().toISOString(),
    },
  };
}

/** Persist full project geometry + workflow snapshots (not workflow-only partial patch). */
export async function persistWorkflowProject(
  token: string,
  projectId: string | undefined,
  input: GateAnalyzeRequest,
  screening: WorkflowScreenResponse,
  lastStage: OutputModuleStage,
  createProject: (token: string, body: ProjectPayload) => Promise<ProjectRecord>,
  updateProject: (token: string, id: string, body: ProjectPayload) => Promise<ProjectRecord>,
  extras?: {
    topo?: TerrainIQAnalyzeResponse | null;
    finalScore?: WorkflowScoreResponse | null;
    gisSetbacks?: Record<string, number> | null;
  },
): Promise<string> {
  const payload = buildWorkflowSavePayload(
    input,
    screening,
    lastStage,
    extras?.topo,
    extras?.finalScore,
    extras?.gisSetbacks,
  );
  const row = projectId
    ? await updateProject(token, projectId, payload)
    : await createProject(token, payload);
  return row.id;
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
    topo: (wf.topo_snapshot as TerrainIQAnalyzeResponse | null) ?? null,
    finalScore: (wf.final_score_snapshot as WorkflowScoreResponse | null) ?? null,
    gisSetbacks: (wf.gis_setbacks_m as Record<string, number> | null) ?? null,
  };
}
