"use client";

import React, { useRef, useEffect } from "react";
import { FileText, ZoomIn, ZoomOut, CheckCircle2, AlertTriangle, Layers } from "lucide-react";
import { DemoScenario, DocumentClause } from "../lib/demoData";

interface DocumentCanvasProps {
  scenario: DemoScenario;
  activeDoc: "docA" | "docB";
  onSelectDoc: (doc: "docA" | "docB") => void;
  activeClauseId: string | null;
  onClauseClick: (clauseId: string) => void;
  activePage: number;
  onPageChange: (page: number) => void;
  activeHighlightText?: string | null;
}

export function DocumentCanvas({
  scenario,
  activeDoc,
  onSelectDoc,
  activeClauseId,
  onClauseClick,
  activePage,
  onPageChange,
  activeHighlightText,
}: DocumentCanvasProps) {
  const currentDocObj = activeDoc === "docA" ? scenario.docA : scenario.docB || scenario.docA;
  const targetClauseRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to active clause when updated
  useEffect(() => {
    if (activeClauseId && targetClauseRef.current) {
      targetClauseRef.current.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [activeClauseId, activeDoc]);

  // Filter clauses by active page
  const pageClauses = currentDocObj.clauses.filter((c) => c.page === activePage);

  return (
    <div className="flex flex-col h-full rounded-2xl border border-white/10 bg-midnight-900/60 overflow-hidden shadow-xl">
      {/* Canvas Top Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-white/10 bg-white/[0.02]">
        {/* Document Switcher Tabs (if Doc B exists) */}
        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onSelectDoc("docA")}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeDoc === "docA"
                ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                : "text-text-muted hover:text-white"
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span className="truncate max-w-[180px]">{scenario.docA.name}</span>
            <span className="text-[10px] text-text-muted font-normal">({scenario.docA.version})</span>
          </button>

          {scenario.docB && (
            <button
              onClick={() => onSelectDoc("docB")}
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                activeDoc === "docB"
                  ? "bg-amber-500/15 text-amber-400 border border-amber-500/30"
                  : "text-text-muted hover:text-white"
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span className="truncate max-w-[180px]">{scenario.docB.name}</span>
              <span className="text-[10px] text-text-muted font-normal">({scenario.docB.version})</span>
            </button>
          )}
        </div>

        {/* Page Selector & Canvas Helpers */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1 text-xs text-text-muted">
            <span>Page</span>
            <div className="flex gap-1">
              {Array.from({ length: currentDocObj.pages }, (_, i) => i + 1).map((pg) => (
                <button
                  key={pg}
                  onClick={() => onPageChange(pg)}
                  className={`w-6 h-6 rounded flex items-center justify-center text-xs font-medium transition-colors ${
                    activePage === pg
                      ? "bg-amber-500 text-black font-bold"
                      : "bg-white/5 text-text-secondary hover:bg-white/10"
                  }`}
                >
                  {pg}
                </button>
              ))}
            </div>
            <span>of {currentDocObj.pages}</span>
          </div>

          <div className="h-4 w-px bg-white/10 mx-1 hidden sm:block" />

          <div className="hidden sm:flex items-center gap-1 text-[11px] text-emerald-400 font-mono bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
            <Layers className="w-3 h-3" />
            <span>PDF.js Text Coordinates</span>
          </div>
        </div>
      </div>

      {/* Main Document Paper / Viewport */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 bg-midnight-950/40">
        <div className="max-w-2xl mx-auto bg-[#141720] border border-white/10 rounded-xl shadow-2xl p-6 sm:p-8 relative min-h-[580px]">
          {/* Document Watermark / Header */}
          <div className="flex items-center justify-between pb-4 mb-6 border-b border-white/5 text-[11px] text-text-muted font-mono uppercase tracking-wider">
            <span>{currentDocObj.name}</span>
            <span>Page {activePage} • Confidential</span>
          </div>

          {/* Render Clauses on Current Page */}
          <div className="space-y-6">
            {pageClauses.length > 0 ? (
              pageClauses.map((clause) => {
                const isActive = activeClauseId === clause.id;
                return (
                  <div
                    key={clause.id}
                    ref={isActive ? targetClauseRef : null}
                    onClick={() => onClauseClick(clause.id)}
                    className={`group relative p-4 rounded-xl border transition-all duration-300 cursor-pointer ${
                      isActive
                        ? "bg-amber-500/10 border-amber-500/60 shadow-lg shadow-amber-500/10 active-canvas-highlight"
                        : "bg-white/[0.01] border-white/5 hover:border-white/20 hover:bg-white/[0.03]"
                    }`}
                  >
                    {/* Clause Title & Category Tag */}
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold font-mono tracking-tight text-white flex items-center gap-1.5">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                        {clause.title}
                      </span>
                      {isActive && (
                        <span className="flex items-center gap-1 text-[10px] font-semibold text-amber-400 bg-amber-500/20 px-2 py-0.5 rounded-md animate-pulse">
                          <span>Visual Grounding Match</span>
                        </span>
                      )}
                    </div>

                    {/* Clause Body Text with Highlighted Key Terms */}
                    <p className="text-xs sm:text-sm text-text-secondary leading-relaxed font-serif">
                      {clause.content}
                    </p>

                    {/* Render Highlighted Term Chips */}
                    {clause.highlightWords && clause.highlightWords.length > 0 && (
                      <div className="mt-3 flex flex-wrap gap-1.5 pt-2 border-t border-white/5">
                        {clause.highlightWords.map((word, wIdx) => (
                          <span
                            key={wIdx}
                            className={`px-2 py-0.5 text-[10px] font-mono rounded transition-colors ${
                              isActive
                                ? "bg-amber-500/30 text-amber-300 border border-amber-500/40"
                                : "bg-white/5 text-text-muted"
                            }`}
                          >
                            &quot;{word}&quot;
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            ) : (
              <div className="text-center py-12 text-text-muted text-xs">
                No clauses recorded on Page {activePage}. Switch page above to review document sections.
              </div>
            )}
          </div>

          {/* Document Footer */}
          <div className="mt-12 pt-4 border-t border-white/5 flex items-center justify-between text-[11px] text-text-muted font-mono">
            <span>Veridocs Forensic Canvas Highlighting</span>
            <span>Ref: {scenario.id}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
