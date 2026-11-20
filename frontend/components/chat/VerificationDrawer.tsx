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
  AlertOctagon,
} from "lucide-react";
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

  if (
    (!citations || citations.length === 0) &&
    (!claimVerifications || claimVerifications.length === 0) &&
    !ragTriad
  ) {
    return null;
  }

  const verifiedCount = claimVerifications.filter((c) => c.status === "verified").length;
  const inferredCount = claimVerifications.filter((c) => c.status === "inferred").length;
  const hallucinatedCount = claimVerifications.filter((c) => c.status === "hallucinated").length;

  return (
    <div className="mt-2.5 border border-[var(--border-subtle)] rounded-lg bg-[var(--bg-surface)] overflow-hidden select-none">
      {/* Header Summary Trigger */}
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-2.5 hover:bg-[var(--bg-surface-raised)] transition-colors text-left"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <ShieldCheck
            className={`w-3.5 h-3.5 shrink-0 ${
              confidenceScore && confidenceScore >= 0.8
                ? "text-[var(--color-success)]"
                : confidenceScore && confidenceScore >= 0.5
                ? "text-[var(--color-warning)]"
                : "text-[var(--color-danger)]"
            }`}
          />
          <span className="text-xs font-semibold text-[var(--text-primary)]">
            Grounding & Verification
          </span>

          {confidenceScore !== undefined && (
            <span className="text-[10px] font-mono-data px-1.5 py-0.2 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-[var(--text-secondary)] font-medium">
              {Math.round(confidenceScore * 100)}% verified
            </span>
          )}

          {claimVerifications.length > 0 && (
            <div className="flex items-center gap-1.5 text-[10.5px] font-mono-data text-[var(--text-muted)]">
              {verifiedCount > 0 && (
                <span className="text-[var(--color-success)] font-medium">
                  {verifiedCount} verified
                </span>
              )}
              {inferredCount > 0 && (
                <span>• {inferredCount} inferred</span>
              )}
              {hallucinatedCount > 0 && (
                <span className="text-[var(--color-danger)] font-medium">
                  • {hallucinatedCount} flagged
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 ml-2 text-[10.5px] text-[var(--text-muted)] font-mono-data">
          <span>
            {citations.length} {citations.length === 1 ? "source" : "sources"}
          </span>
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5" />
          )}
        </div>
      </button>

      {/* Expanded Claims & Citations Breakdown */}
      {expanded && (
        <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-canvas)] p-3 space-y-3">
          {/* Tab Selector */}
          <div className="flex items-center gap-1 pb-2 border-b border-[var(--border-subtle)]">
            {claimVerifications.length > 0 && (
              <button
                type="button"
                onClick={() => setActiveTab("claims")}
                className={`text-[11px] font-medium px-2.5 py-1 rounded transition-colors ${
                  activeTab === "claims"
                    ? "bg-[var(--bg-surface)] text-[var(--text-primary)] border border-[var(--border-default)] font-semibold"
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                }`}
              >
                Claims Audit ({claimVerifications.length})
              </button>
            )}
            {ragTriad && (
              <button
                type="button"
                onClick={() => setActiveTab("triad")}
                className={`text-[11px] font-medium px-2.5 py-1 rounded transition-colors flex items-center gap-1.5 ${
                  activeTab === "triad"
                    ? "bg-[var(--bg-surface)] text-[var(--text-primary)] border border-[var(--border-default)] font-semibold"
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                }`}
              >
                <Gauge className="w-3 h-3 text-[var(--color-accent)]" />
                <span>RAG Triad Evals</span>
              </button>
            )}
            {citations.length > 0 && (
              <button
                type="button"
                onClick={() => setActiveTab("citations")}
                className={`text-[11px] font-medium px-2.5 py-1 rounded transition-colors ${
                  activeTab === "citations"
                    ? "bg-[var(--bg-surface)] text-[var(--text-primary)] border border-[var(--border-default)] font-semibold"
                    : "text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                }`}
              >
                Source Citations ({citations.length})
              </button>
            )}
          </div>

          {/* Tab 1: Compact, Honest RAG Triad Telemetry Table & Bars */}
          {activeTab === "triad" && ragTriad && (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)] font-mono-data">
                <span className="font-semibold text-[var(--text-primary)] uppercase">
                  Production RAG Triad Telemetry
                </span>
                {ragTriad.latency_ms && (
                  <span>Latency: {Math.round(ragTriad.latency_ms)}ms</span>
                )}
              </div>

              {/* Real Table of Evaluation Dimensions */}
              <div className="border border-[var(--border-subtle)] rounded-lg overflow-hidden bg-[var(--bg-surface)]">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-[var(--border-subtle)] bg-[var(--bg-surface-raised)] text-[10.5px] font-mono-data text-[var(--text-muted)] uppercase">
                      <th className="py-2 px-3 font-semibold">Evaluation Dimension</th>
                      <th className="py-2 px-3 font-semibold text-right w-20">Score</th>
                      <th className="py-2 px-3 font-semibold w-28">Fidelity Bar</th>
                      <th className="py-2 px-3 font-semibold hidden sm:table-cell">Meaning</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[var(--border-subtle)] text-[12px]">
                    {/* Groundedness */}
                    <tr>
                      <td className="py-2 px-3 font-medium text-[var(--text-primary)]">
                        Groundedness
                      </td>
                      <td className="py-2 px-3 text-right font-mono-data font-semibold text-[var(--text-primary)]">
                        {Math.round(ragTriad.groundedness * 100)}%
                      </td>
                      <td className="py-2 px-3">
                        <div className="h-1.5 w-full bg-[var(--bg-subtle)] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[var(--color-accent)] rounded-full"
                            style={{ width: `${Math.round(ragTriad.groundedness * 100)}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-2 px-3 text-[11px] text-[var(--text-muted)] hidden sm:table-cell">
                        Directly supported by retrieved text; zero speculative claims.
                      </td>
                    </tr>

                    {/* Context Relevance */}
                    <tr>
                      <td className="py-2 px-3 font-medium text-[var(--text-primary)]">
                        Context Relevance
                      </td>
                      <td className="py-2 px-3 text-right font-mono-data font-semibold text-[var(--text-primary)]">
                        {Math.round(ragTriad.context_relevance * 100)}%
                      </td>
                      <td className="py-2 px-3">
                        <div className="h-1.5 w-full bg-[var(--bg-subtle)] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[var(--color-accent)] rounded-full"
                            style={{ width: `${Math.round(ragTriad.context_relevance * 100)}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-2 px-3 text-[11px] text-[var(--text-muted)] hidden sm:table-cell">
                        Retrieved passages contain exact clauses queried without noise.
                      </td>
                    </tr>

                    {/* Answer Relevance */}
                    <tr>
                      <td className="py-2 px-3 font-medium text-[var(--text-primary)]">
                        Answer Relevance
                      </td>
                      <td className="py-2 px-3 text-right font-mono-data font-semibold text-[var(--text-primary)]">
                        {Math.round(ragTriad.answer_relevance * 100)}%
                      </td>
                      <td className="py-2 px-3">
                        <div className="h-1.5 w-full bg-[var(--bg-subtle)] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[var(--color-accent)] rounded-full"
                            style={{ width: `${Math.round(ragTriad.answer_relevance * 100)}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-2 px-3 text-[11px] text-[var(--text-muted)] hidden sm:table-cell">
                        Addresses query requirements directly without generic digression.
                      </td>
                    </tr>

                    {/* Numeric Token Fidelity */}
                    <tr>
                      <td className="py-2 px-3 font-medium text-[var(--text-primary)]">
                        Numeric Token Fidelity
                      </td>
                      <td className="py-2 px-3 text-right font-mono-data font-semibold text-[var(--text-primary)]">
                        {Math.round((ragTriad.numeric_accuracy ?? 1.0) * 100)}%
                      </td>
                      <td className="py-2 px-3">
                        <div className="h-1.5 w-full bg-[var(--bg-subtle)] rounded-full overflow-hidden">
                          <div
                            className="h-full bg-[var(--color-accent)] rounded-full"
                            style={{ width: `${Math.round((ragTriad.numeric_accuracy ?? 1.0) * 100)}%` }}
                          />
                        </div>
                      </td>
                      <td className="py-2 px-3 text-[11px] text-[var(--text-muted)] hidden sm:table-cell">
                        Exact numeric values (dates, dollars, percentages) verified against source.
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Low Score Warning Flag (if any metric < 70%) */}
              {(ragTriad.groundedness < 0.7 ||
                ragTriad.context_relevance < 0.7 ||
                ragTriad.answer_relevance < 0.7) && (
                <div className="p-2 rounded border border-[var(--color-warning-border)] bg-[var(--color-warning-bg)] text-[var(--color-warning)] text-[11px] flex items-center gap-2">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  <span>
                    Auditor notice: One or more evaluation dimensions fell below 70%. Inspect source citations manually.
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Tab 2: Claims Audit */}
          {activeTab === "claims" && claimVerifications.length > 0 && (
            <div className="space-y-1.5">
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
                    className={`p-2 rounded border text-xs transition-colors ${
                      isVerified
                        ? "border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-raised)]"
                        : isInferred
                        ? "border-[var(--color-warning-border)] bg-[var(--color-warning-bg)]"
                        : "border-[var(--color-danger-border)] bg-[var(--color-danger-bg)]"
                    } ${item.best_source_page ? "cursor-pointer" : ""}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-1.5 text-[10px] font-mono-data uppercase font-semibold">
                        {isVerified && (
                          <span className="text-[var(--color-success)] flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" />
                            Verified Claim
                          </span>
                        )}
                        {isInferred && (
                          <span className="text-[var(--color-warning)] flex items-center gap-1">
                            <HelpCircle className="w-3 h-3" />
                            Inferred Claim
                          </span>
                        )}
                        {isHallucinated && (
                          <span className="text-[var(--color-danger)] flex items-center gap-1">
                            <AlertTriangle className="w-3 h-3" />
                            Unverified Assertion
                          </span>
                        )}
                      </div>

                      {item.best_source_page && (
                        <div className="flex items-center gap-1 text-[10px] text-[var(--text-muted)] hover:text-[var(--text-primary)] font-mono-data">
                          <span>Page {item.best_source_page}</span>
                          <ExternalLink className="w-2.5 h-2.5" />
                        </div>
                      )}
                    </div>

                    <p className="text-[var(--text-secondary)] text-[12px] leading-relaxed">
                      {item.claim}
                    </p>
                  </div>
                );
              })}
            </div>
          )}

          {/* Tab 3: Source Citations */}
          {(activeTab === "citations" || claimVerifications.length === 0) && (
            <div className="space-y-1.5">
              {citations.map((citation, idx) => (
                <div
                  key={citation.citation_id || idx}
                  onClick={() => highlightCitation(citation)}
                  className="flex flex-col p-2 rounded border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:border-[var(--color-accent-border)] cursor-pointer transition-colors"
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className="flex items-center gap-1.5 text-[10.5px] font-mono-data text-[var(--text-primary)] font-medium truncate max-w-[240px]">
                      <FileText className="w-3 h-3 text-[var(--color-accent)] shrink-0" />
                      <span className="truncate">{citation.source_file}</span>
                    </div>
                    <span className="text-[10px] font-mono-data px-1 rounded bg-[var(--bg-subtle)] text-[var(--text-muted)] border border-[var(--border-subtle)] shrink-0">
                      Page {citation.page}
                    </span>
                  </div>

                  <p className="text-[11.5px] text-[var(--text-secondary)] leading-relaxed italic line-clamp-2">
                    &quot;{citation.highlighted_text}&quot;
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
