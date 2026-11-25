"use client";

import { useEffect, useState, useCallback } from "react";
import {
  Sparkles,
  RefreshCw,
  Loader2,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  HelpCircle,
  ExternalLink,
} from "lucide-react";
import {
  fetchDocumentSummary,
  generateDocumentSummary,
  type DocumentSummaryResult,
  type SummaryClaimVerification,
} from "@/lib/api";
import { useAppStore } from "@/lib/store";

interface SummaryViewerProps {
  documentId: string;
}

export default function SummaryViewer({ documentId }: SummaryViewerProps) {
  const { documentSummaries, setDocumentSummary, setCurrentPage } = useAppStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const summaryState: DocumentSummaryResult | undefined = documentId
    ? documentSummaries[documentId]
    : undefined;

  const pollUntilDone = useCallback(
    async (docId: string) => {
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 700));
        try {
          const res = await fetchDocumentSummary(docId);
          setDocumentSummary(docId, res);
          if (res.status === "ready" || res.status === "failed") {
            return;
          }
        } catch {
          return;
        }
      }
    },
    [setDocumentSummary]
  );

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    setError(null);

    fetchDocumentSummary(documentId)
      .then((res) => {
        if (cancelled) return;
        setDocumentSummary(documentId, res);
        if (res.status === "queued" || res.status === "processing") {
          setLoading(true);
          pollUntilDone(documentId).finally(() => {
            if (!cancelled) setLoading(false);
          });
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "Failed to load summary");
      });

    return () => {
      cancelled = true;
    };
  }, [documentId, setDocumentSummary, pollUntilDone]);

  const handleGenerate = async (force: boolean) => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await generateDocumentSummary(documentId, force);
      setDocumentSummary(documentId, res);
      if (res.status === "queued" || res.status === "processing") {
        await pollUntilDone(documentId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Summary generation failed");
    } finally {
      setLoading(false);
    }
  };

  if (!documentId) {
    return (
      <div className="p-6 text-center text-xs text-[var(--text-muted)]">
        Select a document to view or generate its structured summary.
      </div>
    );
  }

  const isWorking =
    loading ||
    summaryState?.status === "queued" ||
    summaryState?.status === "processing";

  const data = summaryState?.summary;
  const verification = summaryState?.verification;
  const scorePct =
    summaryState?.grounding_score !== null && summaryState?.grounding_score !== undefined
      ? Math.round(summaryState.grounding_score * 100)
      : null;

  const claimsByText = new Map<string, SummaryClaimVerification>();
  for (const cl of verification?.claims || []) {
    claimsByText.set(cl.claim, cl);
  }

  const renderClaimMeta = (text: string) => {
    const cl = claimsByText.get(text);
    if (!cl) return null;
    return (
      <div className="flex flex-wrap items-center gap-1.5 mt-1 text-[10px] font-mono-data text-[var(--text-muted)]">
        {cl.status === "supported" ? (
          <span className="inline-flex items-center gap-0.5 text-emerald-500">
            <CheckCircle2 className="w-2.5 h-2.5" />
            Supported ({Math.round(cl.score * 100)}%)
          </span>
        ) : cl.status === "contradicted" ? (
          <span className="inline-flex items-center gap-0.5 text-rose-500">
            <XCircle className="w-2.5 h-2.5" />
            Contradicted
          </span>
        ) : (
          <span className="inline-flex items-center gap-0.5 text-amber-500">
            <HelpCircle className="w-2.5 h-2.5" />
            Unverified
          </span>
        )}
        {cl.matched_page && (
          <button
            type="button"
            onClick={() => setCurrentPage(cl.matched_page!)}
            className="inline-flex items-center gap-0.5 text-[var(--color-accent)] hover:underline"
          >
            <span>
              {cl.section_path ? `${cl.section_path} · ` : ""}p.{cl.matched_page}
            </span>
            <ExternalLink className="w-2.5 h-2.5" />
          </button>
        )}
      </div>
    );
  };

  return (
    <div className="p-3 space-y-3 text-xs">
      {/* Header Bar */}
      <div className="flex items-center justify-between gap-2 pb-2 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-1.5">
          <Sparkles className="w-3.5 h-3.5 text-[var(--color-accent)]" />
          <span className="font-semibold text-[var(--text-primary)]">Structured Summary</span>
          {scorePct !== null && (
            <span
              className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono-data border ${
                scorePct >= 70
                  ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                  : "bg-amber-500/10 text-amber-500 border-amber-500/20"
              }`}
            >
              <ShieldCheck className="w-2.5 h-2.5" />
              {scorePct}% Grounded
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => handleGenerate(Boolean(data))}
          disabled={isWorking}
          className="inline-flex items-center gap-1 px-2 py-1 rounded bg-[var(--color-accent)] text-white text-[11px] font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
        >
          {isWorking ? (
            <Loader2 className="w-3 h-3 animate-spin" />
          ) : (
            <RefreshCw className="w-3 h-3" />
          )}
          <span>{data ? "Regenerate" : "Generate"}</span>
        </button>
      </div>

      {error && (
        <div className="p-2 rounded bg-rose-500/10 border border-rose-500/20 text-rose-500 text-[11px]">
          {error}
        </div>
      )}

      {summaryState?.status === "failed" && summaryState.error && (
        <div className="p-2 rounded bg-rose-500/10 border border-rose-500/20 text-rose-500 text-[11px]">
          Summary failed: {summaryState.error}
        </div>
      )}

      {isWorking ? (
        <div className="py-10 flex flex-col items-center justify-center gap-2 text-[var(--text-muted)]">
          <Loader2 className="w-5 h-5 animate-spin text-[var(--color-accent)]" />
          <span>Running map-reduce summary & NLI verification...</span>
        </div>
      ) : data ? (
        <div className="space-y-3">
          {/* Main Purpose */}
          <div className="p-2.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1">
            <h4 className="text-[10.5px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] font-semibold">
              Main Purpose
            </h4>
            <p className="text-[var(--text-primary)] leading-relaxed">{data.main_purpose}</p>
            {renderClaimMeta(data.main_purpose)}
          </div>

          {/* Important Points */}
          {data.important_points && data.important_points.length > 0 && (
            <div className="p-2.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1.5">
              <h4 className="text-[10.5px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] font-semibold">
                Important Points
              </h4>
              <ul className="space-y-2 list-disc pl-4">
                {data.important_points.map((pt, idx) => (
                  <li key={idx} className="text-[var(--text-primary)] leading-relaxed">
                    <span>{pt}</span>
                    {renderClaimMeta(pt)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Key Information */}
          {data.key_information && data.key_information.length > 0 && (
            <div className="p-2.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1.5">
              <h4 className="text-[10.5px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] font-semibold">
                Key Information
              </h4>
              <ul className="space-y-2 list-disc pl-4">
                {data.key_information.map((ki, idx) => (
                  <li key={idx} className="text-[var(--text-primary)] leading-relaxed">
                    <span>{ki}</span>
                    {renderClaimMeta(ki)}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Conclusion */}
          {data.conclusion && (
            <div className="p-2.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1">
              <h4 className="text-[10.5px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] font-semibold">
                Conclusion
              </h4>
              <p className="text-[var(--text-primary)] leading-relaxed">{data.conclusion}</p>
              {renderClaimMeta(data.conclusion)}
            </div>
          )}
        </div>
      ) : (
        <div className="py-8 text-center space-y-2 text-[var(--text-muted)]">
          <Sparkles className="w-8 h-8 mx-auto opacity-40" />
          <p className="font-medium text-[var(--text-primary)]">No Summary Generated Yet</p>
          <p className="text-[11px]">
            Click &ldquo;Generate&rdquo; to build a section-ordered summary verified by NLI.
          </p>
        </div>
      )}
    </div>
  );
}

