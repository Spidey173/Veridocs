"use client";

import { useState, useRef } from "react";
import { motion } from "framer-motion";
import {
  Scale,
  AlertOctagon,
  AlertTriangle,
  Sparkles,
  ShieldAlert,
  RefreshCw,
  Search,
  Upload,
  Plus,
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

  const docA = (selectedDocA && fileNames.includes(selectedDocA)) ? selectedDocA : (fileNames[0] || "");
  const docB = (selectedDocB && fileNames.includes(selectedDocB)) ? selectedDocB : (fileNames.length > 1 ? fileNames[1] : (fileNames[0] || ""));
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
      const msg = err instanceof Error ? err.message : "Audit analysis failed. Please verify documents are uploaded.";
      setAuditError(msg);
    } finally {
      setIsAuditingDiff(false);
    }
  };

  // Upload a second document to compare directly from the Contradiction Matrix
  const handleUploadSecondFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files || e.target.files.length === 0 || !sessionId) return;
    const file = e.target.files[0];

    setIsAuditingDiff(true);
    setAuditError(null);

    try {
      // 1. Create local blob URL immediately for zero-lag rendering
      setLocalFileUrls({ [file.name]: URL.createObjectURL(file) });

      // 2. Upload to backend appending to existing session
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

      // 3. Immediately run the comparative forensic audit
      const report = await auditContradictions(result.session_id, fileNames[0] || file.name, file.name);
      setActiveDiffReport(report);
    } catch (err: unknown) {
      console.error("Upload & audit error:", err);
      const msg = err instanceof Error ? err.message : "Failed to upload and audit comparison document.";
      setAuditError(msg);
    } finally {
      setIsAuditingDiff(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  // Instant demo comparison pair loader
  const handleLoadDemoPair = async () => {
    setIsAuditingDiff(true);
    setAuditError(null);

    const demoFiles: UploadedFile[] = [
      {
        name: "SaaS_Agreement_2024_v1.pdf",
        size: 2150000,
        type: "application/pdf",
        pages: 3,
      },
      {
        name: "SaaS_Agreement_2025_Amended.pdf",
        size: 2280000,
        type: "application/pdf",
        pages: 3,
      },
      {
        name: "Veridocs_Technical_Architecture.pdf",
        size: 2450000,
        type: "application/pdf",
        pages: 3,
      },
    ];

    setSession("demo-session", demoFiles);
    setDocA("SaaS_Agreement_2024_v1.pdf");
    setDocB("SaaS_Agreement_2025_Amended.pdf");

    try {
      const report = await auditContradictions("demo-session", "SaaS_Agreement_2024_v1.pdf", "SaaS_Agreement_2025_Amended.pdf");
      setActiveDiffReport(report);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load demo audit.";
      setAuditError(msg);
    } finally {
      setIsAuditingDiff(false);
    }
  };

  // Inspect conflict directly in the PDF Viewer Canvas with visual bounding box
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
      label: `⚖️ Conflict: ${topic}`,
      severity,
    });
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
    <div className="h-full flex flex-col bg-midnight-900 overflow-hidden select-none">
      {/* Hidden file input for adding document B */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleUploadSecondFile}
        accept=".pdf,.docx,.txt"
        className="hidden"
      />

      {/* Header Bar */}
      <div className="p-4 border-b border-white/5 bg-midnight-950/60 backdrop-blur-md shrink-0">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
              <Scale className="w-4 h-4 text-rose-400" />
            </div>
            <div>
              <h2 className="text-xs font-bold text-text-primary tracking-tight flex items-center gap-2">
                Forensic Contradiction Matrix
                <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-semibold bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  DIFF ENGINE
                </span>
              </h2>
              <p className="text-[10px] text-text-muted">
                Cross-document covenant discrepancy & numerical mismatch auditor
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {fileNames.length === 1 && (
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={isAuditingDiff}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-text-secondary hover:text-white font-semibold text-xs transition-all"
                title="Upload Document B to perform cross-document comparison"
              >
                <Plus className="w-3.5 h-3.5 text-accent-primary" />
                Add 2nd Document
              </button>
            )}

            <button
              onClick={handleRunAudit}
              disabled={isAuditingDiff}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-gradient-to-r from-rose-500 to-amber-500 hover:from-rose-600 hover:to-amber-600 text-white font-semibold text-xs shadow-lg shadow-rose-500/10 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isAuditingDiff ? "animate-spin" : ""}`} />
              {isAuditingDiff
                ? "Auditing..."
                : fileNames.length >= 2
                ? "Run Forensic Audit"
                : "Audit Single Doc"}
            </button>
          </div>
        </div>

        {/* Document Selectors */}
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="bg-white/[0.02] border border-white/5 rounded-lg p-2">
            <span className="text-[10px] uppercase font-bold text-text-muted block mb-1">
              Document A (Baseline)
            </span>
            <select
              value={docA}
              onChange={(e) => setDocA(e.target.value)}
              className="w-full bg-midnight-950 border border-white/10 rounded px-2 py-1 text-xs text-text-secondary focus:outline-none focus:border-accent-primary truncate"
            >
              {fileNames.map((fn) => (
                <option key={`a-${fn}`} value={fn}>
                  {fn}
                </option>
              ))}
            </select>
          </div>

          <div className="bg-white/[0.02] border border-white/5 rounded-lg p-2">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] uppercase font-bold text-text-muted">
                Document B (Amended / Comparison)
              </span>
              {fileNames.length === 1 && (
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="text-[10px] text-accent-primary hover:underline font-semibold flex items-center gap-0.5"
                >
                  <Plus className="w-2.5 h-2.5" />
                  Upload
                </button>
              )}
            </div>
            {fileNames.length >= 2 ? (
              <select
                value={docB}
                onChange={(e) => setDocB(e.target.value)}
                className="w-full bg-midnight-950 border border-white/10 rounded px-2 py-1 text-xs text-text-secondary focus:outline-none focus:border-accent-primary truncate"
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
                className="w-full bg-midnight-950 border border-dashed border-accent-primary/40 rounded px-2 py-1 text-xs text-accent-primary hover:bg-accent-primary/5 cursor-pointer flex items-center justify-between"
              >
                <span className="truncate">Click to select Doc B...</span>
                <Upload className="w-3 h-3 shrink-0" />
              </div>
            )}
          </div>
        </div>

        {auditError && (
          <div className="mt-2 p-2 rounded-lg bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center gap-2">
            <AlertOctagon className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{auditError}</span>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* If no report has been run yet */}
        {!activeDiffReport && !isAuditingDiff && (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 border border-dashed border-white/10 rounded-2xl bg-white/[0.01]">
            <div className="w-12 h-12 rounded-2xl bg-rose-500/10 border border-rose-500/20 flex items-center justify-center mb-3">
              <Scale className="w-6 h-6 text-rose-400" />
            </div>
            <h3 className="text-sm font-bold text-text-primary mb-1">
              {fileNames.length >= 2
                ? "Multi-Document Forensic Diff Ready"
                : "1 Document Loaded — Compare or Self-Audit"}
            </h3>
            <p className="text-xs text-text-muted max-w-sm mb-5 leading-relaxed">
              {fileNames.length >= 2
                ? `Compare ${docA || fileNames[0]} against ${docB || fileNames[1]} to detect contradictory terms, altered numerical values, and risk breaches.`
                : `Upload a second file to compare cross-document revisions, or audit ${fileNames[0] || "your document"} for internal consistency and timeline discrepancies.`}
            </p>

            {fileNames.length >= 2 ? (
              <div className="flex flex-col gap-2 w-full max-w-xs">
                <button
                  onClick={handleRunAudit}
                  className="w-full px-4 py-2.5 rounded-xl bg-gradient-to-r from-rose-500 to-amber-500 hover:opacity-95 text-white font-bold text-xs shadow-lg transition-all"
                >
                  Execute Comparative Audit
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3 w-full max-w-sm">
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full py-2.5 px-4 rounded-xl bg-gradient-to-r from-accent-primary to-accent-secondary hover:opacity-95 text-midnight-950 font-bold text-xs shadow-lg flex items-center justify-center gap-2 transition-all cursor-pointer"
                >
                  <Upload className="w-4 h-4" />
                  Upload 2nd Document to Compare
                </button>

                <div className="flex items-center gap-2 w-full my-1">
                  <div className="h-px bg-white/10 flex-1" />
                  <span className="text-[10px] text-text-muted uppercase font-bold tracking-wider">or instant options</span>
                  <div className="h-px bg-white/10 flex-1" />
                </div>

                <div className="grid grid-cols-2 gap-2 w-full">
                  <button
                    onClick={handleRunAudit}
                    className="py-2 px-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 text-text-secondary hover:text-white text-[11px] font-semibold transition-all"
                  >
                    🔍 Audit Self-Consistency
                  </button>

                  <button
                    onClick={handleLoadDemoPair}
                    className="py-2 px-3 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 text-rose-300 text-[11px] font-semibold flex items-center justify-center gap-1 transition-all"
                  >
                    <Sparkles className="w-3.5 h-3.5" />
                    Try Demo Contract Pair
                  </button>
                </div>
              </div>
            )}
          </div>
        )}


        {/* Loading Skeleton */}
        {isAuditingDiff && (
          <div className="space-y-4 py-8">
            <div className="p-4 rounded-xl bg-midnight-950 border border-white/10 flex flex-col items-center justify-center text-center">
              <div className="w-10 h-10 border-2 border-rose-500/20 border-t-rose-500 rounded-full animate-spin mb-3" />
              <p className="text-xs font-semibold text-text-primary">
                Scanning Cross-Document Clauses & Numbers...
              </p>
              <p className="text-[11px] text-text-muted mt-1">
                Comparing semantic vectors & extracting numerical entities
              </p>
            </div>
          </div>
        )}

        {/* Active Audit Report */}
        {activeDiffReport && !isAuditingDiff && (
          <div className="space-y-4">
            {/* Executive Risk Scorecard */}
            <div className="p-4 rounded-xl bg-midnight-950 border border-white/10 shadow-xl backdrop-blur-md">
              <div className="flex items-center justify-between pb-3 border-b border-white/5">
                <div className="flex items-center gap-2">
                  <div
                    className={`w-2.5 h-2.5 rounded-full ${
                      activeDiffReport.critical_count > 0
                        ? "bg-rose-500 animate-ping"
                        : "bg-emerald-400"
                    }`}
                  />
                  <span className="text-xs font-bold text-text-primary uppercase tracking-wider">
                    Executive Audit Assessment
                  </span>
                </div>
                <span className="text-xs font-mono font-bold text-amber-300 bg-amber-400/10 border border-amber-400/20 px-2.5 py-0.5 rounded-full">
                  {Math.round(activeDiffReport.alignment_score * 100)}% Alignment
                </span>
              </div>

              <p className="text-xs text-text-secondary mt-2.5 leading-relaxed font-medium">
                {activeDiffReport.summary}
              </p>

              <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-white/5 text-center">
                <div className="bg-rose-500/10 border border-rose-500/20 rounded-lg p-2">
                  <span className="text-base font-extrabold text-rose-400 block font-mono">
                    {activeDiffReport.critical_count}
                  </span>
                  <span className="text-[10px] text-rose-300 font-semibold uppercase">
                    Critical Breaches
                  </span>
                </div>

                <div className="bg-amber-500/10 border border-amber-500/20 rounded-lg p-2">
                  <span className="text-base font-extrabold text-amber-400 block font-mono">
                    {activeDiffReport.warning_count}
                  </span>
                  <span className="text-[10px] text-amber-300 font-semibold uppercase">
                    Modifications
                  </span>
                </div>

                <div className="bg-emerald-500/10 border border-emerald-500/20 rounded-lg p-2">
                  <span className="text-base font-extrabold text-emerald-400 block font-mono">
                    {Math.max(0, 10 - activeDiffReport.conflicts.length)}
                  </span>
                  <span className="text-[10px] text-emerald-300 font-semibold uppercase">
                    Aligned Clauses
                  </span>
                </div>
              </div>
            </div>

            {/* Filter Pills & Search */}
            <div className="flex items-center gap-2 justify-between">
              <div className="flex items-center gap-1.5 text-xs">
                <button
                  onClick={() => setFilterSeverity("all")}
                  className={`px-2.5 py-1 rounded-lg font-medium transition-all ${
                    filterSeverity === "all"
                      ? "bg-white/15 text-white"
                      : "bg-white/5 text-text-muted hover:text-text-secondary"
                  }`}
                >
                  All ({conflicts.length})
                </button>
                <button
                  onClick={() => setFilterSeverity("critical")}
                  className={`px-2.5 py-1 rounded-lg font-medium transition-all ${
                    filterSeverity === "critical"
                      ? "bg-rose-500/20 text-rose-300 border border-rose-500/30"
                      : "bg-white/5 text-text-muted hover:text-text-secondary"
                  }`}
                >
                  Critical ({activeDiffReport.critical_count})
                </button>
                <button
                  onClick={() => setFilterSeverity("warning")}
                  className={`px-2.5 py-1 rounded-lg font-medium transition-all ${
                    filterSeverity === "warning"
                      ? "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                      : "bg-white/5 text-text-muted hover:text-text-secondary"
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
                  className="bg-midnight-950 border border-white/10 rounded-lg pl-7 pr-2.5 py-1 text-xs text-text-secondary placeholder:text-text-muted focus:outline-none focus:border-accent-primary w-36 sm:w-44"
                />
                <Search className="w-3 h-3 text-text-muted absolute left-2 top-2" />
              </div>
            </div>

            {/* Conflict Cards */}
            <div className="space-y-3">
              {filteredConflicts.map((c) => {
                const isCritical = c.severity === "critical";

                return (
                  <motion.div
                    key={c.id}
                    layout
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    className={`rounded-xl border p-4 bg-midnight-950/80 backdrop-blur-sm transition-all ${
                      isCritical
                        ? "border-rose-500/30 shadow-[0_0_20px_rgba(244,63,94,0.06)]"
                        : "border-amber-500/30 shadow-[0_0_20px_rgba(245,158,11,0.06)]"
                    }`}
                  >
                    {/* Card Header */}
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        {isCritical ? (
                          <AlertOctagon className="w-4 h-4 text-rose-400 shrink-0" />
                        ) : (
                          <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0" />
                        )}
                        <h4 className="text-xs font-bold text-text-primary tracking-tight">
                          {c.topic}
                        </h4>
                      </div>

                      <div className="flex items-center gap-1.5">
                        <span
                          className={`text-[9px] uppercase font-mono font-bold px-2 py-0.5 rounded border ${
                            isCritical
                              ? "bg-rose-500/15 border-rose-500/30 text-rose-300"
                              : "bg-amber-500/15 border-amber-500/30 text-amber-300"
                          }`}
                        >
                          {c.severity}
                        </span>
                        <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-text-muted border border-white/10">
                          {c.conflict_type.replace("_", " ")}
                        </span>
                      </div>
                    </div>

                    {/* Discrepancy & Risk Explanation */}
                    <p className="text-xs text-text-secondary leading-relaxed mb-2 font-medium">
                      {c.explanation}
                    </p>

                    <div className="p-2 rounded-lg bg-white/[0.02] border border-white/5 mb-3 text-[11px] text-text-muted flex items-start gap-1.5">
                      <ShieldAlert className="w-3.5 h-3.5 text-rose-400/80 shrink-0 mt-0.5" />
                      <span>
                        <strong className="text-text-secondary">Risk Analysis:</strong> {c.risk_analysis}
                      </span>
                    </div>

                    {/* Side-by-Side Excerpts */}
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                      {/* Doc A Snippet */}
                      <div className="p-2.5 rounded-lg bg-midnight-900 border border-white/5 flex flex-col justify-between group hover:border-accent-primary/40 transition-all">
                        <div>
                          <div className="flex items-center justify-between text-[10px] text-text-muted font-mono mb-1.5">
                            <span className="truncate max-w-[130px] font-semibold text-text-secondary">
                              Doc A: {c.doc_a.filename}
                            </span>
                            <span className="px-1.5 py-0.5 rounded bg-white/10 text-white font-bold">
                              Page {c.doc_a.page}
                            </span>
                          </div>
                          <p className="text-[11px] text-text-secondary italic line-clamp-3">
                            &quot;{c.doc_a.snippet}&quot;
                          </p>
                        </div>

                        <button
                          onClick={() =>
                            handleInspectSnippet(
                              c.doc_a.filename,
                              c.doc_a.page,
                              c.doc_a.snippet,
                              c.topic,
                              c.severity
                            )
                          }
                          className="mt-2.5 pt-2 border-t border-white/5 w-full flex items-center justify-center gap-1 text-[10px] font-semibold text-accent-primary hover:text-white transition-colors"
                        >
                          <Search className="w-3 h-3" />
                          Inspect in Doc A Canvas
                        </button>
                      </div>

                      {/* Doc B Snippet */}
                      <div className="p-2.5 rounded-lg bg-midnight-900 border border-white/5 flex flex-col justify-between group hover:border-rose-400/40 transition-all">
                        <div>
                          <div className="flex items-center justify-between text-[10px] text-text-muted font-mono mb-1.5">
                            <span className="truncate max-w-[130px] font-semibold text-rose-300">
                              Doc B: {c.doc_b.filename}
                            </span>
                            <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/30 font-bold">
                              Page {c.doc_b.page}
                            </span>
                          </div>
                          <p className="text-[11px] text-rose-200/90 italic line-clamp-3">
                            &quot;{c.doc_b.snippet}&quot;
                          </p>
                        </div>

                        <button
                          onClick={() =>
                            handleInspectSnippet(
                              c.doc_b.filename,
                              c.doc_b.page,
                              c.doc_b.snippet,
                              c.topic,
                              c.severity
                            )
                          }
                          className="mt-2.5 pt-2 border-t border-white/5 w-full flex items-center justify-center gap-1 text-[10px] font-semibold text-rose-400 hover:text-white transition-colors"
                        >
                          <Search className="w-3 h-3" />
                          Inspect in Doc B Canvas
                        </button>
                      </div>
                    </div>
                  </motion.div>
                );
              })}

              {filteredConflicts.length === 0 && (
                <div className="text-center py-8 text-xs text-text-muted">
                  No conflicts matched your search filter.
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
