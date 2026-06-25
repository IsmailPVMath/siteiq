import type { GateAnalyzeRequest, GateAnalyzeResponse, MeResponse } from "../types/gate";

const API_URL = (import.meta.env.VITE_API_URL || "https://api.pvmath.com").replace(
  /\/$/,
  "",
);

async function apiFetch<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
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

  const text = await res.text();
  let data: unknown = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { detail: text };
    }
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

export function runGateAnalysis(token: string, body: GateAnalyzeRequest) {
  return apiFetch<GateAnalyzeResponse>("/api/v1/gate/analyze", token, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export interface GeocodeResult {
  lat: number;
  lon: number;
  label: string;
}

export function searchLocation(token: string, q: string) {
  const params = new URLSearchParams({ q });
  return apiFetch<{ results: GeocodeResult[] }>(
    `/api/v1/geocode/search?${params}`,
    token,
  );
}

export interface BoundaryParseResult {
  name: string;
  area_ha: number;
  lat: number;
  lon: number;
  boundary: { lat: number; lon: number }[];
  point_count: number;
}

export function parseBoundaryFile(token: string, file: File) {
  const form = new FormData();
  form.append("file", file);
  return apiFetch<BoundaryParseResult>("/api/v1/boundary/parse", token, {
    method: "POST",
    body: form,
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
