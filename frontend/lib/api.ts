import type {
  ExtractionResponse,
  GenerateResponse,
  HealthStatus,
  ResearchJobResponse,
  ComparisonReport,
  ResearchHistoryItem,
  ResearchHistoryDetail,
} from "./types";

const API_BASE = "/api";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, init);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function checkHealth(): Promise<HealthStatus> {
  return request<HealthStatus>("/health");
}

export async function extractFiles(
  pptxFile: File,
  xlsxFile: File
): Promise<ExtractionResponse> {
  const form = new FormData();
  form.append("pptx", pptxFile);
  form.append("xlsx", xlsxFile);
  return request<ExtractionResponse>("/extract/files", {
    method: "POST",
    body: form,
  });
}

export async function extractJson(
  jsonFile: File
): Promise<ExtractionResponse> {
  const form = new FormData();
  form.append("file", jsonFile);
  return request<ExtractionResponse>("/extract/json", {
    method: "POST",
    body: form,
  });
}

export async function extractFromPaths(
  pptxPath: string,
  xlsxPath: string
): Promise<ExtractionResponse> {
  return request<ExtractionResponse>(
    `/extract/paths?pptx_path=${encodeURIComponent(pptxPath)}&xlsx_path=${encodeURIComponent(xlsxPath)}`,
    { method: "POST" }
  );
}

export async function extractJsonFromPath(
  jsonPath: string
): Promise<ExtractionResponse> {
  return request<ExtractionResponse>(
    `/extract/json-path?json_path=${encodeURIComponent(jsonPath)}`,
    { method: "POST" }
  );
}

export async function startGeneration(
  extractedData: Record<string, unknown>,
  skipContent: boolean,
  topicOverride: string
): Promise<GenerateResponse> {
  return request<GenerateResponse>("/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      extracted_data: extractedData,
      skip_content: skipContent,
      topic_override: topicOverride,
    }),
  });
}

export function getProgressUrl(jobId: string): string {
  return `${API_BASE}/generate/${jobId}/progress`;
}

export function getDownloadUrl(jobId: string): string {
  return `${API_BASE}/generate/${jobId}/download`;
}

// ─── Research Agent API ──────────────────────────────────────

export async function startResearch(
  topic: string,
  maxLayer: number
): Promise<ResearchJobResponse> {
  return request<ResearchJobResponse>("/research", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      topic,
      max_layer: maxLayer,
    }),
  });
}

export function getResearchProgressUrl(jobId: string): string {
  return `${API_BASE}/research/${jobId}/progress`;
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
