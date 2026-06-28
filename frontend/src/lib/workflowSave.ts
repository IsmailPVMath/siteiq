import { draftToGateRequest, draftToProjectPayload, gateRequestToDraft, projectRecordToDraft } from "./projectSetup";
import type { ProjectPayload, ProjectRecord } from "./api";
import { partialUpdateProject } from "./api";
import type { GateAnalyzeRequest } from "../types/gate";
import type { TerrainIQAnalyzeResponse } from "../types/terrainiq";
import type { OutputModuleStage, WorkflowScoreResponse, WorkflowScreenResponse } from "../types/workflow";
import {
  layoutIQToWorkflowFields,
  parseLayoutIQSnapshot,
  type LayoutIQSnapshot,
} from "./layoutIQSettings";

export interface WorkflowRestore {
  projectId: string;
  input: GateAnalyzeRequest;
  screening: WorkflowScreenResponse;
  lastStage: OutputModuleStage;
  topo?: TerrainIQAnalyzeResponse | null;
  finalScore?: WorkflowScoreResponse | null;
  gisSetbacks?: Record<string, number> | null;
  layoutSettings?: LayoutIQSnapshot | null;
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
  layoutSettings?: LayoutIQSnapshot | null,
): ProjectPayload {
  const draft = gateRequestToDraft(input);
  if (screening.project_name) draft.project_info.name = screening.project_name;
  const base = draftToProjectPayload(draft);
  const layoutFields = layoutSettings ? layoutIQToWorkflowFields(layoutSettings) : {};
  return {
    ...base,
    workflow: {
      ...base.workflow,
      ...layoutFields,
      last_stage: lastStage,
      screening_snapshot: screening as unknown as Record<string, unknown>,
      topo_snapshot: slimTopoSnapshot(topo),
      final_score_snapshot: (finalScore ?? null) as unknown as Record<string, unknown> | null,
      gis_setbacks_m: gisSetbacks ?? null,
      layout_settings_snapshot: (layoutSettings ?? null) as unknown as Record<string, unknown> | null,
      saved_at: new Date().toISOString(),
    },
  };
}

/** Small workflow-only patch for step transitions (no boundary re-upload). */
export function buildWorkflowProgressPatch(
  lastStage: OutputModuleStage,
  extras?: {
    topo?: TerrainIQAnalyzeResponse | null;
    finalScore?: WorkflowScoreResponse | null;
    gisSetbacks?: Record<string, number> | null;
    layoutSettings?: LayoutIQSnapshot | null;
  },
): Partial<ProjectPayload> {
  const layoutFields = extras?.layoutSettings ? layoutIQToWorkflowFields(extras.layoutSettings) : {};
  return {
    workflow: {
      ...layoutFields,
      last_stage: lastStage,
      topo_snapshot: slimTopoSnapshot(extras?.topo),
      final_score_snapshot: (extras?.finalScore ?? null) as unknown as Record<string, unknown> | null,
      gis_setbacks_m: extras?.gisSetbacks ?? null,
      layout_settings_snapshot: (extras?.layoutSettings ?? null) as unknown as Record<string, unknown> | null,
      saved_at: new Date().toISOString(),
    },
  };
}

/** Fast save when the project row already exists — workflow progress only. */
export async function persistWorkflowProgress(
  token: string,
  projectId: string,
  lastStage: OutputModuleStage,
  extras?: {
    topo?: TerrainIQAnalyzeResponse | null;
    finalScore?: WorkflowScoreResponse | null;
    gisSetbacks?: Record<string, number> | null;
    layoutSettings?: LayoutIQSnapshot | null;
  },
): Promise<string> {
  const patch = buildWorkflowProgressPatch(lastStage, extras);
  await partialUpdateProject(token, projectId, patch);
  return projectId;
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
    layoutSettings?: LayoutIQSnapshot | null;
  },
): Promise<string> {
  const payload = buildWorkflowSavePayload(
    input,
    screening,
    lastStage,
    extras?.topo,
    extras?.finalScore,
    extras?.gisSetbacks,
    extras?.layoutSettings,
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
    layoutSettings: parseLayoutIQSnapshot(wf.layout_settings_snapshot),
  };
}
