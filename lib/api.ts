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
  section_path?: string | null;
}

export interface CitationInfo {
  citation_id: number;
  page: number;
  source_file: string;
  highlighted_text: string;
  chunk_type?: "text" | "table" | "figure";
  extraction_method?: "text_layer" | "ocr" | "vision";
  ocr_confidence?: number;
  section_path?: string | null;
}

export interface ClaimCheckDetail {
  claim: string;
  overlap_score: number;
  is_supported: boolean;
  status?: "supported" | "contradicted" | "unsupported";
  score?: number;
  nli_label?: string;
  matched_page?: number;
  source_file?: string;
  section_path?: string | null;
  chunk_type?: "text" | "table" | "figure";
  is_low_confidence_ocr?: boolean;
  is_vision_only?: boolean;
}

export interface CitationCheckResult {
  citation_score: number;
  total_claims: number;
  supported_claims: number;
  contradicted_claims?: number;
  unsupported_claims?: number;
  summary?: string;
  claims: ClaimCheckDetail[];
  has_low_confidence_ocr_warning?: boolean;
  has_contradiction_warning?: boolean;
  has_vision_only_warning?: boolean;
}

export interface EntityItem {
  id: string;
  document_id: string;
  page_number: number;
  chunk_id?: string;
  label: string;
  text: string;
  normalized?: any;
  start_offset?: number;
  end_offset?: number;
  score: number;
}

export interface FieldEvidenceItem {
  value: any;
  page: number;
  quote: string;
  confidence: number;
  verified: boolean;
  math_mismatch?: boolean;
}

export interface ExtractionResult {
  document_id: string;
  filename?: string;
  schema_type: string;
  fields: Record<string, any>;
  verified_ratio: number;
  user_edits?: Record<string, any>;
}

export interface VisionFigure {
  type: "chart" | "diagram" | "photo" | "logo" | "other";
  title: string;
  description: string;
  data_points: string[];
  confidence: number;
}

export interface VisionSignature {
  present: boolean;
  signed?: boolean | null;
  location_hint: string;
  confidence: number;
}

export interface VisionPage {
  id: string;
  page_number: number;
  figures: VisionFigure[];
  signatures: VisionSignature[];
  layout_notes: string;
  model: string;
  cost_tokens: number;
}

export interface VisionResult {
  document_id: string;
  filename?: string;
  pages: VisionPage[];
}

export interface UploadResponse {
  session_id: string;
  chunk_count: number;
  processed_files: number;
  failed_files: string[];
  message: string;
  suggested_questions?: string[];
  document_metadata?: Array<{
    filename: string;
    file_size_bytes: number;
    num_pages: number;
    document_id?: string;
  }>;
}

export interface DocumentStatus {
  document_id: string;
  session_id?: string;
  filename: string;
  status: "queued" | "parsing" | "ocr" | "chunking" | "embedding" | "ready" | "failed";
  page_count?: number;
  doc_type?: string;
  error?: string;
  stage_message?: string;
}

export interface ExtractedTable {
  id: string;
  document_id: string;
  page_number: number;
  markdown: string;
  json: {
    headers?: string[];
    rows?: string[][];
  };
  bbox?: Record<string, number>;
}

export interface SessionInfo {
  session_id: string;
  created_at: number;
  file_names: string[];
  chunk_count: number;
  suggested_questions?: string[];
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
  return "";
}

export function getUserApiKey(): string {
  if (typeof window !== "undefined" && window.localStorage) {
    return window.localStorage.getItem("veridocs_user_api_key") || "";
  }
  if (typeof localStorage !== "undefined") {
    return localStorage.getItem("veridocs_user_api_key") || "";
  }
  return "";
}

export function setUserApiKey(key: string): void {
  const storage =
    typeof window !== "undefined" && window.localStorage
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

export async function checkBackendHealth(): Promise<{ ok: boolean; data?: HealthStatus }> {
  const base = getApiBase();
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 4000);

  try {
    const res = await fetch(`${base}/api/health`, { signal: controller.signal });
    clearTimeout(timeoutId);
    if (res.ok) {
      const data = await res.json();
      return { ok: true, data };
    }
    return { ok: false };
  } catch {
    clearTimeout(timeoutId);
    return { ok: false };
  }
}

/**
 * Upload files to backend (synchronous or async-compatible).
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

    xhr.onerror = () => reject(new Error("Connection error connecting to backend."));
    xhr.ontimeout = () => reject(new Error("Upload request timed out."));

    xhr.open("POST", `${base}/api/upload`);
    xhr.send(formData);
  });
}

/**
 * Upload a single document asynchronously for background pipeline processing.
 */
