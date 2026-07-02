import type { GateAnalyzeRequest, GateAnalyzeResponse, MeResponse } from "../types/gate";
import type { ProjectSetupValidateResponse } from "../types/projectSetup";
import type {
  TerrainIQAnalyzeRequest,
  TerrainIQAnalyzeResponse,
  YieldIQAnalyzeRequest,
  YieldIQAnalyzeResponse,
} from "../types/terrainiq";
import type {
  WorkflowGisAnalysisRequest,
  WorkflowGisAnalysisResponse,
  WorkflowLayoutDetailRequest,
  WorkflowLayoutDetailResponse,
  WorkflowLayoutMatrixResponse,
  WorkflowLayoutSweepRequest,
  WorkflowLayoutSweepResponse,
  WorkflowPvmathReportRequest,
  WorkflowProjectPackageRequest,
  WorkflowScoreResponse,
  WorkflowScreenRequest,
  WorkflowScreenResponse,
  WorkflowTerrainMeshRequest,
  WorkflowTerrainMeshResponse,
} from "../types/workflow";
import type * as GeoJSON from "geojson";

import { getApiUrl } from "./apiBase";

let tokenRefresher: (() => Promise<string | null>) | null = null;

export function setTokenRefresher(fn: (() => Promise<string | null>) | null) {
  tokenRefresher = fn;
}

// A raw fetch rejection (no HTTP response) is usually transient — a Railway
// redeploy/cold-start finishing or a brief network blip. A production deploy
// can take well over a second, so retry a few times with increasing backoff
// (~0.8s + 2s + 4s ≈ 7s total) to ride out a redeploy window before surfacing
// the error. Only raw rejections are retried; a real HTTP error still returns.
const RETRY_DELAYS_MS = [800, 2000, 4000];
const JOB_POLL_MS = 1500;
const JOB_TIMEOUT_MS = 10 * 60 * 1000;

async function fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
  let lastErr: unknown;
  for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
    try {
      return await fetch(url, init);
    } catch (err) {
      lastErr = err;
      const delay = RETRY_DELAYS_MS[attempt];
      if (delay === undefined) break;
      await new Promise((r) => setTimeout(r, delay));
    }
  }
  throw lastErr;
}

async function apiFetch<T>(
  path: string,
  token: string,
  init?: RequestInit,
  retried = false,
): Promise<T> {
  let res: Response;
  try {
    res = await fetchWithRetry(`${getApiUrl()}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${token}`,
        ...(init?.body && !(init.body instanceof FormData)
          ? { "Content-Type": "application/json" }
          : {}),
        ...init?.headers,
      },
    });
  } catch (err) {
    // Network-level failure (Safari: "Load failed", Chrome: "Failed to fetch").
    // Retry once with a freshly refreshed token in case the session went stale
    // mid-request, otherwise surface an actionable message.
    if (!retried && tokenRefresher) {
      const fresh = await tokenRefresher();
      if (fresh) return apiFetch<T>(path, fresh, init, true);
    }
    throw new Error(
      "Network error — could not reach the PVMath server. Check your connection and try again.",
    );
  }

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
  }

  if (res.status === 401 && !retried && tokenRefresher) {
    const fresh = await tokenRefresher();
    if (fresh) return apiFetch<T>(path, fresh, init, true);
  }

  if (!res.ok) {
    const detail =
      typeof data === "object" && data && "detail" in data
        ? String((data as { detail: unknown }).detail)
        : `HTTP ${res.status}`;
    throw new Error(detail);
  }

  return data as T;
}

export function fetchMe(token: string) {
  return apiFetch<MeResponse>("/api/v1/me", token);
}

