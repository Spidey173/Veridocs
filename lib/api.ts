/**
 * Veridocs API Client
 * Honest, direct communication with FastAPI backend.
 * Zero hardcoded mock responses.
 */

export interface SourceInfo {
  page: number;
  snippet: string;
  source_file: string;
  relevance_score?: number;
}

export interface CitationInfo {
  citation_id: number;
  page: number;
  source_file: string;
  highlighted_text: string;
}

export interface ClaimCheckDetail {
  claim: string;
  overlap_score: number;
  is_supported: boolean;
  matched_page?: number;
  source_file?: string;
}

export interface CitationCheckResult {
  citation_score: number;
  total_claims: number;
  supported_claims: number;
  claims: ClaimCheckDetail[];
}

export interface QueryResponse {
  answer: string;
  sources: SourceInfo[];
  citations: CitationInfo[];
  citation_check?: CitationCheckResult;
}

export interface UploadResponse {
  session_id: string;
  chunk_count: number;
  processed_files: number;
  failed_files: string[];
  message: string;
  document_metadata?: Array<{
    filename: string;
    file_size_bytes: number;
    num_pages: number;
  }>;
}

export interface SessionInfo {
  session_id: string;
  created_at: number;
  file_names: string[];
  chunk_count: number;
}

export interface HealthStatus {
  status: string;
  version: string;
  llm_configured: boolean;
  active_sessions: number;
  embedding_model_loaded: boolean;
}

export interface StreamEvent {
  event: "token" | "citation" | "citation_check" | "error" | "done";
  data: Record<string, unknown>;
}

export function getApiBase(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl && envUrl.trim()) {
    return envUrl.trim().replace(/\/$/, "");
  }
  // Default to relative /api which proxies to backend via next.config.ts rewrites
  return "";
}

/**
 * Retrieve user custom API key stored locally in browser.
 */
export function getUserApiKey(): string {
  if (typeof window !== "undefined" && window.localStorage) {
    return window.localStorage.getItem("veridocs_user_api_key") || "";
  }
  if (typeof localStorage !== "undefined") {
    return localStorage.getItem("veridocs_user_api_key") || "";
  }
  return "";
}

/**
 * Persist user custom API key strictly in browser localStorage.
 */
export function setUserApiKey(key: string): void {
  const storage = typeof window !== "undefined" && window.localStorage
    ? window.localStorage
    : typeof localStorage !== "undefined"
    ? localStorage
    : null;

  if (storage) {
    if (key.trim()) {
      storage.setItem("veridocs_user_api_key", key.trim());
    } else {
      storage.removeItem("veridocs_user_api_key");
    }
  }
}

/**
 * Check backend health with timeout for waking up cold start detection.
 */
export async function checkBackendHealth(): Promise<{ ok: boolean; waking: boolean; data?: HealthStatus }> {
  const base = getApiBase();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);

  try {
    const res = await fetch(`${base}/api/health`, { signal: controller.signal });
    clearTimeout(timeoutId);
    if (res.ok) {
      const data = await res.json();
      return { ok: true, waking: false, data };
    }
    return { ok: false, waking: false };
  } catch (err: unknown) {
    clearTimeout(timeoutId);
    // If connection refused or timeout, backend might be cold-starting on free-tier Render
    return { ok: false, waking: true };
  }
}

/**
 * Upload files (PDF / TXT) to backend.
 */
export async function uploadDocuments(
  files: File[],
  sessionId?: string,
  onProgress?: (percent: number) => void
): Promise<UploadResponse> {
  const base = getApiBase();
  const formData = new FormData();
  files.forEach((f) => formData.append("files", f));
  if (sessionId) {
    formData.append("session_id", sessionId);
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText));
        } catch {
          reject(new Error("Invalid response format from server."));
        }
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || `Upload failed with status ${xhr.status}`));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error("Connection error connecting to backend. Is it running?"));
    xhr.ontimeout = () => reject(new Error("Upload request timed out."));

    xhr.open("POST", `${base}/api/upload`);
    xhr.send(formData);
  });
}

/**
 * Fetch raw PDF file for in-browser rendering.
 */
export async function fetchPdfBlobUrl(sessionId: string, documentName: string): Promise<string> {
  const base = getApiBase();
  const url = `${base}/api/documents/${sessionId}/pdf?document_name=${encodeURIComponent(documentName)}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load PDF (${res.status}): ${res.statusText}`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

/**
 * Stream question answering tokens from backend via SSE.
 */
export async function* streamQuery(
  sessionId: string,
  question: string,
  history?: Array<{ role: string; content: string }>,
  activeFiles?: string[]
): AsyncGenerator<StreamEvent> {
  const base = getApiBase();
  const userKey = getUserApiKey();
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (userKey) {
    headers["X-LLM-API-Key"] = userKey;
  }

  const res = await fetch(`${base}/api/query/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      session_id: sessionId,
      question,
      history,
      active_files: activeFiles,
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Query failed with status ${res.status}`);
  }

  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("No response stream available.");
  }

  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    let currentEvent = "";
    for (const line of lines) {
      if (line.startsWith("event: ")) {
        currentEvent = line.slice(7).trim();
      } else if (line.startsWith("data: ") && currentEvent) {
        try {
          const data = JSON.parse(line.slice(6));
          yield { event: currentEvent as StreamEvent["event"], data };
        } catch {
          // ignore malformed JSON chunk
        }
        currentEvent = "";
      }
    }
  }
}

/**
 * Retrieve session metadata and file names.
 */
export async function getSessionInfo(sessionId: string): Promise<SessionInfo> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/sessions/${sessionId}`);
  if (!res.ok) {
    throw new Error(`Session ${sessionId} not found`);
  }
  return res.json();
}

/**
 * Delete a session and its files.
 */
export async function deleteSession(sessionId: string): Promise<{ status: string; message: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/sessions/${sessionId}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error("Failed to delete session");
  }
  return res.json();
}

/**
 * Delete a single document.
 */
export async function deleteDocument(
  sessionId: string,
  documentName: string
): Promise<{ status: string; removed_document: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/sessions/${sessionId}/documents/${encodeURIComponent(documentName)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error("Failed to remove document");
  }
  return res.json();
}
