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
      ...(init?.body ? { "Content-Type": "application/json" } : {}),
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