export async function uploadDocumentAsync(
  file: File,
  sessionId?: string
): Promise<{ document_id: string; session_id: string; filename: string; status: string }> {
  const base = getApiBase();
  const formData = new FormData();
  formData.append("file", file);
  if (sessionId) {
    formData.append("session_id", sessionId);
  }

  const res = await fetch(`${base}/documents/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `Upload failed with status ${res.status}`);
  }

  return res.json();
}

/**
 * Subscribe to live progress SSE events for a document.
 */
export function subscribeDocumentStatus(
  documentId: string,
  onEvent: (status: DocumentStatus) => void,
  onError?: (err: any) => void
): () => void {
  const base = getApiBase();
  const url = `${base}/documents/${documentId}/events`;
  let active = true;

  const eventSource = new EventSource(url);

  eventSource.addEventListener("status", (e: MessageEvent) => {
    if (!active) return;
    try {
      const data: DocumentStatus = JSON.parse(e.data);
      onEvent(data);
    } catch { }
  });

  eventSource.addEventListener("done", (e: MessageEvent) => {
    if (!active) return;
    try {
      const data: DocumentStatus = JSON.parse(e.data);
      onEvent(data);
    } catch { }
    eventSource.close();
  });

  eventSource.onerror = (err) => {
    if (onError && active) onError(err);
    eventSource.close();
  };

  return () => {
    active = false;
    eventSource.close();
  };
}

/**
 * Fetch document tables.
 */
export async function fetchDocumentTables(documentId: string): Promise<ExtractedTable[]> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/tables`);
  if (!res.ok) {
    return [];
  }
  const data = await res.json();
  return data.tables || [];
}

/**
 * Retry processing for a failed document.
 */
export async function retryDocumentProcessing(documentId: string): Promise<void> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/retry`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Retry failed");
  }
}

/**
 * Fetch raw PDF or converted image/Word PDF.
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

export interface TextViewerPage {
  page_number: number;
  text: string;
}

/**
 * Fetch extracted page text for fallback text viewer (e.g. .docx without LibreOffice or .txt).
 */
export async function fetchDocumentTextPages(
  sessionId: string,
  documentName: string
): Promise<TextViewerPage[]> {
  const base = getApiBase();
  const url = `${base}/api/documents/${sessionId}/text?document_name=${encodeURIComponent(documentName)}`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Failed to load text preview (${res.status})`);
  }
  const data = await res.json();
  return data.pages || [];
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
        } catch { }
        currentEvent = "";
      }
    }
  }
}

export async function getSessionInfo(sessionId: string): Promise<SessionInfo> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/sessions/${sessionId}`);
  if (!res.ok) {
    throw new Error(`Session ${sessionId} not found`);
  }
  return res.json();
}

export async function deleteSession(sessionId: string): Promise<{ status: string; message: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/api/sessions/${sessionId}`, { method: "DELETE" });
  if (!res.ok) {
    throw new Error("Failed to delete session");
  }
  return res.json();
}

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

/**
 * Fetch extracted entities for a document.
 */
export async function fetchDocumentEntities(documentId: string, label?: string): Promise<EntityItem[]> {
  const base = getApiBase();
  const url = label
    ? `${base}/documents/${documentId}/entities?label=${encodeURIComponent(label)}`
    : `${base}/documents/${documentId}/entities`;
  const res = await fetch(url);
  if (!res.ok) return [];
  const data = await res.json();
  return data.entities || [];
}

/**
 * Fetch structured schema extraction for a document.
 */
export async function fetchDocumentExtraction(documentId: string): Promise<ExtractionResult | null> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/extraction`);
  if (!res.ok) return null;
  return res.json();
}

/**
 * Save manual user edits on extracted fields without overwriting model output.
 */
export async function updateDocumentExtraction(
  documentId: string,
  userEdits: Record<string, any>
): Promise<ExtractionResult | null> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/extraction`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_edits: userEdits }),
  });
  if (!res.ok) return null;
  return res.json();
}

/**
 * Manually override classified document type (e.g. invoice, contract).
 */
export async function overrideDocumentType(
  documentId: string,
  docType: string
): Promise<{ document_id: string; doc_type: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/type`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_type: docType }),
  });
  if (!res.ok) {
    throw new Error("Failed to override document type");
  }
  return res.json();
}

/**
 * Fetch multimodal vision analyses for a document.
 */
export async function fetchDocumentVision(documentId: string): Promise<VisionResult | null> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/vision`);
  if (!res.ok) return null;
  return res.json();
}

