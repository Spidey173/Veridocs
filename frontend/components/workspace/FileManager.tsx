"use client";

import { useAppStore } from "@/lib/store";
import {
  FileText,
  Upload,
  Scale,
  Sparkles,
  ChevronDown,
  ChevronRight,
  Info,
  DollarSign,
  Calendar,
  Building,
  User,
  Hash,
  ArrowRight,
  Loader2,
  Trash2,
} from "lucide-react";
import { uploadDocuments, getInsights, deleteDocument } from "@/lib/api";
import { useRef, useState } from "react";
import type { UploadedFile } from "@/lib/store";

export default function FileManager() {
  const {
    sessionId,
    files,
    activeDocumentName,
    isUploading,
    insights,
    isLoadingInsights,
    setActiveDocument,
    setSession,
    setUploading,
    setUploadProgress,
    setInsights,
    setLoadingInsights,
    setLocalFileUrls,
    setActiveWorkspaceTab,
    setPendingQuestion,
  } = useAppStore();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [insightsExpanded, setInsightsExpanded] = useState(true);

  const handleAddFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0) return;
    const acceptedFiles = Array.from(e.target.files);

    setUploading(true);
    setUploadProgress(0, "Staging document...");

    try {
      const blobUrls: Record<string, string> = {};
      acceptedFiles.forEach((f) => {
        blobUrls[f.name] = URL.createObjectURL(f);
      });
      setLocalFileUrls(blobUrls);

      setUploadProgress(20, "Uploading to workspace...");
      const result = await uploadDocuments(
        acceptedFiles,
        (progress) => {
          setUploadProgress(Math.min(progress * 0.7, 70), "Uploading...");
        },
        sessionId || undefined
      );

      setUploadProgress(85, "Updating index & coordinate maps...");

      const newFiles: UploadedFile[] = acceptedFiles.map((f) => ({
        name: f.name,
        size: f.size,
        type: f.type,
      }));

      const updatedFiles = [...files, ...newFiles];
      setSession(result.session_id, updatedFiles);
      setUploadProgress(100, "Ready");
      setUploading(false);

      // Refresh insights in the background
      setLoadingInsights(true);
      getInsights(result.session_id, newFiles[0]?.name)
        .then((ins) => {
          if (ins) setInsights(ins);
        })
        .catch((err) => {
          console.warn("Background insights fetch:", err);
        })
        .finally(() => {
          setLoadingInsights(false);
        });
    } catch (err) {
      console.error(err);
      setUploading(false);
    }
  };

  const triggerUpload = () => {
    fileInputRef.current?.click();
  };

  const handleQuestionClick = (q: string) => {
    setPendingQuestion(q);
    setActiveWorkspaceTab("chat");
  };

  // Group entities by classification
  const entities = insights?.key_entities || [];

  return (
    <div className="w-full h-full flex flex-col bg-[var(--bg-surface)] border-r border-[var(--border-subtle)] select-none text-[var(--text-primary)]">
      {/* Hidden file input */}
      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.txt"
        onChange={handleAddFile}
        className="hidden"
      />

      {/* Top Action Header */}
      <div className="p-3 border-b border-[var(--border-subtle)] space-y-2 shrink-0">
        <div className="flex items-center justify-between">
          <span className="text-[10px] font-mono-data font-semibold text-[var(--text-muted)] uppercase tracking-wider">
            Workspace Corpus ({files.length})
          </span>
          <button
            type="button"
            onClick={triggerUpload}
            disabled={isUploading}
            className="inline-flex items-center gap-1 text-[11px] font-medium text-[var(--color-accent)] hover:underline disabled:opacity-50"
          >
            <Upload className="w-3 h-3" />
            <span>Add Document</span>
          </button>
        </div>

        {/* Forensic Diff Trigger Button (when 2+ docs) */}
        {files.length >= 2 && (
          <button
            type="button"
            onClick={() => setActiveWorkspaceTab("contradictions")}
            className="w-full flex items-center justify-between py-1.5 px-2.5 rounded border border-[var(--border-default)] bg-[var(--bg-surface-raised)] hover:bg-[var(--bg-subtle)] text-xs font-medium text-[var(--text-primary)] transition-colors"
          >
            <div className="flex items-center gap-2">
              <Scale className="w-3.5 h-3.5 text-[var(--color-accent)] shrink-0" />
              <span>Contradiction Matrix</span>
            </div>
            <span className="text-[10px] font-mono-data px-1.5 py-0.2 rounded bg-[var(--color-accent-subtle)] text-[var(--color-accent)] border border-[var(--color-accent-border)] font-bold">
              DIFF
            </span>
          </button>
        )}
      </div>

      {/* Scrollable Document List & Insights */}
      <div className="flex-1 overflow-y-auto divide-y divide-[var(--border-subtle)]">
        {/* Document List */}
        <div className="p-2 space-y-0.5">
          {files.map((file) => {
            const isActive = activeDocumentName === file.name;

            return (
              <div
                key={file.name}
                onClick={() => setActiveDocument(file.name)}
                className={`
                  group flex items-center gap-2 p-2 rounded cursor-pointer transition-colors text-xs
                  ${
                    isActive
                      ? "bg-[var(--bg-subtle)] border-l-2 border-l-[var(--color-accent)] font-medium text-[var(--text-primary)]"
                      : "hover:bg-[var(--bg-surface-raised)] text-[var(--text-secondary)] border-l-2 border-l-transparent"
                  }
                `}
              >
                <FileText
                  className={`w-3.5 h-3.5 shrink-0 ${
                    isActive ? "text-[var(--color-accent)]" : "text-[var(--text-muted)] group-hover:text-[var(--text-secondary)]"
                  }`}
                />

                <div className="flex-1 min-w-0">
                  <p className="truncate">{file.name}</p>
                </div>
              </div>
            );
          })}
        </div>

        {/* Document Insights Section (Screen 4) */}
        <div className="p-3 space-y-3">
          <div
            onClick={() => setInsightsExpanded(!insightsExpanded)}
            className="flex items-center justify-between cursor-pointer text-[10px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            <div className="flex items-center gap-1.5">
              <span>Document Insights</span>
              {isLoadingInsights && (
                <Loader2 className="w-2.5 h-2.5 animate-spin text-[var(--color-accent)]" />
              )}
            </div>
            {insightsExpanded ? (
              <ChevronDown className="w-3 h-3" />
            ) : (
              <ChevronRight className="w-3 h-3" />
            )}
          </div>

          {insightsExpanded && (
            <div className="space-y-4">
              {/* Executive Summary */}
              {insights?.executive_summary && (
                <div className="space-y-1.5 text-xs">
                  <p className="text-[11px] font-semibold text-[var(--text-secondary)] font-mono-data uppercase tracking-wider">
                    Summary & Purpose
                  </p>
                  <p className="text-[12px] text-[var(--text-secondary)] leading-relaxed bg-[var(--bg-surface-raised)] p-2 rounded border border-[var(--border-subtle)]">
                    {insights.executive_summary.purpose}
                  </p>

                  {insights.executive_summary.key_findings &&
                    insights.executive_summary.key_findings.length > 0 && (
                      <div className="space-y-1 pt-1">
                        <p className="text-[10px] font-mono-data text-[var(--text-muted)] uppercase tracking-wider">
                          Key Provisions
                        </p>
                        <ul className="space-y-1 pl-3 text-[11.5px] text-[var(--text-secondary)] list-disc marker:text-[var(--color-accent)]">
                          {insights.executive_summary.key_findings.map((finding, idx) => (
                            <li key={idx} className="leading-snug">
                              {finding}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                </div>
              )}

              {/* Extracted Entities as Quiet Tags */}
              {entities.length > 0 && (
                <div className="space-y-1.5">
                  <p className="text-[10px] font-mono-data text-[var(--text-muted)] uppercase tracking-wider">
                    Identified Entities ({entities.length})
                  </p>
                  <div className="flex flex-wrap gap-1">
                    {entities.map((ent, idx) => (
                      <span
                        key={idx}
                        className="inline-flex items-center gap-1 text-[10.5px] font-mono-data px-1.5 py-0.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface-raised)] text-[var(--text-secondary)]"
                        title={`Entity: ${ent.value} (${ent.entity_type}${ent.page ? ` · Page ${ent.page}` : ""})`}
                      >
                        <span className="text-[9px] text-[var(--text-muted)] uppercase font-semibold">
                          {ent.entity_type}:
                        </span>
                        <span className="truncate max-w-[130px] font-medium text-[var(--text-primary)]">
                          {ent.value}
                        </span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Suggested Questions as Plain Clickable Lines (Screen 4) */}
              {insights?.suggested_questions && insights.suggested_questions.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="text-[10px] font-mono-data text-[var(--text-muted)] uppercase tracking-wider">
                    Suggested Inquiries
                  </p>
                  <div className="space-y-1">
                    {insights.suggested_questions.map((q, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => handleQuestionClick(q)}
                        className="w-full text-left py-1 px-1.5 rounded hover:bg-[var(--bg-subtle)] text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)] transition-colors flex items-start gap-1.5 group"
                      >
                        <span className="text-[var(--color-accent)] shrink-0 font-mono-data font-bold mt-0.5">
                          ›
                        </span>
                        <span className="line-clamp-2 leading-relaxed">{q}</span>
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
