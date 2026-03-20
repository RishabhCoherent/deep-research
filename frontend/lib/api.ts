import type {
  HealthStatus,
  ResearchJobResponse,
  ComparisonReport,
  ResearchHistoryItem,
  ResearchHistoryDetail,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}/api${url}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function checkHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/health");
}

// ─── Research Agent API ──────────────────────────────────────

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
  return `${API_BASE}/api/research/${jobId}/progress`;
}

export async function getResearchResult(
  jobId: string
): Promise<ComparisonReport> {
  return request<ComparisonReport>(`/research/${jobId}/result`);
}

// ─── Research History API ────────────────────────────────────

export async function getResearchHistory(): Promise<ResearchHistoryItem[]> {
  return request<ResearchHistoryItem[]>("/research/history");
}

export async function getResearchHistoryDetail(
  id: string
): Promise<ResearchHistoryDetail> {
  return request<ResearchHistoryDetail>(`/research/history/${id}`);
}

export async function deleteResearchHistory(id: string): Promise<void> {
  await request<{ deleted: boolean; id: string }>(`/research/history/${id}`, {
    method: "DELETE",
  });
}
