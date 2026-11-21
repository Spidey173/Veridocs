"use client";

import { useState } from "react";
import {
  ShieldCheck,
  ChevronDown,
  ChevronUp,
  FileText,
  CheckCircle2,
  AlertTriangle,
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

  if ((!citations || citations.length === 0) && !citationCheck) {
    return null;
  }

  const score = citationCheck ? Math.round(citationCheck.citation_score * 100) : null;
  const isHighMatch = score !== null ? score >= 70 : citations.length > 0;

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
              isHighMatch ? "text-emerald-500" : "text-amber-500"
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
        </div>

        <div className="text-[var(--text-muted)]">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </div>
      </button>

      {expanded && (
        <div className="p-3 border-t border-[var(--border-subtle)] space-y-3 bg-[var(--bg-canvas)]">
          {/* Real Citations */}
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
                    className="w-full text-left p-2 rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--color-accent)] transition-colors flex items-start gap-2"
                  >
                    <FileText className="w-3.5 h-3.5 text-[var(--color-accent)] shrink-0 mt-0.5" />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between font-mono-data text-[10.5px] text-[var(--text-secondary)] mb-0.5">
                        <span className="font-semibold">{c.source_file}</span>
                        <span className="text-[var(--color-accent)] font-semibold">Page {c.page}</span>
                      </div>
                      <p className="text-xs text-[var(--text-primary)] line-clamp-2 leading-relaxed">
                        {c.highlighted_text}
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
                Answer Claim Support ({citationCheck.supported_claims}/{citationCheck.total_claims} verified)
              </p>
              <div className="space-y-1">
                {citationCheck.claims.map((claim, idx) => (
                  <div
                    key={idx}
                    className="p-2 rounded bg-[var(--bg-surface)] border border-[var(--border-subtle)] text-xs flex items-start gap-2"
                  >
                    {claim.is_supported ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500 shrink-0 mt-0.5" />
                    ) : (
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-500 shrink-0 mt-0.5" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="text-[var(--text-primary)] leading-normal">{claim.claim}</p>
                      <div className="flex items-center gap-2 mt-1 text-[10px] font-mono-data text-[var(--text-muted)]">
                        <span>Overlap: {Math.round(claim.overlap_score * 100)}%</span>
                        {claim.matched_page && <span>• Best match on Page {claim.matched_page}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
