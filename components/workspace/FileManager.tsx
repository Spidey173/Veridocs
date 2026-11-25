"use client";

import { useAppStore } from "@/lib/store";
import {
  FileText,
  Trash2,
  Loader2,
  Plus,
  Table as TableIcon,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Tag,
  FileSpreadsheet,
  GitCompare,
  ShieldAlert,
  Network,
  Sparkles,
  FileBarChart,
} from "lucide-react";
import {
  uploadDocumentAsync,
  subscribeDocumentStatus,
  deleteDocument,
  fetchDocumentTables,
  fetchDocumentEntities,
  fetchDocumentExtraction,
  retryDocumentProcessing,
  type ExtractedTable,
} from "@/lib/api";
import { useRef, useEffect, useState } from "react";
import dynamic from "next/dynamic";
import type { UploadedFile } from "@/lib/store";

const EntitiesViewer = dynamic(() => import("./EntitiesViewer"), { ssr: false });
const FieldsViewer = dynamic(() => import("./FieldsViewer"), { ssr: false });
const CompareViewer = dynamic(() => import("./CompareViewer"), { ssr: false });
const FlagsViewer = dynamic(() => import("./FlagsViewer"), { ssr: false });
const GraphViewer = dynamic(() => import("./GraphViewer"), { ssr: false });
const SummaryViewer = dynamic(() => import("./SummaryViewer"), { ssr: false });
const ReportViewer = dynamic(() => import("./ReportViewer"), { ssr: false });

