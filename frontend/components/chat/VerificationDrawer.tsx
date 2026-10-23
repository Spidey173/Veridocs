"use client";

import { useState } from "react";
import {
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  FileText,
  CheckCircle2,
  AlertTriangle,
  HelpCircle,
  Activity,
  Gauge,
} from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import type { CitationInfo, ClaimVerificationItem, RagTriadMetrics } from "@/lib/api";
import { useAppStore } from "@/lib/store";

interface VerificationDrawerProps {
  citations: CitationInfo[];
  confidenceScore?: number;
  claimVerifications?: ClaimVerificationItem[];
  ragTriad?: RagTriadMetrics;
}

export default function VerificationDrawer({
  citations,
  confidenceScore,
  claimVerifications = [],
  ragTriad,
}: VerificationDrawerProps) {
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<"claims" | "triad" | "citations">("claims");
  const { highlightCitation, setCurrentPage } = useAppStore();

  if ((!citations || citations.length === 0) && (!claimVerifications || claimVerifications.length === 0) && !ragTriad) {
    return null;
  }

  const verifiedCount = claimVerifications.filter((c) => c.status === "verified").length;
  const inferredCount = claimVerifications.filter((c) => c.status === "inferred").length;
  const hallucinatedCount = claimVerifications.filter((c) => c.status === "hallucinated").length;

  return (
    <div className="mt-3 border border-white/10 rounded-xl bg-white/[0.02] overflow-hidden select-none backdrop-blur-sm shadow-sm">
      {/* Header Summary Trigger */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-white/[0.04] transition-colors"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <ShieldCheck
            className={`w-4 h-4 ${
              confidenceScore && confidenceScore >= 0.8
                ? "text-emerald-400"
                : confidenceScore && confidenceScore >= 0.5
                ? "text-amber-400"
                : "text-rose-400"
            }`}
          />
          <span className="text-xs font-semibold text-text-secondary">
            Grounding & Verification
          </span>

          {confidenceScore !== undefined && (
            <span className="text-[10px] bg-white/10 px-2 py-0.5 rounded-full text-white font-mono font-medium">
              {Math.round(confidenceScore * 100)}% verified
            </span>
          )}

          {claimVerifications.length > 0 && (
            <div className="flex items-center gap-1.5 text-[10px] ml-1">
              {verifiedCount > 0 && (
                <span className="text-emerald-400 font-medium">
                  {verifiedCount} verified
                </span>
              )}
              {inferredCount > 0 && (
                <span className="text-amber-400 font-medium">
                  • {inferredCount} inferred
                </span>
              )}
              {hallucinatedCount > 0 && (
                <span className="text-rose-400 font-medium">
                  • {hallucinatedCount} flagged
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 ml-2">
          <span className="text-[10px] text-text-muted">
            {citations.length} source{citations.length !== 1 ? "s" : ""}
          </span>
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5 text-text-muted" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-text-muted" />
          )}
        </div>
      </button>

      {/* Expanded Claims & Citations List */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="border-t border-white/10 bg-black/25 px-3 py-3 space-y-3"
          >
            {/* Tab selector */}
            <div className="flex items-center gap-1.5 pb-1 border-b border-white/5 flex-wrap">
              {claimVerifications.length > 0 && (
                <button
                  type="button"
                  onClick={() => setActiveTab("claims")}
                  className={`text-[11px] font-medium px-2.5 py-1 rounded-md transition-colors ${
                    activeTab === "claims"
                      ? "bg-white/15 text-white"
                      : "text-text-muted hover:text-white"
                  }`}
                >
                  Claims Audit ({claimVerifications.length})
                </button>
              )}
              {ragTriad && (
                <button
                  type="button"
                  onClick={() => setActiveTab("triad")}
                  className={`text-[11px] font-medium px-2.5 py-1 rounded-md transition-colors flex items-center gap-1 ${
                    activeTab === "triad"
                      ? "bg-accent-primary/20 text-accent-primary border border-accent-primary/30"
                      : "text-text-muted hover:text-white"
                  }`}
                >
                  <Gauge className="w-3 h-3 text-accent-primary" />
                  RAG Triad Evals
                </button>
              )}
              {citations.length > 0 && (
                <button
                  type="button"
                  onClick={() => setActiveTab("citations")}
                  className={`text-[11px] font-medium px-2.5 py-1 rounded-md transition-colors ${
                    activeTab === "citations"
                      ? "bg-white/15 text-white"
                      : "text-text-muted hover:text-white"
                  }`}
                >
                  Source Citations ({citations.length})
                </button>
              )}
            </div>

            {/* View 0: RAG Triad Metrics */}
            {activeTab === "triad" && ragTriad && (
              <div className="p-3 rounded-xl border border-white/10 bg-white/[0.02] space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-accent-primary" />
                    <span className="text-xs font-semibold text-text-primary">Production RAG Triad Telemetry</span>
                  </div>
                  {ragTriad.latency_ms && (
                    <span className="text-[10px] text-text-muted font-mono bg-white/5 px-2 py-0.5 rounded">
                      {Math.round(ragTriad.latency_ms)}ms latency
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-3 gap-2">
                  <div className="p-2 rounded-lg bg-black/40 border border-white/5">
                    <div className="text-[10px] text-text-muted mb-0.5">Context Relevance</div>
                    <div className="text-sm font-bold font-mono text-emerald-400">
                      {Math.round(ragTriad.context_relevance * 100)}%
                    </div>
                    <div className="w-full h-1 bg-white/10 rounded-full mt-1.5 overflow-hidden">
                      <div className="h-full bg-emerald-400 rounded-full" style={{ width: `${Math.round(ragTriad.context_relevance * 100)}%` }} />
                    </div>
                  </div>

                  <div className="p-2 rounded-lg bg-black/40 border border-white/5">
                    <div className="text-[10px] text-text-muted mb-0.5">Groundedness</div>
                    <div className="text-sm font-bold font-mono text-cyan-400">
                      {Math.round(ragTriad.groundedness * 100)}%
                    </div>
                    <div className="w-full h-1 bg-white/10 rounded-full mt-1.5 overflow-hidden">
                      <div className="h-full bg-cyan-400 rounded-full" style={{ width: `${Math.round(ragTriad.groundedness * 100)}%` }} />
                    </div>
                  </div>

                  <div className="p-2 rounded-lg bg-black/40 border border-white/5">
                    <div className="text-[10px] text-text-muted mb-0.5">Answer Relevance</div>
                    <div className="text-sm font-bold font-mono text-amber-400">
                      {Math.round(ragTriad.answer_relevance * 100)}%
                    </div>
                    <div className="w-full h-1 bg-white/10 rounded-full mt-1.5 overflow-hidden">
                      <div className="h-full bg-amber-400 rounded-full" style={{ width: `${Math.round(ragTriad.answer_relevance * 100)}%` }} />
                    </div>
                  </div>
                </div>

                <div className="flex items-center justify-between text-[10px] text-text-muted pt-1 border-t border-white/5">
                  <span>Numeric Token Fidelity: <strong className="text-white font-mono">{Math.round(ragTriad.numeric_accuracy * 100)}%</strong></span>
                  <span className="text-[9px] text-text-muted italic">{ragTriad.retrieval_pipeline || "Hybrid Search"}</span>
                </div>
              </div>
            )}

            {/* View 1: Sentence-by-Sentence Claim Audit */}
            {activeTab === "claims" && claimVerifications.length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] text-text-muted bg-white/[0.02] border border-white/5 rounded-lg px-2.5 py-1.5 flex items-center justify-between">
                  <span>Method: Lexical token & numeric overlap heuristic</span>
                  <span className="text-[9px] text-amber-400/80">Surface check, does not prove semantic truth</span>
                </div>
                {claimVerifications.map((item, idx) => {
                  const isVerified = item.status === "verified";
                  const isInferred = item.status === "inferred";
                  const isHallucinated = item.status === "hallucinated";

                  return (
                    <div
                      key={idx}
                      onClick={() => {
                        if (item.best_source_page) {
                          setCurrentPage(item.best_source_page);
                        }
                      }}
                      className={`p-2.5 rounded-lg border text-xs transition-all ${
                        isVerified
                          ? "bg-emerald-500/5 border-emerald-500/20 hover:border-emerald-500/40"
                          : isInferred
                          ? "bg-amber-500/5 border-amber-500/20 hover:border-amber-500/40"
                          : "bg-rose-500/5 border-rose-500/20 hover:border-rose-500/40"
                      } ${item.best_source_page ? "cursor-pointer" : ""}`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <div className="flex items-center gap-1.5 font-semibold text-[10px] uppercase tracking-wider">
                          {isVerified && (
                            <span className="flex items-center gap-1 text-emerald-400">
                              <CheckCircle2 className="w-3 h-3" />
                              <span>Verified Claim</span>
                            </span>
                          )}
                          {isInferred && (
                            <span className="flex items-center gap-1 text-amber-400">
                              <HelpCircle className="w-3 h-3" />
                              <span>Inferred Reasoning</span>
                            </span>
                          )}
                          {isHallucinated && (
                            <span className="flex items-center gap-1 text-rose-400">
                              <AlertTriangle className="w-3 h-3" />
                              <span>Potential Hallucination</span>
                            </span>
                          )}
                        </div>

                        {item.best_source_page && (
                          <div className="flex items-center gap-1 text-[10px] text-text-muted hover:text-white font-mono">
                            <span>Jump to Page {item.best_source_page}</span>
                            <ExternalLink className="w-2.5 h-2.5" />
                          </div>
                        )}
                      </div>

                      <p className="text-text-secondary leading-relaxed font-sans">
                        {item.claim}
                      </p>

                      {item.numeric_grounded === false && (
                        <p className="mt-1.5 text-[10px] text-rose-400/90 font-medium">
                          ⚠️ Numbers/metrics in this claim could not be matched in source text.
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* View 2: Source Citations */}
            {(activeTab === "citations" || claimVerifications.length === 0) && (
              <div className="space-y-2">
                {citations.map((citation, idx) => (
                  <div
                    key={citation.citation_id || idx}
                    onClick={() => highlightCitation(citation)}
                    className="group flex flex-col p-2.5 rounded-lg border border-white/5 bg-white/[0.01] hover:bg-accent-soft/20 hover:border-accent-primary/20 cursor-pointer transition-all"
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-1.5 text-[10px] font-semibold text-text-muted group-hover:text-accent-primary uppercase tracking-wider">
                        <FileText className="w-3 h-3 text-accent-primary" />
                        <span>{citation.source_file}</span>
                      </div>
                      <div className="flex items-center gap-1 text-[10px] text-text-muted group-hover:text-text-secondary font-mono">
                        <span>Page {citation.page}</span>
                        <ExternalLink className="w-2.5 h-2.5" />
                      </div>
                    </div>

                    <p className="text-xs text-text-secondary leading-relaxed line-clamp-2 italic">
                      &quot;{citation.highlighted_text}&quot;
                    </p>

                    <div className="flex items-center gap-1 mt-2 text-[9px] font-semibold text-emerald-400 uppercase tracking-wider">
                      <CheckCircle2 className="w-3 h-3" />
                      <span>Verified Grounding Evidence</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
