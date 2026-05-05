import type {
  HealthStatus,
  ResearchJobResponse,
  ComparisonReport,
  ResearchHistoryItem,
  ResearchHistoryDetail,
} from "./types";
import type { Backend2Report, Backend2HistoryItem } from "./types-backend2";
import { useResearchStore } from "./store";

// The base URL is no longer a module-level constant — it's read from the
// Zustand store on every call so the backend toggle (BackendToggle in the
// header) can flip between :8000 (legacy) and :8001 (backend2) at runtime.
function _base(): string {
  return useResearchStore.getState().apiBase();
}

// Explicit per-backend bases — used by the history page, which fetches BOTH
// backends in parallel regardless of the active toggle so the merged list
// always reflects every saved run.
export const LEGACY_API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const AGENTIC_API_BASE =
  process.env.NEXT_PUBLIC_API_URL_BACKEND2 || "http://localhost:8001";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${_base()}/api${url}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function checkHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/health");
}

// ─── Research Agent API (works against EITHER backend; the store decides which) ──

export async function startResearch(
  topic: string,
  maxLayer: number,
  brief: string = ""
): Promise<ResearchJobResponse> {
  return request<ResearchJobResponse>("/research", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic,
      brief,
      max_layer: maxLayer,
    }),
  });
}

export function getResearchProgressUrl(jobId: string): string {
  return `${_base()}/api/research/${jobId}/progress`;
}

// Legacy result shape (3-layer ComparisonReport).
export async function getResearchResult(
  jobId: string
): Promise<ComparisonReport> {
  return request<ComparisonReport>(`/research/${jobId}/result`);
}

// Backend2-shaped result. The frontend's results page checks
// `store.backend === "agentic"` and uses this fetcher instead of the legacy
// one. Same URL — the server endpoint just returns a different JSON shape.
export async function getBackend2Result(
  jobId: string
): Promise<Backend2Report> {
  return request<Backend2Report>(`/research/${jobId}/result`);
}

// Backend2 only — resolve the mandatory variant pick after a1. `index` is
// 1-based (matches the SSE awaiting_variant_choice payload).
export async function selectBackend2Variant(
  jobId: string,
  index: number,
): Promise<{ job_id: string; chosen_query: string }> {
  return request<{ job_id: string; chosen_query: string }>(
    `/research/${jobId}/select_variant`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ index }),
    },
  );
}

// ─── Research History API ────────────────────────────────────

export async function getResearchHistory(): Promise<ResearchHistoryItem[]> {
  return request<ResearchHistoryItem[]>("/research/history");
}

// Backend2's history shape is different (has grounding_score, latest_node,
// is_complete, etc.). The history page calls one of these depending on the
// active backend.
export async function getBackend2History(): Promise<Backend2HistoryItem[]> {
  return request<Backend2HistoryItem[]>("/research/history");
}

export async function getResearchHistoryDetail(
  id: string
): Promise<ResearchHistoryDetail> {
  return request<ResearchHistoryDetail>(`/research/history/${id}`);
}

export async function getBackend2HistoryDetail(
  id: string
): Promise<Backend2Report> {
  return request<Backend2Report>(`/research/history/${id}`);
}

export async function deleteResearchHistory(id: string): Promise<void> {
  await request<{ deleted: boolean; id: string }>(`/research/history/${id}`, {
    method: "DELETE",
  });
}

// ─── Explicit per-backend history fetchers ───────────────────
// The merged history page calls both of these in parallel and unions the
// results. Failure on either side is non-fatal — we just show what loaded.

export async function getLegacyHistoryDirect(): Promise<ResearchHistoryItem[]> {
  const res = await fetch(`${LEGACY_API_BASE}/api/research/history`);
  if (!res.ok) throw new Error(`legacy history failed: ${res.status}`);
  return res.json();
}

export async function getAgenticHistoryDirect(): Promise<Backend2HistoryItem[]> {
  const res = await fetch(`${AGENTIC_API_BASE}/api/research/history`);
  if (!res.ok) throw new Error(`agentic history failed: ${res.status}`);
  return res.json();
}

export async function deleteLegacyHistoryDirect(id: string): Promise<void> {
  await fetch(`${LEGACY_API_BASE}/api/research/history/${id}`, {
    method: "DELETE",
  });
}

export async function deleteAgenticHistoryDirect(id: string): Promise<void> {
  await fetch(`${AGENTIC_API_BASE}/api/research/history/${id}`, {
    method: "DELETE",
  });
}
