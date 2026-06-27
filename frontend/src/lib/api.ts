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

const API_URL = (import.meta.env.VITE_API_URL || "https://api.pvmath.com").replace(
  /\/$/,
  "",
);

let tokenRefresher: (() => Promise<string | null>) | null = null;

export function setTokenRefresher(fn: (() => Promise<string | null>) | null) {
  tokenRefresher = fn;
}

async function apiFetch<T>(
  path: string,
  token: string,
  init?: RequestInit,
  retried = false,
): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, {
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
  body: { score_components: Record<string, number>; terrain_score: number },
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

export function workflowLayoutDetail(token: string, body: WorkflowLayoutDetailRequest) {
  return apiFetch<WorkflowLayoutDetailResponse>("/api/v1/workflow/layout-detail", token, {
    method: "POST",
    body: JSON.stringify(body),
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

export function analyzeYield(token: string, body: YieldIQAnalyzeRequest) {
  return apiFetch<YieldIQAnalyzeResponse>("/api/v1/yieldiq/analyze", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
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

export function deleteAllProjects(token: string) {
  return apiFetch<{ success: boolean; deleted: number }>("/api/v1/projects", token, {
    method: "DELETE",
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
  const res = await fetch(`${API_URL}/api/v1/reports/screening-pdf`, {
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
    res = await fetch(`${API_URL}${path}`, {
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

export function topoExportsZip(token: string, body: TerrainIQAnalyzeRequest) {
  return downloadBlob("/api/v1/terrainiq/exports", token, body, "application/zip");
}
