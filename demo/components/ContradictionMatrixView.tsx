"use client";

import React from "react";
import { GitCompare, AlertTriangle, ArrowRight, Eye, CheckCircle2 } from "lucide-react";
import { ContradictionItem, DemoScenario } from "../lib/demoData";

interface ContradictionMatrixViewProps {
  scenario: DemoScenario;
  onInspectClause: (doc: "docA" | "docB", clauseId: string, page: number) => void;
}

export function ContradictionMatrixView({
  scenario,
  onInspectClause,
}: ContradictionMatrixViewProps) {
  const contradictions = scenario.contradictions || [];

  return (
    <div className="flex flex-col h-full rounded-2xl border border-white/10 bg-midnight-900/60 overflow-hidden shadow-xl">
      {/* Header */}
      <div className="px-6 py-4 border-b border-white/10 bg-white/[0.02] flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <GitCompare className="w-4 h-4 text-rose-400" />
            <h3 className="text-sm font-bold text-white">Forensic Contradiction Matrix</h3>
            <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-rose-500/20 text-rose-300 border border-rose-500/30">
              {contradictions.length} Critical Discrepancies
            </span>
          </div>
          <p className="text-xs text-text-muted mt-0.5">
            Cross-document diffing comparing <strong className="text-white">{scenario.docA.name}</strong> vs <strong className="text-white">{scenario.docB?.name}</strong>
          </p>
        </div>
      </div>

      {/* Discrepancy Cards List */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4">
        {contradictions.map((item) => {
          const isHigh = item.severity === "high";

          return (
            <div
              key={item.id}
              className="p-5 rounded-xl border border-white/10 bg-white/[0.02] hover:bg-white/[0.04] transition-all space-y-4 shadow-md"
            >
              {/* Card Title & Category Tag */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className={`p-1.5 rounded-lg ${
                      isHigh ? "bg-rose-500/20 text-rose-400" : "bg-amber-500/20 text-amber-400"
                    }`}
                  >
                    <AlertTriangle className="w-4 h-4" />
                  </span>
                  <div>
                    <h4 className="text-sm font-bold text-white">{item.title}</h4>
                    <span className="text-[10px] font-medium text-text-muted uppercase tracking-wider">
                      Category: {item.category}
                    </span>
                  </div>
                </div>

                <span
                  className={`px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider rounded-full border ${
                    isHigh
                      ? "bg-rose-500/10 text-rose-400 border-rose-500/20"
                      : "bg-amber-500/10 text-amber-400 border-amber-500/20"
                  }`}
                >
                  {item.severity} Severity
                </span>
              </div>

              {/* Side-by-side Clause Comparison */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 pt-2">
                {/* Doc A */}
                <div className="p-3 rounded-lg border border-white/5 bg-black/40 space-y-2">
                  <div className="flex items-center justify-between text-[11px] font-mono text-text-muted">
                    <span className="font-semibold text-text-secondary">{scenario.docA.name}</span>
                    <button
                      onClick={() => onInspectClause("docA", item.docAClauseId, 1)}
                      className="flex items-center gap-1 text-amber-400 hover:text-amber-300 font-sans text-[10px] underline"
                    >
                      <Eye className="w-3 h-3" />
                      <span>Inspect in Doc A</span>
                    </button>
                  </div>
                  <p className="text-xs text-rose-300/90 leading-relaxed font-serif bg-rose-500/5 p-2 rounded border border-rose-500/10">
                    &quot;{item.docAText}&quot;
                  </p>
                </div>

                {/* Doc B */}
                <div className="p-3 rounded-lg border border-white/5 bg-black/40 space-y-2">
                  <div className="flex items-center justify-between text-[11px] font-mono text-text-muted">
                    <span className="font-semibold text-text-secondary">{scenario.docB?.name}</span>
                    <button
                      onClick={() => onInspectClause("docB", item.docBClauseId, 1)}
                      className="flex items-center gap-1 text-emerald-400 hover:text-emerald-300 font-sans text-[10px] underline"
                    >
                      <Eye className="w-3 h-3" />
                      <span>Inspect in Doc B</span>
                    </button>
                  </div>
                  <p className="text-xs text-emerald-300/90 leading-relaxed font-serif bg-emerald-500/5 p-2 rounded border border-emerald-500/10">
                    &quot;{item.docBText}&quot;
                  </p>
                </div>
              </div>

              {/* Forensic Diff Summary */}
              <div className="flex items-center gap-2 p-2.5 rounded-lg bg-amber-500/10 border border-amber-500/20 text-xs text-amber-200">
                <ArrowRight className="w-4 h-4 text-amber-400 flex-shrink-0" />
                <span>
                  <strong className="text-amber-400">Forensic Diff:</strong> {item.diffSummary}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
