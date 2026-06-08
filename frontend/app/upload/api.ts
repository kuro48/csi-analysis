import { API_BASE } from "./constants";
import type { BaseCSIResponse, CSIDataListResponse, CSIStatus, MainCSIResponse } from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export function uploadBaseCSI(file: File, signal?: AbortSignal): Promise<BaseCSIResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<BaseCSIResponse>(`${API_BASE}/api/v2/base-csi/register`, { method: "POST", body: form, signal });
}

export function getBaseCSI(id: string, signal?: AbortSignal): Promise<BaseCSIResponse> {
  return request<BaseCSIResponse>(`${API_BASE}/api/v2/base-csi/${id}`, { signal });
}

export function uploadMainCSI(file: File, signal?: AbortSignal): Promise<MainCSIResponse> {
  const form = new FormData();
  form.append("file", file);
  return request<MainCSIResponse>(`${API_BASE}/api/v2/csi-data/upload`, { method: "POST", body: form, signal });
}

export function getMainCSI(id: string, signal?: AbortSignal): Promise<MainCSIResponse> {
  return request<MainCSIResponse>(`${API_BASE}/api/v2/csi-data/${id}`, { signal });
}

export function listMainCSI(
  params: {
    status?: CSIStatus | "all";
    page?: number;
    pageSize?: number;
    sessionId?: string;
  } = {},
  signal?: AbortSignal
): Promise<CSIDataListResponse> {
  const query = new URLSearchParams();
  query.set("data_status", params.status ?? "all");
  query.set("page", String(params.page ?? 1));
  query.set("page_size", String(params.pageSize ?? 20));
  if (params.sessionId) query.set("session_id", params.sessionId);

  return request<CSIDataListResponse>(`${API_BASE}/api/v2/csi-data/?${query.toString()}`, { signal });
}
