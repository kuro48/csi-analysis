import { API_BASE } from "./constants";
import type { BaseCSIResponse, CSIDataListResponse, CSIStatus, MainCSIResponse } from "./types";

const CHUNK_SIZE = 2 * 1024 * 1024; // 2MB — 100秒タイムアウト対策

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

async function uploadInChunks(
  file: File,
  endpoint: string,
  extraFields: Record<string, string>,
  signal?: AbortSignal,
): Promise<unknown> {
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE);
  let uploadId: string | undefined;

  for (let i = 0; i < totalChunks; i++) {
    if (signal?.aborted) throw new DOMException("Aborted", "AbortError");

    const start = i * CHUNK_SIZE;
    const chunk = file.slice(start, start + CHUNK_SIZE);

    const form = new FormData();
    form.append("chunk", chunk, file.name);
    form.append("chunk_index", String(i));
    form.append("total_chunks", String(totalChunks));
    form.append("filename", file.name);
    if (uploadId) form.append("upload_id", uploadId);
    for (const [k, v] of Object.entries(extraFields)) form.append(k, v);

    const res = await request<{ upload_id: string; chunks_received: number; base_csi?: BaseCSIResponse; csi_data?: MainCSIResponse }>(
      `${API_BASE}${endpoint}`,
      { method: "POST", body: form, signal },
    );

    uploadId = res.upload_id;

    if (res.base_csi) return res.base_csi;
    if (res.csi_data) return res.csi_data;
  }

  throw new Error("チャンクアップロード完了後にレコードが返されませんでした");
}

export function uploadBaseCSI(file: File, signal?: AbortSignal): Promise<BaseCSIResponse> {
  if (file.size <= CHUNK_SIZE) {
    const form = new FormData();
    form.append("file", file);
    return request<BaseCSIResponse>(`${API_BASE}/api/v2/base-csi/register`, { method: "POST", body: form, signal });
  }
  return uploadInChunks(file, "/api/v2/base-csi/upload-chunk", {}, signal) as Promise<BaseCSIResponse>;
}

export function getBaseCSI(id: string, signal?: AbortSignal): Promise<BaseCSIResponse> {
  return request<BaseCSIResponse>(`${API_BASE}/api/v2/base-csi/${id}`, { signal });
}

export function uploadMainCSI(file: File, signal?: AbortSignal): Promise<MainCSIResponse> {
  if (file.size <= CHUNK_SIZE) {
    const form = new FormData();
    form.append("file", file);
    return request<MainCSIResponse>(`${API_BASE}/api/v2/csi-data/upload`, { method: "POST", body: form, signal });
  }
  return uploadInChunks(file, "/api/v2/csi-data/upload-chunk", {}, signal) as Promise<MainCSIResponse>;
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