export default function FileManager() {
  const {
    sessionId,
    files,
    activeDocumentName,
    isUploading,
    documentTables,
    activeSidebarTab,
    setActiveSidebarTab,
    setDocumentTables,
    documentEntities,
    documentExtractions,
    setDocumentEntities,
    setDocumentExtraction,
    setActiveDocument,
    setSession,
    updateFile,
    setUploading,
    setUploadProgress,
    setLocalFileUrls,
  } = useAppStore();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [loadingTables, setLoadingTables] = useState(false);

  // Active document object
  const activeFile = files.find((f) => f.name === activeDocumentName) || files[0];
  const activeDocId = activeFile?.documentId;
  const currentTables: ExtractedTable[] = (activeDocId && documentTables[activeDocId]) || [];

  // Fetch tables, entities, or fields when switching tabs or selecting document
  useEffect(() => {
    if (!activeDocId) return;

    if (activeSidebarTab === "tables" && !documentTables[activeDocId]) {
      setLoadingTables(true);
      fetchDocumentTables(activeDocId)
        .then((tabs) => setDocumentTables(activeDocId, tabs))
        .finally(() => setLoadingTables(false));
    } else if (activeSidebarTab === "entities" && !documentEntities[activeDocId]) {
      fetchDocumentEntities(activeDocId)
        .then((ents) => setDocumentEntities(activeDocId, ents));
    } else if (activeSidebarTab === "fields" && !documentExtractions[activeDocId]) {
      fetchDocumentExtraction(activeDocId)
        .then((ext) => {
          if (ext) setDocumentExtraction(activeDocId, ext);
        });
    }
  }, [
    activeDocId,
    activeSidebarTab,
    documentTables,
    documentEntities,
    documentExtractions,
    setDocumentTables,
    setDocumentEntities,
    setDocumentExtraction,
  ]);

  const handleAddFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const acceptedFiles = Array.from(e.target.files);

    setUploading(true);
    setUploadProgress(15);

    try {
      const blobUrls: Record<string, string> = {};
      acceptedFiles.forEach((f) => {
        blobUrls[f.name] = URL.createObjectURL(f);
      });
      setLocalFileUrls(blobUrls);

      const targetSessionId = sessionId || `session-${Date.now()}`;

      // Upload each file and subscribe to SSE progress
      for (const f of acceptedFiles) {
        const initialFile: UploadedFile = {
          name: f.name,
          size: f.size,
          type: f.type,
          status: "queued",
        };

        // Add file immediately with "queued" status
        const merged = [...files.filter((x) => x.name !== f.name), initialFile];
        setSession(targetSessionId, merged);
        setActiveDocument(f.name);

        try {
          const resp = await uploadDocumentAsync(f, targetSessionId);
          updateFile(f.name, {
            documentId: resp.document_id,
            status: "parsing",
          });

          // Subscribe to SSE progress events
          const unsubscribe = subscribeDocumentStatus(resp.document_id, (ev) => {
            updateFile(f.name, {
              status: ev.status,
              pages: ev.page_count,
              error: ev.error,
            });

            if (ev.status === "ready" || ev.status === "failed") {
              // Load tables if ready
              if (ev.status === "ready") {
                fetchDocumentTables(resp.document_id).then((tabs) => {
                  setDocumentTables(resp.document_id, tabs);
                });
              }
              unsubscribe();
            }
          });
        } catch (uploadErr: any) {
          updateFile(f.name, {
            status: "failed",
            error: uploadErr.message || "Upload failed",
          });
        }
      }

      setUploading(false);
    } catch (err) {
      console.error("Upload error:", err);
      setUploading(false);
    }
  };

  const handleRetry = async (e: React.MouseEvent, file: UploadedFile) => {
    e.stopPropagation();
    if (!file.documentId) return;

    updateFile(file.name, { status: "queued", error: undefined });
    try {
      await retryDocumentProcessing(file.documentId);
      const unsubscribe = subscribeDocumentStatus(file.documentId, (ev) => {
        updateFile(file.name, {
          status: ev.status,
          pages: ev.page_count,
          error: ev.error,
        });
        if (ev.status === "ready" || ev.status === "failed") {
          unsubscribe();
        }
      });
    } catch (err: any) {
      updateFile(file.name, { status: "failed", error: err.message });
    }
  };

  const handleDeleteFile = async (e: React.MouseEvent, docName: string) => {
    e.stopPropagation();
    if (!sessionId) return;
    try {
      await deleteDocument(sessionId, docName);
      const remaining = files.filter((f) => f.name !== docName);
      setSession(sessionId, remaining);
      if (activeDocumentName === docName) {
        setActiveDocument(remaining[0]?.name || null);
      }
    } catch (err) {
      console.error("Delete document error:", err);
    }
  };

  const getStatusBadge = (file: UploadedFile) => {
    if (file.status === "ready") {
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono-data bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
          <CheckCircle2 className="w-2.5 h-2.5" />
          <span>Ready</span>
        </span>
      );
    }

    if (file.status === "failed") {
      return (
        <div className="flex items-center gap-1">
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono-data bg-rose-500/10 text-rose-500 border border-rose-500/20" title={file.error}>
            <AlertTriangle className="w-2.5 h-2.5" />
            <span>Failed</span>
          </span>
          <button
            type="button"
            onClick={(e) => handleRetry(e, file)}
            className="p-1 text-[var(--color-accent)] hover:bg-[var(--bg-subtle)] rounded transition-colors"
            title="Retry processing"
          >
            <RefreshCw className="w-2.5 h-2.5" />
          </button>
        </div>
      );
    }

    if (file.status) {
      const stageLabels: Record<string, string> = {
        queued: "Queued",
        parsing: "Parsing...",
        ocr: "OCR Check...",
        chunking: "Chunking...",
        embedding: "Embedding...",
      };
      return (
        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono-data bg-[var(--color-accent-subtle)] text-[var(--color-accent)] border border-[var(--color-accent-border)]">
          <Loader2 className="w-2.5 h-2.5 animate-spin" />
          <span>{stageLabels[file.status] || file.status}</span>
        </span>
      );
    }

    return null;
  };

  return (
    <div className="w-full h-full flex flex-col bg-[var(--bg-surface)] text-[var(--text-primary)] select-none">
      {/* Top Tab Switcher: Documents vs Tables vs Entities vs Fields */}
      <div className="h-10 px-2 border-b border-[var(--border-subtle)] flex items-center justify-between shrink-0 bg-[var(--bg-canvas)] overflow-x-auto">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setActiveSidebarTab("documents")}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              activeSidebarTab === "documents"
                ? "bg-[var(--bg-surface)] text-[var(--color-accent)] font-semibold shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Files ({files.length})</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSidebarTab("tables")}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              activeSidebarTab === "tables"
                ? "bg-[var(--bg-surface)] text-[var(--color-accent)] font-semibold shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            <TableIcon className="w-3.5 h-3.5" />
            <span>Tables {currentTables.length > 0 && `(${currentTables.length})`}</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSidebarTab("entities")}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              activeSidebarTab === "entities"
                ? "bg-[var(--bg-surface)] text-[var(--color-accent)] font-semibold shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            <Tag className="w-3.5 h-3.5" />
            <span>Entities</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSidebarTab("fields")}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              activeSidebarTab === "fields"
                ? "bg-[var(--bg-surface)] text-[var(--color-accent)] font-semibold shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            <FileSpreadsheet className="w-3.5 h-3.5" />
            <span>Fields</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSidebarTab("summary")}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              activeSidebarTab === "summary"
                ? "bg-[var(--bg-surface)] text-[var(--color-accent)] font-semibold shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Summary</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSidebarTab("report")}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              activeSidebarTab === "report"
                ? "bg-[var(--bg-surface)] text-[var(--color-accent)] font-semibold shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            <FileBarChart className="w-3.5 h-3.5" />
            <span>Report</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSidebarTab("compare")}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              activeSidebarTab === "compare"
                ? "bg-[var(--bg-surface)] text-[var(--color-accent)] font-semibold shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            <GitCompare className="w-3.5 h-3.5" />
            <span>Compare</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSidebarTab("flags")}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              activeSidebarTab === "flags"
                ? "bg-[var(--bg-surface)] text-[var(--color-accent)] font-semibold shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            <ShieldAlert className="w-3.5 h-3.5" />
            <span>Flags</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveSidebarTab("graph")}
            className={`flex items-center gap-1 px-2 py-1 rounded text-xs font-medium transition-colors ${
              activeSidebarTab === "graph"
                ? "bg-[var(--bg-surface)] text-[var(--color-accent)] font-semibold shadow-sm"
                : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
            }`}
          >
            <Network className="w-3.5 h-3.5" />
            <span>Graph</span>
          </button>
        </div>

        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="flex items-center gap-1 px-2 py-1 rounded bg-[var(--color-accent-subtle)] text-[var(--color-accent)] hover:bg-[var(--color-accent)] hover:text-white text-[11px] font-medium transition-colors shrink-0 ml-1"
          title="Add PDF, DOCX, DOC, TXT, or Scanned Image"
        >
          <Plus className="w-3 h-3" />
          <span>Add</span>
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.tiff,.tif"
          multiple
          onChange={handleAddFile}
          className="hidden"
        />
      </div>

      {/* Tab 1: Documents */}
      {activeSidebarTab === "documents" && (
        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {files.length === 0 ? (
            <div className="p-4 text-center text-xs text-[var(--text-muted)]">
              <p>No documents in workspace.</p>
            </div>
          ) : (
            files.map((file) => {
              const isActive = file.name === activeDocumentName;
              return (
                <div
                  key={file.name}
                  onClick={() => setActiveDocument(file.name)}
                  className={`w-full flex flex-col p-2 rounded cursor-pointer text-xs transition-colors group space-y-1.5 ${
                    isActive
                      ? "bg-[var(--color-accent-subtle)] border border-[var(--color-accent-border)] text-[var(--color-accent)] font-medium"
                      : "hover:bg-[var(--bg-subtle)] text-[var(--text-secondary)] border border-transparent"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 truncate min-w-0">
                      <FileText className="w-3.5 h-3.5 shrink-0" />
                      <span className="truncate font-semibold text-[11.5px]">{file.name}</span>
                    </div>

                    <button
                      type="button"
                      onClick={(e) => handleDeleteFile(e, file.name)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:text-red-500 transition-opacity ml-1"
                      title="Remove document"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  {/* Status chip & OCR metadata */}
                  <div className="flex items-center justify-between text-[10px] font-mono-data text-[var(--text-muted)]">
                    <div className="flex items-center gap-1.5">
                      {file.extractionMethod && (
                        <span className="px-1 py-0.2 rounded bg-[var(--bg-canvas)] border border-[var(--border-subtle)]">
                          {file.extractionMethod === "ocr" ? "OCR" : "Text"}
                        </span>
                      )}
                      {file.ocrConfidence !== undefined && file.ocrConfidence !== null && (
                        <span>{Math.round(file.ocrConfidence * 100)}% conf</span>
                      )}
                      {file.pages && <span>{file.pages} p.</span>}
                      {file.doc_type && (
                        <span className="px-1 py-0.2 rounded bg-primary/10 text-primary capitalize font-medium">
                          {file.doc_type}
                        </span>
                      )}
                    </div>

                    {getStatusBadge(file)}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {/* Tab 2: Tables */}
      {activeSidebarTab === "tables" && (
        <div className="flex-1 overflow-y-auto p-2 space-y-3">
          {loadingTables ? (
            <div className="p-4 text-center text-xs text-[var(--text-muted)] flex items-center justify-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--color-accent)]" />
              <span>Loading extracted tables...</span>
            </div>
          ) : currentTables.length === 0 ? (
            <div className="p-4 text-center text-xs text-[var(--text-muted)] space-y-1">
              <p className="font-semibold text-[var(--text-primary)]">No Tables Detected</p>
              <p className="text-[11px]">
                {activeDocumentName
                  ? `No tabular data extracted from ${activeDocumentName}.`
                  : "Select a document to inspect its extracted tables."}
              </p>
            </div>
          ) : (
            currentTables.map((table, tIdx) => (
              <div
                key={table.id || tIdx}
                className="border border-[var(--border-subtle)] rounded bg-[var(--bg-surface)] p-2.5 space-y-2 text-xs"
              >
                <div className="flex items-center justify-between font-mono-data text-[10.5px] text-[var(--text-secondary)] border-b border-[var(--border-subtle)] pb-1.5">
                  <span className="font-semibold flex items-center gap-1">
                    <TableIcon className="w-3 h-3 text-[var(--color-accent)]" />
                    <span>Table {tIdx + 1}</span>
                  </span>
                  <span className="text-[var(--color-accent)]">Page {table.page_number}</span>
                </div>

                {table.json?.rows && table.json.rows.length > 0 ? (
                  <div className="overflow-x-auto border border-[var(--border-subtle)] rounded max-h-48">
                    <table className="w-full text-left text-[11px] border-collapse font-sans">
                      {table.json.headers && table.json.headers.length > 0 && (
                        <thead className="bg-[var(--bg-subtle)] border-b border-[var(--border-subtle)] font-semibold text-[var(--text-primary)]">
                          <tr>
                            {table.json.headers.map((h, hIdx) => (
                              <th key={hIdx} className="px-2 py-1 font-medium border-r border-[var(--border-subtle)] last:border-0">
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                      )}
                      <tbody>
                        {table.json.rows.map((row, rIdx) => (
                          <tr key={rIdx} className="border-b border-[var(--border-subtle)] last:border-0 hover:bg-[var(--bg-subtle)]/50">
                            {row.map((cell, cIdx) => (
                              <td key={cIdx} className="px-2 py-1 text-[var(--text-secondary)] border-r border-[var(--border-subtle)] last:border-0 truncate max-w-[120px]">
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <pre className="p-2 rounded bg-[var(--bg-canvas)] text-[10px] font-mono overflow-x-auto whitespace-pre-wrap">
                    {table.markdown}
                  </pre>
                )}
              </div>
            ))
          )}
        </div>
      )}

      {/* Tab 3: Entities */}
      {activeSidebarTab === "entities" && (
        <div className="flex-1 overflow-y-auto">
          <EntitiesViewer entities={(activeDocId && documentEntities[activeDocId]) || []} />
        </div>
      )}

      {/* Tab 4: Fields */}
      {activeSidebarTab === "fields" && (
        <div className="flex-1 overflow-y-auto">
          <FieldsViewer
            documentId={activeDocId || ""}
            extraction={(activeDocId && documentExtractions[activeDocId]) || null}
            currentDocType={activeFile?.doc_type}
          />
        </div>
      )}

      {/* Tab 4b: Summary */}
      {activeSidebarTab === "summary" && (
        <div className="flex-1 overflow-y-auto">
          <SummaryViewer documentId={activeDocId || ""} />
        </div>
      )}

      {/* Tab 4c: Report */}
      {activeSidebarTab === "report" && (
        <div className="flex-1 overflow-y-auto">
          <ReportViewer documentId={activeDocId || ""} />
        </div>
      )}

      {/* Tab 5: Compare */}
      {activeSidebarTab === "compare" && (
        <div className="flex-1 overflow-y-auto">
          <CompareViewer />
        </div>
      )}

      {/* Tab 6: Flags */}
      {activeSidebarTab === "flags" && (
        <div className="flex-1 overflow-y-auto">
          <FlagsViewer documentId={activeDocId || ""} />
        </div>
      )}

      {/* Tab 7: Graph */}
      {activeSidebarTab === "graph" && (
        <div className="flex-1 overflow-y-auto">
          <GraphViewer documentId={activeDocId || ""} />
        </div>
      )}
    </div>
  );
}