// ----------------------------------------------------------------------
// Comparisons, Flags, and Knowledge Graph Types & APIs
// ----------------------------------------------------------------------

export interface DiffToken {
  type: "equal" | "insert" | "delete";
  text: string;
}

export interface ClauseAnalysis {
  change_type: "financial" | "liability" | "term" | "termination" | "confidentiality" | "governing_law" | "other";
  summary: string;
  risk: "low" | "medium" | "high";
  risk_reason: string;
  evidence_quote?: string;
  quote_verified?: boolean;
}

export interface AlignedClause {
  status: "unchanged" | "modified" | "added" | "removed" | "moved";
  clause_a?: {
    clause_index: number;
    number?: string;
    heading?: string;
    text: string;
    page_start: number;
    page_end: number;
  };
  clause_b?: {
    clause_index: number;
    number?: string;
    heading?: string;
    text: string;
    page_start: number;
    page_end: number;
  };
  similarity: number;
  diff_tokens: DiffToken[];
  page_a?: number;
  page_b?: number;
  analysis?: ClauseAnalysis;
}

export interface ComparisonData {
  id: string;
  doc_a: string;
  doc_b: string;
  status: "queued" | "processing" | "ready" | "failed";
  data?: {
    comparison_id: string;
    doc_a: { id: string; filename: string; clause_count: number };
    doc_b: { id: string; filename: string; clause_count: number };
    stats: {
      total_aligned: number;
      status_counts: Record<string, number>;
      risk_counts: { high: number; medium: number; low: number };
    };
    aligned_clauses: AlignedClause[];
  };
  error?: string;
  created_at: number;
}

export async function createComparison(
  docAId: string,
  docBId: string
): Promise<{ id: string; doc_a: string; doc_b: string; status: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/comparisons`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ doc_a: docAId, doc_b: docBId }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to start comparison");
  }
  return res.json();
}

export async function fetchComparison(comparisonId: string): Promise<ComparisonData> {
  const base = getApiBase();
  const res = await fetch(`${base}/comparisons/${comparisonId}`);
  if (!res.ok) {
    throw new Error("Failed to fetch comparison details");
  }
  return res.json();
}

export async function exportComparisonMarkdown(
  comparisonId: string
): Promise<{ filename: string; markdown: string }> {
  const base = getApiBase();
  const res = await fetch(`${base}/comparisons/${comparisonId}/export`);
  if (!res.ok) {
    throw new Error("Failed to export comparison markdown");
  }
  return res.json();
}

export interface AnomalyFlagEvidence {
  page: number;
  quote: string;
  details?: string;
}

export interface AnomalyFlag {
  id: string;
  document_id: string;
  rule_id: string;
  severity: "low" | "medium" | "high";
  message: string;
  evidence: AnomalyFlagEvidence[];
  confidence: number;
  created_at: number;
}

export interface DocumentFlagsResult {
  document_id: string;
  filename?: string;
  disclaimer: string;
  total_flags: number;
  severity_counts: { high: number; medium: number; low: number };
  flags: AnomalyFlag[];
}

export async function fetchDocumentFlags(documentId: string): Promise<DocumentFlagsResult> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/flags`);
  if (!res.ok) {
    throw new Error("Failed to fetch document flags");
  }
  return res.json();
}

export interface GraphNodeData {
  id: string;
  label: string;
  name: string;
  canonical_name: string;
  aliases: string[];
  properties: Record<string, any>;
  document_ids: string[];
  created_at?: number;
}

export interface GraphEdgeData {
  id: string;
  source_id: string;
  target_id: string;
  relation: string;
  document_id?: string;
  page_number?: number;
  quote?: string;
  verified: boolean;
  properties: Record<string, any>;
  created_at?: number;
}

export interface GraphResult {
  document_id?: string;
  query?: string;
  capped: boolean;
  total_nodes: number;
  total_edges: number;
  nodes: GraphNodeData[];
  edges: GraphEdgeData[];
}

