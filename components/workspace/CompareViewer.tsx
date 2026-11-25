"use client";

import React, { useState } from "react";
import { useAppStore } from "../../lib/store";
import {
  createComparison,
  fetchComparison,
  exportComparisonMarkdown,
  ComparisonData,
  AlignedClause,
} from "../../lib/api";

export default function CompareViewer() {
  const { files, activeComparison, setActiveComparison, setCurrentPage } = useAppStore();

  const [docAId, setDocAId] = useState<string>("");
  const [docBId, setDocBId] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [filterRisk, setFilterRisk] = useState<"all" | "high" | "medium" | "low">("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [exportNotice, setExportNotice] = useState<string | null>(null);

  // Available documents with document IDs
  const availableDocs = files.filter((f) => f.documentId && f.status === "ready");

  const handleStartComparison = async () => {
    if (!docAId || !docBId) {
      setError("Please select both Base Document (A) and Comparison Document (B).");
      return;
    }
    if (docAId === docBId) {
      setError("Please select two distinct documents for comparison.");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const res = await createComparison(docAId, docBId);
      // Poll until ready
      let comp: ComparisonData | null = null;
      for (let i = 0; i < 20; i++) {
        await new Promise((r) => setTimeout(r, 1000));
        comp = await fetchComparison(res.id);
        if (comp.status === "ready" || comp.status === "failed") {
          break;
        }
      }

      if (comp && comp.status === "ready") {
        setActiveComparison(comp);
      } else if (comp && comp.status === "failed") {
        setError(comp.error || "Comparison failed during processing.");
      } else {
        setError("Comparison timed out. Please try again.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to initiate comparison.");
    } finally {
      setLoading(false);
    }
  };

  const handleExportMarkdown = async () => {
    if (!activeComparison) return;
    try {
      const data = await exportComparisonMarkdown(activeComparison.id);
      const blob = new Blob([data.markdown], { type: "text/markdown" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename || "contract_comparison.md";
      a.click();
      URL.revokeObjectURL(url);
      setExportNotice("Exported Markdown successfully!");
      setTimeout(() => setExportNotice(null), 3000);
    } catch (err: any) {
      setError("Failed to export comparison markdown: " + err.message);
    }
  };

  const alignedClauses: AlignedClause[] = activeComparison?.data?.aligned_clauses || [];
  const stats = activeComparison?.data?.stats;

  const filteredClauses = alignedClauses.filter((clause) => {
    if (filterRisk !== "all" && clause.analysis?.risk !== filterRisk) {
      return false;
    }
    if (filterStatus !== "all" && clause.status !== filterStatus) {
      return false;
    }
    return true;
  });

  return (
    <div className="flex flex-col h-full bg-slate-900 text-slate-100 overflow-hidden">
      {/* Header and Picker Section */}
      <div className="p-4 border-b border-slate-800 bg-slate-900/90 backdrop-blur sticky top-0 z-10 space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-white flex items-center gap-2">
              <span>⚖️</span> Contract Comparison & Redline
            </h2>
            <p className="text-xs text-slate-400">
              Hungarian clause alignment, word-level redline diff, and legal risk classification
            </p>
          </div>
          {activeComparison?.status === "ready" && (
            <button
              onClick={handleExportMarkdown}
              className="px-3 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg transition-colors flex items-center gap-1.5 shadow"
            >
              <span>📥</span> Export Markdown
            </button>
          )}
        </div>

        {exportNotice && (
          <div className="px-3 py-1 text-xs bg-emerald-950 text-emerald-300 border border-emerald-800 rounded">
            {exportNotice}
          </div>
        )}

        {/* Document Selection Pickers */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 bg-slate-800/60 p-3 rounded-lg border border-slate-700/60">
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Base Document (Version A):
            </label>
            <select
              value={docAId}
              onChange={(e) => setDocAId(e.target.value)}
              className="w-full text-xs bg-slate-900 border border-slate-700 rounded-md p-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">Select Document A...</option>
              {availableDocs.map((doc) => (
                <option key={`a-${doc.documentId}`} value={doc.documentId}>
                  {doc.name}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Comparison Document (Version B):
            </label>
            <select
              value={docBId}
              onChange={(e) => setDocBId(e.target.value)}
              className="w-full text-xs bg-slate-900 border border-slate-700 rounded-md p-2 text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">Select Document B...</option>
              {availableDocs.map((doc) => (
                <option key={`b-${doc.documentId}`} value={doc.documentId}>
                  {doc.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex items-center justify-between">
          <button
            onClick={handleStartComparison}
            disabled={loading || !docAId || !docBId}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white transition-all shadow-sm"
          >
            {loading ? "Aligning Clauses..." : "Compare Contracts"}
          </button>

          {error && <span className="text-xs text-rose-400 font-medium">{error}</span>}
        </div>

        {/* Stats and Filter Chips */}
        {stats && (
          <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-slate-800 text-xs">
            <span className="text-slate-400 font-medium">Filters:</span>
            <button
              onClick={() => setFilterRisk("all")}
              className={`px-2 py-0.5 rounded-full ${
                filterRisk === "all" ? "bg-slate-700 text-white" : "bg-slate-800 text-slate-400"
              }`}
            >
              All Risks ({stats.total_aligned})
            </button>
            <button
              onClick={() => setFilterRisk("high")}
              className={`px-2 py-0.5 rounded-full ${
                filterRisk === "high" ? "bg-rose-900 text-rose-200 border border-rose-700" : "bg-slate-800 text-rose-400"
              }`}
            >
              🔴 High Risk ({stats.risk_counts?.high || 0})
            </button>
            <button
              onClick={() => setFilterRisk("medium")}
              className={`px-2 py-0.5 rounded-full ${
                filterRisk === "medium" ? "bg-amber-900 text-amber-200 border border-amber-700" : "bg-slate-800 text-amber-400"
              }`}
            >
              🟡 Medium Risk ({stats.risk_counts?.medium || 0})
            </button>
            <button
              onClick={() => setFilterStatus(filterStatus === "modified" ? "all" : "modified")}
              className={`px-2 py-0.5 rounded-full ${
                filterStatus === "modified" ? "bg-blue-900 text-blue-200" : "bg-slate-800 text-slate-400"
              }`}
            >
              Modified ({stats.status_counts?.modified || 0})
            </button>
            <button
              onClick={() => setFilterStatus(filterStatus === "added" ? "all" : "added")}
              className={`px-2 py-0.5 rounded-full ${
                filterStatus === "added" ? "bg-emerald-900 text-emerald-200" : "bg-slate-800 text-slate-400"
              }`}
            >
              Added ({stats.status_counts?.added || 0})
            </button>
          </div>
        )}
      </div>

      {/* Aligned Clauses View */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {filteredClauses.length === 0 ? (
          <div className="text-center py-12 text-slate-500 text-xs">
            {activeComparison
              ? "No clauses match the active filters."
              : "Select two documents above and click 'Compare Contracts' to inspect differences."}
          </div>
        ) : (
          filteredClauses.map((item, idx) => {
            const ca = item.clause_a;
            const cb = item.clause_b;
            const analysis = item.analysis;
            const status = item.status;

            return (
              <div
                key={`aligned-${idx}`}
                className="bg-slate-800/80 border border-slate-700/80 rounded-xl overflow-hidden shadow"
              >
                {/* Clause Header Bar */}
                <div className="flex items-center justify-between px-4 py-2.5 bg-slate-850 border-b border-slate-750 text-xs">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-slate-300">
                      Clause {idx + 1}:
                    </span>
                    <span className="text-slate-100 font-medium">
                      {(cb?.heading || ca?.heading) || "Unlabeled Section"}
                    </span>
                    <span
                      className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase tracking-wider ${
                        status === "unchanged"
                          ? "bg-slate-700 text-slate-300"
                          : status === "modified"
                          ? "bg-amber-950 text-amber-300 border border-amber-800"
                          : status === "added"
                          ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                          : "bg-rose-950 text-rose-300 border border-rose-800"
                      }`}
                    >
                      {status}
                    </span>
                  </div>

                  {analysis && (
                    <div className="flex items-center gap-2">
                      <span className="text-[11px] text-slate-400 uppercase tracking-wider">
                        {analysis.change_type}
                      </span>
                      <span
                        className={`px-2 py-0.5 text-[10px] font-semibold rounded ${
                          analysis.risk === "high"
                            ? "bg-rose-900/80 text-rose-200 border border-rose-700"
                            : analysis.risk === "medium"
                            ? "bg-amber-900/80 text-amber-200 border border-amber-700"
                            : "bg-emerald-900/80 text-emerald-200"
                        }`}
                      >
                        {analysis.risk.toUpperCase()} RISK
                      </span>
                    </div>
                  )}
                </div>

                {/* Analysis / Summary Box */}
                {analysis && (
                  <div className="px-4 py-2 bg-slate-900/60 border-b border-slate-800 text-xs space-y-1">
                    <p className="text-slate-200 font-medium">
                      <span className="text-blue-400 font-semibold">Summary: </span>
                      {analysis.summary}
                    </p>
                    {analysis.risk_reason && (
                      <p className="text-slate-400 text-[11px]">
                        <span className="text-amber-400 font-medium">Risk Factor: </span>
                        {analysis.risk_reason}
                      </p>
                    )}
                  </div>
                )}

                {/* Side-by-side or Redline Panel */}
                <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-mono">
                  {/* Version A */}
                  <div className="bg-slate-900/90 p-3 rounded-lg border border-slate-800 space-y-2">
                    <div className="flex items-center justify-between text-slate-400 text-[11px] font-sans pb-1 border-b border-slate-800">
                      <span>Doc A (Base)</span>
                      {ca && (
                        <button
                          onClick={() => setCurrentPage(ca.page_start)}
                          className="text-blue-400 hover:underline"
                        >
                          Jump to p.{ca.page_start}
                        </button>
                      )}
                    </div>
                    <div className="text-slate-300 whitespace-pre-wrap leading-relaxed text-[11px]">
                      {ca ? ca.text : <span className="text-slate-600 italic">Not present in Doc A (Added)</span>}
                    </div>
                  </div>

                  {/* Version B */}
                  <div className="bg-slate-900/90 p-3 rounded-lg border border-slate-800 space-y-2">
                    <div className="flex items-center justify-between text-slate-400 text-[11px] font-sans pb-1 border-b border-slate-800">
                      <span>Doc B (Modified)</span>
                      {cb && (
                        <button
                          onClick={() => setCurrentPage(cb.page_start)}
                          className="text-blue-400 hover:underline"
                        >
                          Jump to p.{cb.page_start}
                        </button>
                      )}
                    </div>
                    <div className="text-slate-300 whitespace-pre-wrap leading-relaxed text-[11px]">
                      {cb ? cb.text : <span className="text-slate-600 italic">Deleted from Doc B (Removed)</span>}
                    </div>
                  </div>
                </div>

                {/* Redline Highlighting */}
                {status === "modified" && item.diff_tokens && (
                  <div className="px-4 pb-4 pt-1">
                    <div className="bg-slate-950 p-3 rounded-lg border border-slate-800/80 text-[11px] font-mono leading-relaxed">
                      <span className="text-[10px] font-sans font-semibold text-slate-400 block mb-1">
                        REDLINE VIEW:
                      </span>
                      {item.diff_tokens.map((tok, tIdx) => {
                        if (tok.type === "insert") {
                          return (
                            <span
                              key={`t-${tIdx}`}
                              className="bg-emerald-950 text-emerald-300 font-semibold px-1 py-0.5 rounded mr-1"
                            >
                              {tok.text}{" "}
                            </span>
                          );
                        }
                        if (tok.type === "delete") {
                          return (
                            <span
                              key={`t-${tIdx}`}
                              className="bg-rose-950 text-rose-400 line-through px-1 py-0.5 rounded mr-1"
                            >
                              {tok.text}{" "}
                            </span>
                          );
                        }
                        return (
                          <span key={`t-${tIdx}`} className="text-slate-300 mr-1">
                            {tok.text}{" "}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
