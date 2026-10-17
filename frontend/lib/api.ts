/**
 * Veridocs AI — API Client
 * Handles all communication with the FastAPI backend.
 */

export function getApiBase(): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl && envUrl.trim()) {
    return envUrl.trim().replace(/\/$/, "");
  }
  return "http://localhost:8000";
}

// === Types ===

export interface UploadResponse {
  session_id: string;
  chunk_count: number;
  processed_files: number;
  failed_files: string[];
  message: string;
  document_metadata?: Record<string, unknown>[];
}

export interface SourceInfo {
  page: number;
  snippet: string;
  source_file?: string;
  section?: string;
  relevance_score?: number;
  bm25_score?: number;
  dense_score?: number;
  rerank_score?: number;
}

export interface CitationInfo {
  citation_id: number;
  page: number;
  source_file: string;
  highlighted_text: string;
  section?: string;
  confidence?: number;
}

export interface RagTriadMetrics {
  context_relevance: number;
  groundedness: number;
  answer_relevance: number;
  numeric_accuracy: number;
  latency_ms?: number;
  retrieval_pipeline?: string;
}

export interface QueryResponse {
  answer: string;
  sources: SourceInfo[];
  citations?: CitationInfo[];
  confidence_score?: number;
  rag_triad?: RagTriadMetrics;
  suggested_followups?: string[];
}

export interface ClaimVerificationItem {
  claim: string;
  score: number;
  status: "verified" | "inferred" | "hallucinated";
  is_supported: boolean;
  numeric_grounded?: boolean;
  best_source_page?: number;
  source_file?: string;
}

export interface StreamEvent {
  event: "token" | "citation" | "confidence" | "verification" | "audit_metrics" | "done" | "error" | "suggested_questions";
  data: Record<string, unknown>;
}

export interface InsightsResponse {
  session_id: string;
  executive_summary?: {
    purpose: string;
    key_findings: string[];
    risks?: string[];
    conclusions: string[];
  };
  suggested_questions: string[];
  key_entities: Array<{
    entity_type: string;
    value: string;
    count: number;
    page?: number;
  }>;
  total_pages: number;
  total_chunks: number;
  processing_time_ms?: number;
}

export interface ConversationMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: CitationInfo[];
  confidence_score?: number;
  timestamp: string;
}

export interface SessionInfo {
  session_id: string;
  file_names: string[];
  chunk_count: number;
  metadata: Record<string, unknown>[];
  created_at: number;
  has_insights: boolean;
}

// === API Functions ===

export async function uploadDocuments(
  files: File[],
  onProgress?: (progress: number) => void,
  sessionId?: string
): Promise<UploadResponse> {
  const formData = new FormData();
  files.forEach((file) => formData.append("files", file));
  if (sessionId) {
    formData.append("session_id", sessionId);
  }

  const xhr = new XMLHttpRequest();

  return new Promise((resolve, reject) => {
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        try {
          const err = JSON.parse(xhr.responseText);
          reject(new Error(err.detail || "Upload failed"));
        } catch {
          reject(new Error(`Upload failed with status ${xhr.status}`));
        }
      }
    };

    xhr.onerror = () => reject(new Error("Network error during upload (is backend running at http://localhost:8000?)"));
    xhr.open("POST", `${getApiBase()}/api/upload`);
    xhr.send(formData);
  });
}

export async function queryDocuments(
  sessionId: string,
  question: string,
  history?: Array<{ role: string; content: string }>
): Promise<QueryResponse> {
  const response = await fetch(`${getApiBase()}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      question,
      history,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Query failed");
  }

  return response.json();
}

export async function* streamQuery(
  sessionId: string,
  question: string,
  history?: Array<{ role: string; content: string }>,
  activeFiles?: string[]
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${getApiBase()}/api/query/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      question,
      history,
      active_files: activeFiles,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Stream query failed");
  }

  const reader = response.body?.getReader();
  if (!reader) throw new Error("No response stream");

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
          // Skip malformed data
        }
        currentEvent = "";
      }
    }
  }
}

export async function getInsights(
  sessionId: string,
  documentName?: string
): Promise<InsightsResponse> {
  const url = documentName
    ? `${getApiBase()}/api/documents/${sessionId}/insights?document_name=${encodeURIComponent(documentName)}`
    : `${getApiBase()}/api/documents/${sessionId}/insights`;
  const response = await fetch(url);
  if (!response.ok) throw new Error("Failed to fetch insights");
  return response.json();
}

export async function getSessionInfo(
  sessionId: string
): Promise<SessionInfo> {
  const response = await fetch(`${getApiBase()}/api/sessions/${sessionId}`);
  if (!response.ok) throw new Error("Failed to fetch session info");
  return response.json();
}

export async function getConversationHistory(
  sessionId: string
): Promise<{ messages: ConversationMessage[] }> {
  const response = await fetch(
    `${getApiBase()}/api/sessions/${sessionId}/history`
  );
  if (!response.ok) throw new Error("Failed to fetch conversation history");
  return response.json();
}

export function getPdfUrl(sessionId: string, documentName: string): string {
  return `${getApiBase()}/api/documents/${sessionId}/pdf?document_name=${encodeURIComponent(documentName)}`;
}

// === Cross-Document Contradiction Audit ===

export interface ConflictSnippet {
  filename: string;
  page: number;
  snippet: string;
  section?: string;
}

export interface AuditDiffItem {
  id: string;
  topic: string;
  severity: "critical" | "warning" | "info";
  conflict_type: "contradiction" | "omission" | "modification" | "numeric_mismatch";
  explanation: string;
  risk_analysis: string;
  doc_a: ConflictSnippet;
  doc_b: ConflictSnippet;
}

export interface AuditDiffReport {
  doc_a_name: string;
  doc_b_name: string;
  alignment_score: number;
  summary: string;
  critical_count: number;
  warning_count: number;
  conflicts: AuditDiffItem[];
}

export async function auditContradictions(
  sessionId: string,
  docA: string,
  docB: string,
  focusTopic: string = "all"
): Promise<AuditDiffReport> {
  const response = await fetch(`${getApiBase()}/api/audit/contradictions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: sessionId,
      doc_a: docA,
      doc_b: docB,
      focus_topic: focusTopic,
    }),
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || "Contradiction audit failed");
  }

  return response.json();
}
