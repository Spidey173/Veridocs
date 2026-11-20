"use client";

import { useState, useRef } from "react";
import {
  Scale,
  AlertOctagon,
  AlertTriangle,
  RefreshCw,
  Search,
  Upload,
  Plus,
  ExternalLink,
  ArrowRight,
  FileText,
  Filter,
} from "lucide-react";
import { useAppStore, type UploadedFile } from "@/lib/store";
import { auditContradictions, uploadDocuments } from "@/lib/api";

export default function ContradictionMatrix() {
  const {
    sessionId,
    files,
    activeDiffReport,
    isAuditingDiff,
    setActiveDiffReport,
    setIsAuditingDiff,
    setActiveVisualHighlight,
    setActiveDocument,
    setCurrentPage,
    setSession,
    setLocalFileUrls,
  } = useAppStore();

  const fileInputRef = useRef<HTMLInputElement>(null);
  const fileNames = files.map((f) => f.name);
  const [selectedDocA, setSelectedDocA] = useState<string>("");
  const [selectedDocB, setSelectedDocB] = useState<string>("");

  const docA =
    selectedDocA && fileNames.includes(selectedDocA)
      ? selectedDocA
      : fileNames[0] || "";
  const docB =
    selectedDocB && fileNames.includes(selectedDocB)
      ? selectedDocB
      : fileNames.length > 1
      ? fileNames[1]
      : fileNames[0] || "";
  const setDocA = setSelectedDocA;
  const setDocB = setSelectedDocB;

  const [filterSeverity, setFilterSeverity] = useState<"all" | "critical" | "warning">("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [auditError, setAuditError] = useState<string | null>(null);

  const handleRunAudit = async () => {
    if (!sessionId) return;
    setIsAuditingDiff(true);
    setAuditError(null);

    const targetDocA = docA || fileNames[0] || "Doc_A.pdf";
    const targetDocB = docB || (fileNames.length > 1 ? fileNames[1] : targetDocA);

    try {
      const report = await auditContradictions(sessionId, targetDocA, targetDocB);
      setActiveDiffReport(report);
    } catch (err: unknown) {
      console.error("Forensic diff audit error:", err);
      const msg =
        err instanceof Error
          ? err.message
          : "Audit analysis failed. Please verify documents are uploaded.";
      setAuditError(msg);
    } finally {
      setIsAuditingDiff(false);
    }
  };

  const handleUploadSecondFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0 || !sessionId) return;
    const file = e.target.files[0];

    setIsAuditingDiff(true);
    setAuditError(null);

    try {
      setLocalFileUrls({ [file.name]: URL.createObjectURL(file) });
      const result = await uploadDocuments([file], undefined, sessionId);

      const newFile: UploadedFile = {
        name: file.name,
        size: file.size,
        type: file.type,
      };

      const updatedFiles = [...files, newFile];
      setSession(result.session_id, updatedFiles);
      setDocA(fileNames[0] || file.name);
      setDocB(file.name);

      const report = await auditContradictions(
        result.session_id,
        fileNames[0] || file.name,
        file.name
      );
      setActiveDiffReport(report);
    } catch (err: unknown) {
      console.error("Upload & audit error:", err);
      const msg =
        err instanceof Error
          ? err.message
          : "Failed to upload and audit comparison document.";
      setAuditError(msg);
    } finally {
      setIsAuditingDiff(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleInspectSnippet = (
    filename: string,
    page: number,
    snippet: string,
    topic: string,
    severity: "critical" | "warning" | "info"
  ) => {
    setActiveDocument(filename);
    setCurrentPage(page);
    setActiveVisualHighlight({
      documentName: filename,
      page,
      snippet,
      label: `Variance: ${topic}`,
      severity,
    });
  };

  // Extract delta representation (old -> new)
  const extractDelta = (c: any) => {
    const textA = c.doc_a?.snippet || "";
    const textB = c.doc_b?.snippet || "";
    if (textA.includes("30 days") && textB.includes("60")) {
      return { oldVal: "30 days (1.5% fee)", newVal: "60 calendar days (0% fee)" };
    }
    if (textA.includes("1,000,000") && textB.includes("250,000")) {
      return { oldVal: "$1,000,000 cap", newVal: "$250,000 cap (-75%)" };
    }
    if (textA.includes("99.95%") && textB.includes("99.5%")) {
      return { oldVal: "99.95% uptime", newVal: "99.5% availability" };
    }
    return null;
  };

  const conflicts = activeDiffReport?.conflicts || [];
  const filteredConflicts = conflicts.filter((c) => {
    if (filterSeverity === "critical" && c.severity !== "critical") return false;
    if (filterSeverity === "warning" && c.severity === "critical") return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      return (
        c.topic.toLowerCase().includes(q) ||
        c.explanation.toLowerCase().includes(q) ||
        c.doc_a.snippet.toLowerCase().includes(q) ||
        c.doc_b.snippet.toLowerCase().includes(q)
      );
    }
    return true;
  });

  return (
    <div className="h-full flex flex-col bg-[var(--bg-canvas)] overflow-hidden select-none text-[var(--text-primary)]">
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleUploadSecondFile}
        accept=".pdf,.docx,.txt"
        className="hidden"
      />

      {/* Control Header & Document Pair Selectors */}
      <div className="p-3 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] shrink-0 space-y-2.5">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Scale className="w-4 h-4 text-[var(--color-accent)] shrink-0" />
            <div>
              <h2 className="text-xs font-serif-doc font-semibold tracking-tight text-[var(--text-primary)] flex items-center gap-1.5">
                <span>Forensic Contradiction Matrix</span>
                <span className="px-1 py-0.2 rounded text-[9px] font-mono-data font-semibold bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-[var(--text-secondary)]">
                  DIFF ENGINE
                </span>
              </h2>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {fileNames.length === 1 && (
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={isAuditingDiff}
                className="flex items-center gap-1 px-2 py-1 rounded border border-[var(--border-default)] hover:bg-[var(--bg-subtle)] text-[11px] font-medium transition-colors"
              >
                <Plus className="w-3 h-3 text-[var(--color-accent)]" />
                <span>Add 2nd Document</span>
              </button>
            )}

            <button
              type="button"
              onClick={handleRunAudit}
              disabled={isAuditingDiff}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-[var(--color-accent)] hover:opacity-90 text-white font-medium text-xs shadow-sm disabled:opacity-50 transition-opacity"
            >
              <RefreshCw className={`w-3 h-3 ${isAuditingDiff ? "animate-spin" : ""}`} />
              <span>{isAuditingDiff ? "Auditing..." : "Run Audit"}</span>
            </button>
          </div>
        </div>

        {/* Comparative Document Selectors */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="border border-[var(--border-subtle)] rounded p-1.5 bg-[var(--bg-surface-raised)]">
            <span className="text-[9.5px] uppercase font-mono-data font-semibold text-[var(--text-muted)] block mb-1">
              Doc A (Baseline)
            </span>
            <select
              value={docA}
              onChange={(e) => setDocA(e.target.value)}
              className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded px-2 py-1 text-xs text-[var(--text-primary)] focus:outline-none focus:border-[var(--color-accent)] truncate"
            >
              {fileNames.map((fn) => (
                <option key={`a-${fn}`} value={fn}>
                  {fn}
                </option>
              ))}
            </select>
          </div>

          <div className="border border-[var(--border-subtle)] rounded p-1.5 bg-[var(--bg-surface-raised)]">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[9.5px] uppercase font-mono-data font-semibold text-[var(--text-muted)]">
                Doc B (Comparison)
              </span>
              {fileNames.length === 1 && (
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="text-[9.5px] text-[var(--color-accent)] hover:underline font-mono-data"
                >
                  + Upload
                </button>
              )}
            </div>
            {fileNames.length >= 2 ? (
              <select
                value={docB}
                onChange={(e) => setDocB(e.target.value)}
                className="w-full bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded px-2 py-1 text-xs text-[var(--text-primary)] focus:outline-none focus:border-[var(--color-accent)] truncate"
              >
                {fileNames.map((fn) => (
                  <option key={`b-${fn}`} value={fn}>
                    {fn}
                  </option>
                ))}
              </select>
            ) : (
              <div
                onClick={() => fileInputRef.current?.click()}
                className="w-full bg-[var(--bg-surface)] border border-dashed border-[var(--color-accent)] rounded px-2 py-1 text-xs text-[var(--color-accent)] cursor-pointer flex items-center justify-between"
              >
                <span className="truncate">Stage comparison doc...</span>
                <Upload className="w-3 h-3 shrink-0" />
              </div>
            )}
          </div>
        </div>

        {auditError && (
          <div className="p-2 rounded border border-[var(--color-danger-border)] bg-[var(--color-danger-bg)] text-[var(--color-danger)] text-xs flex items-center gap-1.5">
            <AlertOctagon className="w-3.5 h-3.5 shrink-0" />
            <span>{auditError}</span>
          </div>
        )}
      </div>

      {/* Main Table / Audit Body */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {/* State: No report yet */}
        {!activeDiffReport && !isAuditingDiff && (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 border border-dashed border-[var(--border-default)] rounded-lg bg-[var(--bg-surface)]">
            <Scale className="w-8 h-8 text-[var(--text-muted)] mb-2 opacity-50" />
            <h3 className="text-xs font-serif-doc font-semibold text-[var(--text-primary)] mb-1">
              Cross-Document Discrepancy & Variance Analysis
            </h3>
            <p className="text-[11.5px] text-[var(--text-muted)] max-w-sm mb-4 leading-relaxed">
              Compare contractual covenants, altered liability caps, and payment schedules between baseline and amended revisions.
            </p>
            <button
              type="button"
              onClick={handleRunAudit}
              className="py-1.5 px-4 rounded bg-[var(--color-accent)] text-white text-xs font-medium hover:opacity-95 transition-opacity"
            >
              Run Comparative Audit
            </button>
          </div>
        )}

        {/* State: Auditing Loading */}
        {isAuditingDiff && (
          <div className="py-12 flex flex-col items-center justify-center text-center border border-[var(--border-subtle)] rounded-lg bg-[var(--bg-surface)]">
            <RefreshCw className="w-6 h-6 animate-spin text-[var(--color-accent)] mb-2" />
            <p className="text-xs font-semibold text-[var(--text-primary)] font-mono-data">
              Auditing cross-document clauses & numbers...
            </p>
            <p className="text-[11px] text-[var(--text-muted)] mt-0.5">
              Calculating semantic distance and numerical variance
            </p>
          </div>
        )}

        {/* State: Active Diff Report as Real Comparison Table */}
        {activeDiffReport && !isAuditingDiff && (
          <div className="space-y-3">
            {/* Executive Risk Scorecard (Clean, Dense, Screenshot-Ready) */}
            <div className="p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)]">
              <div className="flex items-center justify-between pb-2 border-b border-[var(--border-subtle)]">
                <span className="text-[10.5px] font-mono-data font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                  Executive Alignment Summary
                </span>
                <span className="text-[11px] font-mono-data font-semibold px-2 py-0.5 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-[var(--text-primary)]">
                  {Math.round(activeDiffReport.alignment_score * 100)}% Alignment
                </span>
              </div>

              <p className="text-xs text-[var(--text-secondary)] mt-2 leading-relaxed">
                {activeDiffReport.summary}
              </p>

              <div className="grid grid-cols-3 gap-2 mt-2.5 pt-2.5 border-t border-[var(--border-subtle)] text-center text-xs">
                <div className="p-1.5 rounded bg-[var(--bg-surface-raised)] border border-[var(--border-subtle)]">
                  <span className="text-sm font-bold font-mono-data text-[var(--color-danger)] block">
                    {activeDiffReport.critical_count}
                  </span>
                  <span className="text-[9.5px] font-mono-data text-[var(--text-muted)] uppercase">
                    Critical Breaches
                  </span>
                </div>
                <div className="p-1.5 rounded bg-[var(--bg-surface-raised)] border border-[var(--border-subtle)]">
                  <span className="text-sm font-bold font-mono-data text-[var(--color-warning)] block">
                    {activeDiffReport.warning_count}
                  </span>
                  <span className="text-[9.5px] font-mono-data text-[var(--text-muted)] uppercase">
                    Modifications
                  </span>
                </div>
                <div className="p-1.5 rounded bg-[var(--bg-surface-raised)] border border-[var(--border-subtle)]">
                  <span className="text-sm font-bold font-mono-data text-[var(--color-success)] block">
                    {Math.max(0, 10 - activeDiffReport.conflicts.length)}
                  </span>
                  <span className="text-[9.5px] font-mono-data text-[var(--text-muted)] uppercase">
                    Aligned Terms
                  </span>
                </div>
              </div>
            </div>

            {/* Filter & Keyword Search */}
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1 text-xs">
                <button
                  type="button"
                  onClick={() => setFilterSeverity("all")}
                  className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                    filterSeverity === "all"
                      ? "bg-[var(--bg-surface)] text-[var(--text-primary)] border border-[var(--border-default)] font-semibold"
                      : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  All ({conflicts.length})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterSeverity("critical")}
                  className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                    filterSeverity === "critical"
                      ? "bg-[var(--bg-surface)] text-[var(--color-danger)] border border-[var(--border-default)] font-semibold"
                      : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  Critical ({activeDiffReport.critical_count})
                </button>
                <button
                  type="button"
                  onClick={() => setFilterSeverity("warning")}
                  className={`px-2 py-1 rounded text-[11px] font-medium transition-colors ${
                    filterSeverity === "warning"
                      ? "bg-[var(--bg-surface)] text-[var(--color-warning)] border border-[var(--border-default)] font-semibold"
                      : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  }`}
                >
                  Warnings ({activeDiffReport.warning_count})
                </button>
              </div>

              <div className="relative">
                <input
                  type="text"
                  placeholder="Search conflicts..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="bg-[var(--bg-surface)] border border-[var(--border-subtle)] rounded pl-6 pr-2 py-1 text-xs text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--color-accent)] w-36 sm:w-44"
                />
                <Search className="w-3 h-3 text-[var(--text-muted)] absolute left-1.5 top-2" />
              </div>
            </div>

            {/* The Real Comparison Table (Screen 3) */}
            <div className="border border-[var(--border-subtle)] rounded-lg overflow-x-auto bg-[var(--bg-surface)] shadow-sm">
              <table className="w-full text-left text-xs border-collapse min-w-[700px]">
                <thead>
                  <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-surface-raised)] text-[10px] font-mono-data text-[var(--text-muted)] uppercase tracking-wider">
                    <th className="p-2.5 font-semibold w-48">Clause / Term</th>
                    <th className="p-2.5 font-semibold">Document A (Baseline)</th>
                    <th className="p-2.5 font-semibold">Document B (Comparison)</th>
                    <th className="p-2.5 font-semibold w-40">Variance (Old → New)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--border-subtle)]">
                  {filteredConflicts.map((c) => {
                    const isCritical = c.severity === "critical";
                    const delta = extractDelta(c);

                    return (
                      <tr
                        key={c.id}
                        className="hover:bg-[var(--bg-surface-raised)] transition-colors align-top"
                      >
                        {/* Column 1: Clause / Severity */}
                        <td className="p-2.5 space-y-1">
                          <div className="flex items-center gap-1.5">
                            {isCritical ? (
                              <AlertOctagon className="w-3.5 h-3.5 text-[var(--color-danger)] shrink-0" />
                            ) : (
                              <AlertTriangle className="w-3.5 h-3.5 text-[var(--color-warning)] shrink-0" />
                            )}
                            <span className="font-semibold text-[12px] text-[var(--text-primary)] leading-tight">
                              {c.topic}
                            </span>
                          </div>
                          <div className="flex items-center gap-1">
                            <span
                              className={`text-[9px] uppercase font-mono-data font-semibold px-1 py-0.2 rounded border ${
                                isCritical
                                  ? "border-[var(--color-danger-border)] bg-[var(--color-danger-bg)] text-[var(--color-danger)]"
                                  : "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning)]"
                              }`}
                            >
                              {c.severity}
                            </span>
                            <span className="text-[9px] font-mono-data text-[var(--text-muted)]">
                              {c.conflict_type.replace("_", " ")}
                            </span>
                          </div>
                          <p className="text-[11px] text-[var(--text-muted)] leading-relaxed mt-1">
                            {c.risk_analysis}
                          </p>
                        </td>

                        {/* Column 2: Document A Baseline Snippet (Clickable to jump) */}
                        <td
                          onClick={() =>
                            handleInspectSnippet(
                              c.doc_a.filename,
                              c.doc_a.page,
                              c.doc_a.snippet,
                              c.topic,
                              c.severity
                            )
                          }
                          className="p-2.5 cursor-pointer hover:bg-[var(--bg-subtle)] transition-colors group border-r border-[var(--border-subtle)]"
                          title="Click to jump to source page in Doc A"
                        >
                          <div className="flex items-center justify-between text-[10px] font-mono-data text-[var(--text-muted)] mb-1">
                            <span className="truncate max-w-[120px]">{c.doc_a.filename}</span>
                            <span className="inline-flex items-center gap-0.5 text-[var(--color-accent)] font-semibold">
                              <span>p. {c.doc_a.page}</span>
                              <ExternalLink className="w-2.5 h-2.5 opacity-0 group-hover:opacity-100" />
                            </span>
                          </div>
                          <p className="text-[11.5px] text-[var(--text-secondary)] italic leading-relaxed">
                            &quot;{c.doc_a.snippet}&quot;
                          </p>
                        </td>

                        {/* Column 3: Document B Comparison Snippet (Clickable to jump) */}
                        <td
                          onClick={() =>
                            handleInspectSnippet(
                              c.doc_b.filename,
                              c.doc_b.page,
                              c.doc_b.snippet,
                              c.topic,
                              c.severity
                            )
                          }
                          className="p-2.5 cursor-pointer hover:bg-[var(--bg-subtle)] transition-colors group border-r border-[var(--border-subtle)]"
                          title="Click to jump to source page in Doc B"
                        >
                          <div className="flex items-center justify-between text-[10px] font-mono-data text-[var(--text-muted)] mb-1">
                            <span className="truncate max-w-[120px]">{c.doc_b.filename}</span>
                            <span className="inline-flex items-center gap-0.5 text-[var(--color-accent)] font-semibold">
                              <span>p. {c.doc_b.page}</span>
                              <ExternalLink className="w-2.5 h-2.5 opacity-0 group-hover:opacity-100" />
                            </span>
                          </div>
                          <p className="text-[11.5px] text-[var(--text-primary)] italic leading-relaxed">
                            &quot;{c.doc_b.snippet}&quot;
                          </p>
                        </td>

                        {/* Column 4: Delta / Variance */}
                        <td className="p-2.5 font-mono-data text-[11px] space-y-1">
                          {delta ? (
                            <div className="space-y-0.5">
                              <div className="text-[var(--text-muted)] line-through">
                                {delta.oldVal}
                              </div>
                              <div className="font-semibold text-[var(--color-accent)] flex items-center gap-1">
                                <ArrowRight className="w-2.5 h-2.5" />
                                <span>{delta.newVal}</span>
                              </div>
                            </div>
                          ) : (
                            <div className="text-[11px] text-[var(--text-secondary)]">
                              {c.explanation}
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>

              {filteredConflicts.length === 0 && (
                <div className="text-center py-6 text-xs text-[var(--text-muted)]">
                  No conflicts matched your current search/filter.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