export function changePassword(token: string, currentPassword: string, newPassword: string) {
  return apiFetch<{ success: boolean; message: string }>("/api/v1/me/password", token, {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
}

export async function downloadEngineeringManual(token: string): Promise<Blob> {
  const res = await fetch(`${getApiUrl()}/api/v1/me/engineering-manual`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error((err as { detail?: string }).detail || "Manual download failed");
  }
  return res.blob();
}

export function runWorkflowScreen(token: string, body: WorkflowScreenRequest) {
  return apiFetch<WorkflowScreenResponse>("/api/v1/workflow/screen", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function workflowGisAnalysis(token: string, body: WorkflowGisAnalysisRequest) {
  return apiFetch<WorkflowGisAnalysisResponse>("/api/v1/workflow/gis-analysis", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function workflowScore(
  token: string,
  body: {
    score_components: Record<string, number>;
    terrain_score: number;
    yield_spec_y?: number;
    yield_cf?: number | null;
    lat?: number;
    lon?: number;
    country?: string;
    terrain_confirmed?: boolean;
    capacity_mwp?: number;
    economic_score?: number;
  },
) {
  return apiFetch<WorkflowScoreResponse>("/api/v1/workflow/score", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function workflowLayoutSweep(token: string, body: WorkflowLayoutSweepRequest) {
  return apiFetch<WorkflowLayoutSweepResponse>(
    "/api/v1/workflow/layout-sweep",
    token,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export async function workflowLayoutSweepJob(token: string, body: WorkflowLayoutSweepRequest) {
  const started = await apiFetch<JobStartResponse>("/api/v1/workflow/layout-sweep-job", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return pollJob<WorkflowLayoutSweepResponse>(
    token,
    (jobId) => `/api/v1/workflow/layout-sweep-job/${jobId}`,
    started.job_id,
  );
}

export function workflowLayoutDetail(token: string, body: WorkflowLayoutDetailRequest) {
  return apiFetch<WorkflowLayoutDetailResponse>("/api/v1/workflow/layout-detail", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface LayoutImportDxfParams {
  file: File;
  ref_lat: number;
  ref_lon: number;
  config_key?: string;
  pitch_m?: number;
  module_wp?: number;
  modules_per_string?: number;
  tracker_string_options?: string;
  project_name?: string;
}

export function workflowImportLayoutDxf(token: string, params: LayoutImportDxfParams) {
  const form = new FormData();
  form.append("file", params.file);
  form.append("ref_lat", String(params.ref_lat));
  form.append("ref_lon", String(params.ref_lon));
  form.append("config_key", params.config_key ?? "SAT_2P");
  form.append("pitch_m", String(params.pitch_m ?? 6.5));
  form.append("module_wp", String(params.module_wp ?? 550));
  form.append("modules_per_string", String(params.modules_per_string ?? 28));
  form.append("tracker_string_options", params.tracker_string_options ?? "8,7,6,5,4,3");
  form.append("project_name", params.project_name ?? "Imported layout");
  return apiFetch<WorkflowLayoutDetailResponse>("/api/v1/workflow/layout-import-dxf", token, {
    method: "POST",
    body: form,
  });
}

export function workflowLayoutDxf(token: string, body: WorkflowLayoutDetailRequest) {
  return downloadBlob("/api/v1/workflow/layout-dxf", token, body, "application/dxf");
}

export function workflowTerrainMesh(token: string, body: WorkflowTerrainMeshRequest) {
  return apiFetch<WorkflowTerrainMeshResponse>("/api/v1/workflow/terrain-mesh", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

interface JobStartResponse {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
}

interface JobStatusResponse<T> extends JobStartResponse {
  created_at: number;
  updated_at: number;
  error?: string | null;
  result?: T | null;
}

async function pollJob<T>(
  token: string,
  statusPath: (jobId: string) => string,
  jobId: string,
): Promise<T> {
  const started = Date.now();
  while (Date.now() - started < JOB_TIMEOUT_MS) {
    const status = await apiFetch<JobStatusResponse<T>>(statusPath(jobId), token);
    if (status.status === "succeeded") {
      if (!status.result) throw new Error("Job finished without a result");
      return status.result;
    }
    if (status.status === "failed") {
      throw new Error(status.error || "Job failed");
    }
    await new Promise((resolve) => setTimeout(resolve, JOB_POLL_MS));
  }
  throw new Error("Job timed out. Try a coarser grid or smaller area.");
}

export async function workflowTerrainMeshJob(token: string, body: WorkflowTerrainMeshRequest) {
  const started = await apiFetch<JobStartResponse>("/api/v1/workflow/terrain-mesh-job", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return pollJob<WorkflowTerrainMeshResponse>(
    token,
    (jobId) => `/api/v1/workflow/terrain-mesh-job/${jobId}`,
    started.job_id,
  );
}

export function workflowPvmathReportPdf(token: string, body: WorkflowPvmathReportRequest) {
  return downloadBlob("/api/v1/workflow/pvmath-report-pdf", token, body, "application/pdf");
}

export function workflowProjectPackage(token: string, body: WorkflowProjectPackageRequest) {
  return downloadBlob("/api/v1/workflow/project-package", token, body, "application/zip");
}

export function workflowLayoutMatrix(
  token: string,
  body: {
    boundary: { lat: number; lon: number }[];
    module_h?: number;
    module_w?: number;
    module_wp?: number;
    pitch_m?: number;
    setback_m?: number;
  },
) {
  return apiFetch<WorkflowLayoutMatrixResponse>("/api/v1/workflow/layout-matrix", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function runGateAnalysis(token: string, body: GateAnalyzeRequest) {
  return apiFetch<GateAnalyzeResponse>("/api/v1/gate/analyze", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function analyzeTopo(token: string, body: TerrainIQAnalyzeRequest) {
  return apiFetch<TerrainIQAnalyzeResponse>("/api/v1/terrainiq/analyze", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function analyzeTopoJob(token: string, body: TerrainIQAnalyzeRequest) {
  const started = await apiFetch<JobStartResponse>("/api/v1/terrainiq/analyze-job", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
  return pollJob<TerrainIQAnalyzeResponse>(
    token,
    (jobId) => `/api/v1/terrainiq/analyze-job/${jobId}`,
    started.job_id,
  );
}

export function analyzeYield(token: string, body: YieldIQAnalyzeRequest) {
  return apiFetch<YieldIQAnalyzeResponse>("/api/v1/yieldiq/analyze", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function analyzeRevenue(token: string, body: import("../types/revenueiq").RevenueIQAnalyzeRequest) {
  return apiFetch<import("../types/revenueiq").RevenueIQAnalyzeResponse>(
    "/api/v1/revenueiq/analyze",
    token,
    {
      method: "POST",
      body: JSON.stringify(body),
    },
  );
}

export interface GeocodeResult {
  lat: number;
  lon: number;
  label: string;
}

export interface ReverseGeocodeResult {
  lat: number;
  lon: number;
  label: string;
  country: string;
  state: string;
  city: string;
}

export function reverseGeocode(token: string, lat: number, lon: number) {
  const params = new URLSearchParams({ lat: String(lat), lon: String(lon) });
  return apiFetch<ReverseGeocodeResult>(`/api/v1/geocode/reverse?${params}`, token);
}

export function searchLocation(token: string, q: string) {
  const params = new URLSearchParams({ q });
  return apiFetch<{ results: GeocodeResult[] }>(
    `/api/v1/geocode/search?${params}`,
    token,
  );
}

export interface BoundaryParcel {
  id: string;
  name: string;
  full_name?: string;
  layer_group?: string;
  area_ha: number;
  boundary: { lat: number; lon: number }[];
  point_count: number;
  is_primary: boolean;
}

export interface BoundaryParseResult {
  name: string;
  area_ha: number;
  lat: number;
  lon: number;
  boundary: { lat: number; lon: number }[];
  point_count: number;
  parcels?: BoundaryParcel[];
}

export interface ProjectPayload {
  name: string;
  center: { lat: number; lon: number };
  site_boundary_geojson?: GeoJSON.GeoJSON | null;
  restriction_polygons_geojson?: GeoJSON.GeoJSON | null;
  buildable_area_geojson?: GeoJSON.GeoJSON | null;
  land_use: string;
  mount_type: string;
  country: string;
  workflow: Record<string, unknown>;
}

export interface ProjectRecord {
  id: string;
  user_id: string;
  project_data: ProjectPayload;
  created_at?: string;
  updated_at?: string;
}

export interface BuildableAreaResponse {
  buildable_area_geojson: GeoJSON.GeoJSON | null;
  buildable_area_ha: number;
}

export function validateProjectSetup(token: string, project_data: Record<string, unknown>) {
  return apiFetch<ProjectSetupValidateResponse>("/api/v1/projects/validate", token, {
    method: "POST",
    body: JSON.stringify({ project_data }),
  });
}

export function parseBoundaryFile(token: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<BoundaryParseResult>("/api/v1/boundary/parse", token, {
    method: "POST",
    body: form,
  });
}

export function listProjects(token: string) {
  return apiFetch<ProjectRecord[]>("/api/v1/projects", token);
}

export function getProject(token: string, id: string) {
  return apiFetch<ProjectRecord>(`/api/v1/projects/${id}`, token);
}

export function createProject(token: string, body: ProjectPayload) {
  return apiFetch<ProjectRecord>("/api/v1/projects", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateProject(token: string, id: string, body: ProjectPayload) {
  return apiFetch<ProjectRecord>(`/api/v1/projects/${id}`, token, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
}

export function partialUpdateProject(
  token: string,
  id: string,
  patch: Partial<ProjectPayload>,
) {
  return apiFetch<ProjectRecord>(`/api/v1/projects/${id}/partial`, token, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export function deleteProject(token: string, id: string) {
  return apiFetch<{ success: boolean }>(`/api/v1/projects/${id}`, token, {
    method: "DELETE",
  });
}

export function deleteProjectsBulk(token: string, ids: string[]) {
  return apiFetch<{ success: boolean; deleted: number }>("/api/v1/projects/bulk-delete", token, {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
}

export function computeBuildableArea(
  token: string,
  body: {
    site_boundary_geojson: GeoJSON.GeoJSON;
    restriction_polygons_geojson?: GeoJSON.GeoJSON | null;
  },
) {
  return apiFetch<BuildableAreaResponse>("/api/v1/projects/buildable-area", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function downloadScreeningPdf(
  token: string,
  result: GateAnalyzeResponse,
): Promise<Blob> {
  const res = await fetch(`${getApiUrl()}/api/v1/reports/screening-pdf`, {
    method: "POST",
    headers: {
      Accept: "application/pdf",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(result),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.blob();
}

async function downloadBlob(
  path: string,
  token: string,
  body: unknown,
  accept: string,
  retried = false,
): Promise<Blob> {
  let res: Response;
  try {
    res = await fetchWithRetry(`${getApiUrl()}${path}`, {
      method: "POST",
      headers: {
        Accept: accept,
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    });
  } catch {
    if (!retried && tokenRefresher) {
      const fresh = await tokenRefresher();
      if (fresh) return downloadBlob(path, fresh, body, accept, true);
    }
    throw new Error(
      "Network error — could not reach the PVMath server. Check your connection and try again.",
    );
  }
  if (res.status === 401 && !retried && tokenRefresher) {
    const fresh = await tokenRefresher();
    if (fresh) return downloadBlob(path, fresh, body, accept, true);
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.blob();
}

export function topoReportPdf(token: string, body: TerrainIQAnalyzeRequest) {
  return downloadBlob("/api/v1/terrainiq/report-pdf", token, body, "application/pdf");
}

export function topoExportLandxml(token: string, body: TerrainIQAnalyzeRequest) {
  return downloadBlob("/api/v1/terrainiq/export/landxml", token, body, "application/xml");
}

export function topoExportContoursLocal(token: string, body: TerrainIQAnalyzeRequest) {
  return downloadBlob("/api/v1/terrainiq/export/contours-local", token, body, "application/dxf");
}

export function topoExportsZip(token: string, body: TerrainIQAnalyzeRequest) {
  return downloadBlob("/api/v1/terrainiq/exports", token, body, "application/zip");
}
