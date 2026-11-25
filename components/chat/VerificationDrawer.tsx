"use client";

import { useState } from "react";
import {
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  FileText,
  CheckCircle2,
  AlertTriangle,
  Table as TableIcon,
  XCircle,
  HelpCircle,
  Image as ImageIcon,
} from "lucide-react";
import type { CitationInfo, CitationCheckResult } from "@/lib/api";
import { useAppStore } from "@/lib/store";

interface CitationCheckDrawerProps {
  citations?: CitationInfo[];
  citationCheck?: CitationCheckResult;
}

export default function VerificationDrawer({
  citations = [],
  citationCheck,
}: CitationCheckDrawerProps) {
  const [expanded, setExpanded] = useState(false);
  const { highlightCitation } = useAppStore();

  if (
    (!citations || citations.length === 0) &&
    (!citationCheck || citationCheck.total_claims === 0)
  ) {
    return null;
  }

  const score = citationCheck ? Math.round(citationCheck.citation_score * 100) : null;
  const isHighMatch = score !== null ? score >= 70 : citations.length > 0;
  const hasLowOcrWarning = citationCheck?.has_low_confidence_ocr_warning;
  const hasContradictionWarning = citationCheck?.has_contradiction_warning;
  const hasVisionWarning = citationCheck?.has_vision_only_warning;

  return (
    <div className="mt-2 border border-[var(--border-subtle)] rounded bg-[var(--bg-surface)] overflow-hidden text-xs select-none">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-2 hover:bg-[var(--bg-subtle)] transition-colors text-left"
      >
        <div className="flex items-center gap-2">
          <ShieldCheck
            className={`w-3.5 h-3.5 ${
              hasContradictionWarning
                ? "text-red-500"
                : hasLowOcrWarning
                ? "text-amber-500"
                : isHighMatch
                ? "text-emerald-500"
                : "text-amber-500"
            }`}
          />
          <span className="font-semibold text-[var(--text-primary)]">
            Citation Check
          </span>

          {score !== null && (
            <span className="px-1.5 py-0.2 rounded text-[10px] font-mono-data bg-[var(--bg-subtle)] border border-[var(--border-subtle)] text-[var(--text-secondary)]">
              {score}% grounded
            </span>
          )}

          {citations.length > 0 && (
            <span className="text-[10px] text-[var(--text-muted)] font-mono-data">
              ({citations.length} {citations.length === 1 ? "citation" : "citations"})
            </span>
          )}

          {hasContradictionWarning && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-mono-data bg-red-500/10 text-red-500 border border-red-500/20">
              <XCircle className="w-2.5 h-2.5" />
              <span>Contradiction</span>
            </span>
          )}

          {hasLowOcrWarning && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-mono-data bg-amber-500/10 text-amber-500 border border-amber-500/20">
              <AlertTriangle className="w-2.5 h-2.5" />
              <span>Low OCR</span>
            </span>
          )}

          {hasVisionWarning && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.2 rounded text-[10px] font-mono-data bg-blue-500/10 text-blue-400 border border-blue-500/20">
              <ImageIcon className="w-2.5 h-2.5" />
              <span>Vision</span>
            </span>
          )}
        </div>

        <div className="text-[var(--text-muted)]">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </button>

      {expanded && (
        <div className="p-3 border-t border-[var(--border-subtle)] space-y-3 bg-[var(--bg-canvas)]">
          {/* Contradiction Warning Banner */}
          {hasContradictionWarning && (
            <div className="p-2.5 rounded bg-red-500/10 border border-red-500/20 text-red-500 text-[11px] flex items-start gap-2">
              <XCircle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <div className="leading-tight space-y-0.5">
                <p className="font-semibold">Contradicted Claim Detected</p>
                <p className="text-[10.5px] opacity-90">
                  One or more claims directly contradict the source document text according to natural language inference (NLI).
                </p>
              </div>
            </div>
          )}

          {/* Low OCR Confidence Warning Banner */}
          {hasLowOcrWarning && (
            <div className="p-2.5 rounded bg-amber-500/10 border border-amber-500/20 text-amber-500 text-[11px] flex items-start gap-2">
              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <div className="leading-tight space-y-0.5">
                <p className="font-semibold">Low-Confidence OCR Detected</p>
                <p className="text-[10.5px] opacity-90">
                  One or more answer statements rely on text extracted via OCR from low-quality scans. Treat citations with appropriate scrutiny.
                </p>
              </div>
            </div>
          )}

          {/* Vision-Derived Content Banner */}
          {hasVisionWarning && (
            <div className="p-2.5 rounded bg-blue-500/10 border border-blue-500/20 text-blue-400 text-[11px] flex items-start gap-2">
              <ImageIcon className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <div className="leading-tight space-y-0.5">
                <p className="font-semibold">Vision Model Analysis Used</p>
                <p className="text-[10.5px] opacity-90">
                  Some claims are verified against multimodal descriptions of charts, diagrams, or figures rather than raw textual layers.
                </p>
              </div>
            </div>
          )}

          {/* Real Citations with OCR, Table, and Figure Badges */}
          {citations.length > 0 && (
            <div>
              <p className="text-[11px] font-mono-data font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">
                Page Citations (Click to View in PDF)
              </p>
              <div className="space-y-1.5">
                {citations.map((c, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => highlightCitation(c)}
                    className="w-full text-left p-2 rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--color-accent)] transition-colors flex items-start gap-2 group"
                  >
                    {c.chunk_type === "table" ? (
                      <TableIcon className="w-3.5 h-3.5 text-purple-400 shrink-0 mt-0.5" />
                    ) : c.chunk_type === "figure" ? (
                      <ImageIcon className="w-3.5 h-3.5 text-blue-400 shrink-0 mt-0.5" />
                    ) : (
                      <FileText className="w-3.5 h-3.5 text-[var(--color-accent)] shrink-0 mt-0.5" />
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2 font-mono-data text-[10.5px] text-[var(--text-secondary)] mb-0.5">
                        <div className="flex items-center gap-1.5 truncate min-w-0">
                          <span className="font-semibold truncate">
                            {c.source_file}
                            {c.section_path ? ` · ${c.section_path}` : ""}
                            {` · p.${c.page}`}
                          </span>
                          {/* Table / Figure / OCR Badge */}
                          {c.chunk_type === "table" && (
                            <span className="px-1 py-0.2 rounded text-[9px] bg-purple-500/10 text-purple-400 border border-purple-500/20 shrink-0">
                              Table
                            </span>
                          )}
                          {c.chunk_type === "figure" && (
                            <span className="px-1 py-0.2 rounded text-[9px] bg-blue-500/10 text-blue-400 border border-blue-500/20 shrink-0">
                              Figure
                            </span>
                          )}
                          {c.extraction_method === "ocr" && (
                            <span className="px-1 py-0.2 rounded text-[9px] bg-amber-500/10 text-amber-500 border border-amber-500/20 shrink-0">
                              OCR {c.ocr_confidence ? `${Math.round(c.ocr_confidence * 100)}%` : ""}
                            </span>
                          )}
                        </div>
                        <span className="text-[var(--color-accent)] font-semibold shrink-0">p.{c.page}</span>
                      </div>
                      <p className="text-[11.5px] text-[var(--text-secondary)] line-clamp-3 leading-relaxed">
                        &ldquo;{c.highlighted_text}&rdquo;
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Real Claim-by-Claim Support Check */}
          {citationCheck && citationCheck.claims && citationCheck.claims.length > 0 && (
            <div>
              <p className="text-[11px] font-mono-data font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">
                Answer Claim Support ({citationCheck.supported_claims}/{citationCheck.total_claims} verified
                {citationCheck.contradicted_claims ? `, ${citationCheck.contradicted_claims} contradicted` : ""})
              </p>
              <div className="space-y-1">
                {citationCheck.claims.map((claim, idx) => {
                  const status = claim.status || (claim.is_supported ? "supported" : "unsupported");
                  return (
                    <div
                      key={idx}
                      className={`p-2 rounded border text-xs flex items-start gap-2 ${
                        status === "contradicted"
                          ? "bg-red-500/5 border-red-500/20"
                          : status === "supported"
                          ? "bg-[var(--bg-surface)] border-[var(--border-subtle)]"
                          : "bg-amber-500/5 border-amber-500/20"
                      }`}
                    >
                      {status === "supported" ? (
                        <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                      ) : status === "contradicted" ? (
                        <XCircle className="w-3.5 h-3.5 text-red-500 shrink-0 mt-0.5" />
                      ) : (
                        <HelpCircle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                      )}
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2 mb-0.5">
                          <p className="text-[var(--text-primary)] leading-normal">{claim.claim}</p>
                          <span
                            className={`px-1.5 py-0.2 rounded text-[9.5px] font-mono-data shrink-0 font-medium ${
                              status === "supported"
                                ? "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
                                : status === "contradicted"
                                ? "bg-red-500/10 text-red-500 border border-red-500/20"
                                : "bg-amber-500/10 text-amber-500 border border-amber-500/20"
                            }`}
                          >
                            {status.toUpperCase()}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 mt-1 text-[10px] font-mono-data text-[var(--text-muted)]">
                          <span>Confidence: {Math.round((claim.score ?? claim.overlap_score) * 100)}%</span>
                          {claim.section_path && <span>• {claim.section_path}</span>}
                          {claim.matched_page && <span>• p.{claim.matched_page}</span>}
                          {claim.chunk_type && (
                            <span className="uppercase text-[9px] px-1 py-0.2 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)]">
                              {claim.chunk_type}
                            </span>
                          )}
                          {claim.is_vision_only && (
                            <span className="text-blue-400 font-semibold">• Vision-derived</span>
                          )}
                          {claim.is_low_confidence_ocr && (
                            <span className="text-amber-500 font-semibold">• Low OCR source</span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
