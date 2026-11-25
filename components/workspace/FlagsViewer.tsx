"use client";

import React, { useEffect, useState } from "react";
import { useAppStore } from "../../lib/store";
import { fetchDocumentFlags, DocumentFlagsResult, AnomalyFlag } from "../../lib/api";

export default function FlagsViewer({ documentId }: { documentId: string }) {
  const { documentFlags, setDocumentFlags, setCurrentPage } = useAppStore();
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const flagsData: DocumentFlagsResult | undefined = documentFlags[documentId];

  useEffect(() => {
    if (!documentId) return;
    if (flagsData) return;

    let active = true;
    setLoading(true);
    fetchDocumentFlags(documentId)
      .then((data) => {
        if (active) {
          setDocumentFlags(documentId, data);
        }
      })
      .catch((err) => {
        if (active) setError(err.message || "Failed to load anomaly flags");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [documentId, flagsData, setDocumentFlags]);

  const flags: AnomalyFlag[] = flagsData?.flags || [];
  const severityCounts = flagsData?.severity_counts || { high: 0, medium: 0, low: 0 };

  return (
    <div className="flex flex-col h-full bg-slate-900 text-slate-100 overflow-hidden">
      {/* Disclaimer Banner */}
      <div className="p-3 bg-amber-950/70 border-b border-amber-800/80 text-amber-200 text-xs flex items-start gap-2 shadow-sm">
        <span className="text-base leading-none">⚠️</span>
        <div className="leading-snug">
          <p className="font-semibold text-amber-100">Reviewer Advisory:</p>
          <p className="text-[11px] text-amber-300/90">
            {flagsData?.disclaimer ||
              "These are heuristic signals for human review, not automated fraud accusations."}
          </p>
        </div>
      </div>

      {/* Severity Counters Header */}
      <div className="p-4 border-b border-slate-800 bg-slate-850 flex items-center justify-between text-xs">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-slate-200">Audit Flags:</span>
          <span className="px-2 py-0.5 rounded-full bg-slate-700 text-slate-300 font-medium">
            {flags.length} Total
          </span>
        </div>

        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1 font-semibold text-rose-400">
            🔴 {severityCounts.high} High
          </span>
          <span className="flex items-center gap-1 font-semibold text-amber-400">
            🟡 {severityCounts.medium} Medium
          </span>
          <span className="flex items-center gap-1 font-semibold text-blue-400">
            🟢 {severityCounts.low} Low
          </span>
        </div>
      </div>

      {/* Flags List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {loading && (
          <div className="text-center py-10 text-slate-400 text-xs animate-pulse">
            Running independent anomaly checkers...
          </div>
        )}

        {error && (
          <div className="text-center py-10 text-rose-400 text-xs">
            {error}
          </div>
        )}

        {!loading && !error && flags.length === 0 && (
          <div className="text-center py-12 text-slate-500 text-xs space-y-1">
            <span className="text-2xl block">✅</span>
            <p className="font-medium text-slate-300">No anomaly flags detected.</p>
            <p className="text-[11px]">All mathematical checks, date sequences, and threshold rules passed cleanly.</p>
          </div>
        )}

        {flags.map((flag) => {
          const isHigh = flag.severity === "high";
          const isMedium = flag.severity === "medium";

          return (
            <div
              key={flag.id}
              className={`p-3.5 rounded-xl border transition-all ${
                isHigh
                  ? "bg-rose-950/30 border-rose-900/60 shadow-sm"
                  : isMedium
                  ? "bg-amber-950/20 border-amber-900/60"
                  : "bg-slate-800/60 border-slate-700/60"
              }`}
            >
              <div className="flex items-center justify-between mb-1.5">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase tracking-wider ${
                      isHigh
                        ? "bg-rose-900 text-rose-200 border border-rose-700"
                        : isMedium
                        ? "bg-amber-900 text-amber-200 border border-amber-700"
                        : "bg-blue-900 text-blue-200"
                    }`}
                  >
                    {flag.severity}
                  </span>
                  <span className="text-xs font-mono font-medium text-slate-300">
                    {flag.rule_id}
                  </span>
                </div>
                <span className="text-[10px] text-slate-400">
                  Confidence: {Math.round(flag.confidence * 100)}%
                </span>
              </div>

              <p className="text-xs text-slate-200 font-medium leading-relaxed mb-2.5">
                {flag.message}
              </p>

              {/* Evidence Quotes */}
              {flag.evidence && flag.evidence.length > 0 && (
                <div className="space-y-1.5 pt-2 border-t border-slate-800/80">
                  <span className="text-[10px] font-semibold text-slate-400 block uppercase tracking-wider">
                    Evidence Signals:
                  </span>
                  {flag.evidence.map((ev, eIdx) => (
                    <div
                      key={`ev-${eIdx}`}
                      onClick={() => setCurrentPage(ev.page)}
                      className="group cursor-pointer p-2 rounded-lg bg-slate-900/80 border border-slate-800 hover:border-blue-600 transition-colors flex items-start justify-between gap-2 text-[11px]"
                    >
                      <div className="flex-1 space-y-0.5">
                        <p className="text-slate-300 font-mono italic">
                          &ldquo;{ev.quote}&rdquo;
                        </p>
                        {ev.details && (
                          <p className="text-[10px] text-slate-400 font-sans">
                            {ev.details}
                          </p>
                        )}
                      </div>
                      <span className="shrink-0 px-1.5 py-0.5 rounded bg-blue-950 text-blue-300 text-[10px] font-semibold group-hover:bg-blue-600 group-hover:text-white transition-colors">
                        Page {ev.page} ↗
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