export async function fetchDocumentGraph(documentId: string, maxNodes: number = 50): Promise<GraphResult> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/graph?max_nodes=${maxNodes}`);
  if (!res.ok) {
    throw new Error("Failed to fetch document knowledge graph");
  }
  return res.json();
}

export async function searchCrossDocumentGraph(entity: string, maxNodes: number = 50): Promise<GraphResult> {
  const base = getApiBase();
  const res = await fetch(`${base}/graph?entity=${encodeURIComponent(entity)}&max_nodes=${maxNodes}`);
  if (!res.ok) {
    throw new Error("Failed to search cross-document graph");
  }
  return res.json();
}

// ----------------------------------------------------------------------
// Structured Document Summary Types & APIs
// ----------------------------------------------------------------------

export interface SummaryClaimVerification {
  field?: string;
  claim: string;
  status: "supported" | "contradicted" | "unsupported";
  score: number;
  overlap_score: number;
  matched_page?: number | null;
  section_path?: string | null;
  source_file?: string | null;
}

export interface DocumentSummaryResult {
  document_id: string;
  filename?: string;
  status: "not_generated" | "queued" | "processing" | "ready" | "failed";
  summary?: {
    main_purpose: string;
    important_points: string[];
    key_information: string[];
    conclusion: string;
  } | null;
  verification?: {
    grounding_score: number;
    total_claims: number;
    supported_claims: number;
    contradicted_claims: number;
    claims: SummaryClaimVerification[];
  } | null;
  grounding_score?: number | null;
  error?: string | null;
  created_at?: number;
  updated_at?: number;
}

export async function fetchDocumentSummary(documentId: string): Promise<DocumentSummaryResult> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/summary`);
  if (!res.ok) {
    throw new Error("Failed to fetch document summary");
  }
  return res.json();
}

export async function generateDocumentSummary(
  documentId: string,
  force: boolean = false
): Promise<DocumentSummaryResult> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/summary?force=${force}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ force }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to generate summary");
  }
  return res.json();
}

// ----------------------------------------------------------------------
// Report Generation & Export Types & APIs
// ----------------------------------------------------------------------

export interface ReportCitation {
  chunk_id?: string | null;
  page: number;
  section_path?: string | null;
  quote: string;
}

export interface ReportFinding {
  title: string;
  detail: string;
  severity?: "low" | "medium" | "high" | string | null;
  category?: string | null;
  citations: ReportCitation[];
}

export interface DocumentReportResult {
  document_id: string;
  filename?: string;
  executive_summary: string;
  important_findings: ReportFinding[];
  risks: ReportFinding[];
  recommendations: ReportFinding[];
  generated_at?: number;
}

export async function generateDocumentReport(documentId: string): Promise<DocumentReportResult> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/report`, {
    method: "POST",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to generate report");
  }
  return res.json();
}

export async function fetchDocumentReport(documentId: string): Promise<DocumentReportResult | null> {
  const base = getApiBase();
  const res = await fetch(`${base}/documents/${documentId}/report`);
  if (res.status === 404) return null;
  if (!res.ok) {
    throw new Error("Failed to fetch report");
  }
  return res.json();
}

export function getReportExportUrl(documentId: string, format: "md" | "pdf" | "docx"): string {
  const base = getApiBase();
  return `${base}/documents/${documentId}/report/export?format=${format}`;
}

// ----------------------------------------------------------------------
// Analytics & Cross-Document Library Search Types & APIs
// ----------------------------------------------------------------------

export interface DailyAnalyticsBucket {
  date: string;
  documents_uploaded: number;
  documents_analyzed: number;
  questions_asked: number;
  flags_found: number;
  avg_verification_score?: number | null;
}

export interface AnalyticsResult {
  documents_uploaded: number;
  documents_analyzed: number;
  questions_asked: number;
  flags_found: number;
  avg_verification_score?: number | null;
  by_day: DailyAnalyticsBucket[];
}

export async function fetchAnalytics(): Promise<AnalyticsResult> {
  const base = getApiBase();
  const res = await fetch(`${base}/analytics`);
  if (!res.ok) {
    throw new Error("Failed to fetch analytics");
  }
  return res.json();
}

export interface SearchChunkMatch {
  chunk_id?: string | null;
  content: string;
  page: number;
  section_path?: string | null;
  chunk_type: string;
  score: number;
}

export interface SearchDocumentGroup {
  document_id?: string | null;
  filename: string;
  session_id?: string | null;
  max_score: number;
  matches: SearchChunkMatch[];
}

export interface CrossDocSearchResult {
  query: string;
  scope: string;
  total_matches: number;
  documents: SearchDocumentGroup[];
}

export async function searchLibrary(
  query: string,
  options?: { sessionId?: string; scope?: "library" | "session"; topK?: number }
): Promise<CrossDocSearchResult> {
  const base = getApiBase();
  const res = await fetch(`${base}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      query,
      session_id: options?.sessionId,
      scope: options?.scope ?? "library",
      top_k: options?.topK ?? 12,
    }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Search failed");
  }
  return res.json();
}
