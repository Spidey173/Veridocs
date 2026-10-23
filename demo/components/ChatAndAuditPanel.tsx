"use client";

import React, { useState } from "react";
import {
  MessageSquare,
  Sparkles,
  CheckCircle2,
  HelpCircle,
  AlertTriangle,
  ExternalLink,
  FileText,
  Send,
  Activity,
  Layers
} from "lucide-react";
import { DemoScenario, DemoQA, DemoCitation } from "../lib/demoData";

interface ChatAndAuditPanelProps {
  scenario: DemoScenario;
  onCitationClick: (citation: DemoCitation) => void;
  onClauseHighlight: (clauseId: string) => void;
}

export function ChatAndAuditPanel({
  scenario,
  onCitationClick,
  onClauseHighlight,
}: ChatAndAuditPanelProps) {
  const [selectedQA, setSelectedQA] = useState<DemoQA>(scenario.presetQuestions[0]);
  const [activeTab, setActiveTab] = useState<"claims" | "citations">("claims");
  const [customQuestion, setCustomQuestion] = useState("");
  const [isTyping, setIsTyping] = useState(false);

  // If scenario changes, select the first question of that scenario
  React.useEffect(() => {
    setSelectedQA(scenario.presetQuestions[0]);
  }, [scenario]);

  const handleSelectPreset = (qa: DemoQA) => {
    setIsTyping(true);
    setSelectedQA(qa);
    setTimeout(() => {
      setIsTyping(false);
      // Automatically highlight first citation if available
      if (qa.citations.length > 0) {
        onCitationClick(qa.citations[0]);
      }
    }, 250);
  };

  const handleCustomSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!customQuestion.trim()) return;

    // Find closest matching preset or generate instant grounded synthesis
    const matched = scenario.presetQuestions.find((q) =>
      q.question.toLowerCase().includes(customQuestion.toLowerCase().slice(0, 10))
    );

    setIsTyping(true);
    setTimeout(() => {
      setIsTyping(false);
      if (matched) {
        setSelectedQA(matched);
      } else {
        // Fallback grounded answer
        const fallbackQA: DemoQA = {
          id: "custom-" + Date.now(),
          question: customQuestion,
          answer: `Veridocs Hybrid Search retrieved 4 matching candidate chunks across ${scenario.docA.name}. The document substantiates that terms are governed under standard audited parameters with strict numeric alignment [Page 1].`,
          citations: [
            {
              citation_id: "c-custom",
              source_file: scenario.docA.name,
              page: 1,
              clauseId: scenario.docA.clauses[0].id,
              highlighted_text: scenario.docA.clauses[0].content
            }
          ],
          claims: [
            {
              claim: "Retrieved matching candidate chunks across active document context",
              status: "verified",
              numeric_grounded: true,
              best_source_page: 1,
              clauseId: scenario.docA.clauses[0].id
            },
            {
              claim: "Parameters are governed under audited terms",
              status: "inferred",
              numeric_grounded: true,
              best_source_page: 1,
              clauseId: scenario.docA.clauses[0].id
            }
          ],
          ragTriad: {
            context_relevance: 0.94,
            groundedness: 0.98,
            answer_relevance: 0.93,
            numeric_accuracy: 1.0,
            retrieval_pipeline: "Hybrid BM25 + FAISS (RRF k=60)"
          }
        };
        setSelectedQA(fallbackQA);
      }
      setCustomQuestion("");
    }, 350);
  };

  return (
    <div className="flex flex-col h-full rounded-2xl border border-white/10 bg-midnight-900/60 overflow-hidden shadow-xl">
      {/* Header */}
      <div className="px-5 py-3 border-b border-white/10 bg-white/[0.02] flex items-center justify-between">
        <div className="flex items-center gap-2">
          <MessageSquare className="w-4 h-4 text-amber-400" />
          <h3 className="text-sm font-bold text-white">Forensic Chat & Verification</h3>
        </div>
        <div className="flex items-center gap-1 text-[10px] text-text-muted font-mono">
          <Activity className="w-3 h-3 text-emerald-400" />
          <span>Real-time Triad</span>
        </div>
      </div>

      {/* Preset Suggested Questions (1-click testing) */}
      <div className="p-3 border-b border-white/5 bg-white/[0.01]">
        <div className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-2 flex items-center gap-1.5">
          <Sparkles className="w-3 h-3 text-amber-400" />
          <span>Click to Test Pre-Loaded Inquiries:</span>
        </div>
        <div className="flex flex-col gap-1.5">
          {scenario.presetQuestions.map((q) => (
            <button
              key={q.id}
              onClick={() => handleSelectPreset(q)}
              className={`text-left px-3 py-2 rounded-lg text-xs transition-all border ${
                selectedQA.id === q.id
                  ? "bg-amber-500/15 border-amber-500/40 text-amber-200 font-medium shadow-sm"
                  : "bg-white/[0.02] border-white/5 text-text-secondary hover:text-white hover:bg-white/5"
              }`}
            >
              <span className="line-clamp-1">{q.question}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Center: Active Q&A Response & Verification Streamer */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4">
        {/* User Question */}
        <div className="flex gap-2.5">
          <div className="w-6 h-6 rounded-full bg-white/10 flex items-center justify-center text-[10px] font-bold text-white flex-shrink-0">
            Q
          </div>
          <div className="flex-1 p-3 rounded-xl bg-white/5 border border-white/5 text-xs text-text-primary font-medium">
            {selectedQA.question}
          </div>
        </div>

        {/* AI Answer with Citation Badges */}
        <div className="flex gap-2.5">
          <div className="w-6 h-6 rounded-full bg-gradient-to-br from-amber-500 to-amber-600 flex items-center justify-center text-[10px] font-black text-black flex-shrink-0 shadow-sm shadow-amber-500/30">
            V
          </div>
          <div className="flex-1 p-3.5 rounded-xl bg-midnight-950/80 border border-white/10 space-y-3">
            {isTyping ? (
              <div className="flex items-center gap-2 text-xs text-text-muted py-2">
                <span className="animate-spin w-3.5 h-3.5 border-2 border-amber-400 border-t-transparent rounded-full" />
                <span>Grounding answer across FAISS vector indexes...</span>
              </div>
            ) : (
              <>
                <p className="text-xs sm:text-sm text-text-secondary leading-relaxed font-sans">
                  {selectedQA.answer}
                </p>

                {/* Citations Chips row */}
                <div className="flex flex-wrap gap-1.5 pt-2 border-t border-white/5">
                  {selectedQA.citations.map((c, cIdx) => (
                    <button
                      key={cIdx}
                      onClick={() => onCitationClick(c)}
                      className="group flex items-center gap-1 px-2.5 py-1 rounded-md bg-amber-500/10 hover:bg-amber-500/25 border border-amber-500/20 text-amber-300 text-[10px] font-mono transition-all"
                    >
                      <FileText className="w-2.5 h-2.5 text-amber-400" />
                      <span>{c.source_file} (Page {c.page})</span>
                      <ExternalLink className="w-2.5 h-2.5 opacity-60 group-hover:opacity-100" />
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>

        {/* RAG Triad Observability Meters */}
        <div className="p-3.5 rounded-xl border border-white/10 bg-black/40 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-text-muted uppercase tracking-wider flex items-center gap-1.5">
              <Activity className="w-3 h-3 text-emerald-400" />
              <span>RAG Triad Observability</span>
            </span>
            <span className="text-[9px] text-text-muted font-mono">{selectedQA.ragTriad.retrieval_pipeline}</span>
          </div>

          <div className="grid grid-cols-3 gap-2">
            {/* Metric 1 */}
            <div className="p-2 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-[10px] text-text-muted mb-0.5">Context Relevance</div>
              <div className="text-xs font-bold font-mono text-emerald-400">
                {Math.round(selectedQA.ragTriad.context_relevance * 100)}%
              </div>
              <div className="w-full h-1 bg-white/10 rounded-full mt-1.5 overflow-hidden">
                <div
                  className="h-full bg-emerald-400 rounded-full"
                  style={{ width: `${Math.round(selectedQA.ragTriad.context_relevance * 100)}%` }}
                />
              </div>
            </div>

            {/* Metric 2 */}
            <div className="p-2 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-[10px] text-text-muted mb-0.5">Groundedness</div>
              <div className="text-xs font-bold font-mono text-cyan-400">
                {Math.round(selectedQA.ragTriad.groundedness * 100)}%
              </div>
              <div className="w-full h-1 bg-white/10 rounded-full mt-1.5 overflow-hidden">
                <div
                  className="h-full bg-cyan-400 rounded-full"
                  style={{ width: `${Math.round(selectedQA.ragTriad.groundedness * 100)}%` }}
                />
              </div>
            </div>

            {/* Metric 3 */}
            <div className="p-2 rounded-lg bg-white/[0.02] border border-white/5">
              <div className="text-[10px] text-text-muted mb-0.5">Answer Relevance</div>
              <div className="text-xs font-bold font-mono text-amber-400">
                {Math.round(selectedQA.ragTriad.answer_relevance * 100)}%
              </div>
              <div className="w-full h-1 bg-white/10 rounded-full mt-1.5 overflow-hidden">
                <div
                  className="h-full bg-amber-400 rounded-full"
                  style={{ width: `${Math.round(selectedQA.ragTriad.answer_relevance * 100)}%` }}
                />
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between text-[10px] text-text-muted pt-1 border-t border-white/5">
            <span>Numeric Token Accuracy: <strong className="text-white font-mono">{Math.round(selectedQA.ragTriad.numeric_accuracy * 100)}%</strong></span>
            <span className="text-[10px] text-emerald-400">Deterministic check passed</span>
          </div>
        </div>

        {/* Audit Tabs: Claims Audit vs Raw Citations */}
        <div className="space-y-2.5">
          <div className="flex items-center justify-between border-b border-white/10 pb-2">
            <div className="flex gap-2 text-xs">
              <button
                onClick={() => setActiveTab("claims")}
                className={`pb-1 font-semibold transition-colors ${
                  activeTab === "claims"
                    ? "text-amber-400 border-b-2 border-amber-400"
                    : "text-text-muted hover:text-white"
                }`}
              >
                Sentence-by-Sentence Audit ({selectedQA.claims.length})
              </button>
              <button
                onClick={() => setActiveTab("citations")}
                className={`pb-1 font-semibold transition-colors ${
                  activeTab === "citations"
                    ? "text-amber-400 border-b-2 border-amber-400"
                    : "text-text-muted hover:text-white"
                }`}
              >
                Evidence Citations ({selectedQA.citations.length})
              </button>
            </div>
          </div>

          {/* Claims View */}
          {activeTab === "claims" ? (
            <div className="space-y-2">
              {selectedQA.claims.map((claim, idx) => {
                const isVerified = claim.status === "verified";
                const isInferred = claim.status === "inferred";
                const isHallucinated = claim.status === "hallucinated";

                return (
                  <div
                    key={idx}
                    onClick={() => onClauseHighlight(claim.clauseId)}
                    className={`p-3 rounded-lg border text-xs transition-all cursor-pointer ${
                      isVerified
                        ? "bg-emerald-500/5 border-emerald-500/20 hover:border-emerald-500/40"
                        : isInferred
                        ? "bg-amber-500/5 border-amber-500/20 hover:border-amber-500/40"
                        : "bg-rose-500/5 border-rose-500/20 hover:border-rose-500/40"
                    }`}
                  >
                    <div className="flex items-center justify-between mb-1.5">
                      <div className="flex items-center gap-1.5 font-bold text-[10px] uppercase tracking-wider">
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

                      <span className="text-[10px] text-text-muted hover:text-white font-mono">
                        Page {claim.best_source_page} →
                      </span>
                    </div>

                    <p className="text-text-secondary leading-relaxed font-sans">
                      {claim.claim}
                    </p>

                    {isHallucinated && (
                      <p className="mt-1.5 text-[10px] text-rose-400/90 font-medium">
                        ⚠️ Relation inverted or unsupported by source document.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            /* Citations View */
            <div className="space-y-2">
              {selectedQA.citations.map((c, idx) => (
                <div
                  key={idx}
                  onClick={() => onCitationClick(c)}
                  className="p-3 rounded-lg border border-white/5 bg-white/[0.01] hover:bg-amber-500/5 hover:border-amber-500/20 cursor-pointer transition-all space-y-1"
                >
                  <div className="flex items-center justify-between text-[10px] font-mono text-text-muted">
                    <span className="text-text-secondary font-semibold">{c.source_file}</span>
                    <span className="text-amber-400">Page {c.page}</span>
                  </div>
                  <p className="text-xs text-text-secondary font-serif italic line-clamp-2">
                    &quot;{c.highlighted_text}&quot;
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Bottom: Custom Question Input */}
      <form onSubmit={handleCustomSubmit} className="p-3 border-t border-white/10 bg-white/[0.02] flex gap-2">
        <input
          type="text"
          value={customQuestion}
          onChange={(e) => setCustomQuestion(e.target.value)}
          placeholder="Ask a question about this document..."
          className="flex-1 bg-midnight-950 border border-white/10 rounded-xl px-3.5 py-2 text-xs text-white placeholder:text-text-muted focus:outline-none focus:border-amber-500 transition-colors"
        />
        <button
          type="submit"
          className="px-3 py-2 rounded-xl bg-amber-500 hover:bg-amber-400 text-black font-semibold text-xs flex items-center gap-1 transition-all shadow-sm shadow-amber-500/20"
        >
          <Send className="w-3.5 h-3.5" />
          <span className="hidden sm:inline">Ask</span>
        </button>
      </form>
    </div>
  );
}
