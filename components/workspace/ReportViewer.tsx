"use client";

import { useEffect, useState } from "react";
import {
  FileBarChart,
  Download,
  Loader2,
  RefreshCw,
  AlertTriangle,
  CheckCircle2,
  Lightbulb,
  ExternalLink,
} from "lucide-react";
import {
  fetchDocumentReport,
  generateDocumentReport,
  getReportExportUrl,
  type ReportFinding,
} from "@/lib/api";
import { useAppStore } from "@/lib/store";

interface ReportViewerProps {
  documentId: string;
}

export default function ReportViewer({ documentId }: ReportViewerProps) {
  const { documentReports, setDocumentReport, setCurrentPage } = useAppStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const report = documentId ? documentReports[documentId] : undefined;

  useEffect(() => {
    if (!documentId || report) return;
    let cancelled = false;
    fetchDocumentReport(documentId)
      .then((res) => {
        if (!cancelled && res) {
          setDocumentReport(documentId, res);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [documentId, report, setDocumentReport]);

  const handleGenerate = async () => {
    if (!documentId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await generateDocumentReport(documentId);
      setDocumentReport(documentId, res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate report");
    } finally {
      setLoading(false);
    }
  };

  if (!documentId) {
    return (
      <div className="p-6 text-center text-xs text-[var(--text-muted)]">
        Select a document to generate an executive report and export as MD, PDF, or DOCX.
      </div>
    );
  }

  const renderFindingList = (items: ReportFinding[], emptyMsg: string, accent: "blue" | "amber" | "emerald") => {
    if (!items || items.length === 0) {
      return <p className="text-[11px] text-[var(--text-muted)] italic">{emptyMsg}</p>;
    }
    return (
      <div className="space-y-2">
        {items.map((item, idx) => (
          <div
            key={idx}
            className="p-2.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1.5"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-[var(--text-primary)]">{item.title}</span>
              {item.severity && (
                <span
                  className={`px-1.5 py-0.2 rounded text-[9.5px] font-mono-data uppercase font-semibold border ${
                    item.severity === "high"
                      ? "bg-rose-500/10 text-rose-500 border-rose-500/20"
                      : item.severity === "medium"
                      ? "bg-amber-500/10 text-amber-500 border-amber-500/20"
                      : "bg-emerald-500/10 text-emerald-500 border-emerald-500/20"
                  }`}
                >
                  {item.severity}
                </span>
              )}
            </div>
            <p className="text-[var(--text-secondary)] leading-relaxed">{item.detail}</p>
            {item.citations && item.citations.length > 0 && (
              <div className="flex flex-wrap gap-1.5 pt-0.5">
                {item.citations.map((c, cIdx) => (
                  <button
                    key={cIdx}
                    type="button"
                    onClick={() => setCurrentPage(c.page)}
                    className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-mono-data border transition-colors ${
                      accent === "amber"
                        ? "bg-amber-500/10 text-amber-500 border-amber-500/20 hover:bg-amber-500/20"
                        : accent === "emerald"
                        ? "bg-emerald-500/10 text-emerald-500 border-emerald-500/20 hover:bg-emerald-500/20"
                        : "bg-[var(--color-accent-subtle)] text-[var(--color-accent)] border-[var(--color-accent-border)] hover:bg-[var(--color-accent)] hover:text-white"
                    }`}
                    title={c.quote}
                  >
                    <span>
                      {c.section_path ? `${c.section_path} · ` : ""}p.{c.page}
                    </span>
                    <ExternalLink className="w-2.5 h-2.5" />
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    );
  };

  return (
    <div className="p-3 space-y-3 text-xs">
      {/* Header & Actions */}
      <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-[var(--border-subtle)]">
        <div className="flex items-center gap-1.5">
          <FileBarChart className="w-3.5 h-3.5 text-[var(--color-accent)]" />
          <span className="font-semibold text-[var(--text-primary)]">Executive Report</span>
        </div>

        <button
          type="button"
          onClick={handleGenerate}
          disabled={loading}
          className="inline-flex items-center gap-1 px-2 py-1 rounded bg-[var(--color-accent)] text-white text-[11px] font-medium hover:bg-[var(--color-accent-hover)] disabled:opacity-50 transition-colors"
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          <span>{report ? "Regenerate" : "Generate Report"}</span>
        </button>
      </div>

      {/* Export Buttons */}
      {report && (
        <div className="flex flex-wrap items-center gap-1.5 bg-[var(--bg-canvas)] p-2 rounded border border-[var(--border-subtle)]">
          <span className="text-[10.5px] font-mono-data text-[var(--text-muted)] mr-1">Export:</span>
          {(["md", "pdf", "docx"] as const).map((fmt) => (
            <a
              key={fmt}
              href={getReportExportUrl(documentId, fmt)}
              download
              className="inline-flex items-center gap-1 px-2 py-1 rounded text-[10.5px] font-mono-data font-medium bg-[var(--bg-surface)] border border-[var(--border-subtle)] hover:border-[var(--color-accent)] text-[var(--text-primary)] transition-colors"
            >
              <Download className="w-3 h-3 text-[var(--color-accent)]" />
              <span>.{fmt.toUpperCase()}</span>
            </a>
          ))}
        </div>
      )}

      {error && (
        <div className="p-2 rounded bg-rose-500/10 border border-rose-500/20 text-rose-500 text-[11px]">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-10 flex flex-col items-center justify-center gap-2 text-[var(--text-muted)]">
          <Loader2 className="w-5 h-5 animate-spin text-[var(--color-accent)]" />
          <span>Synthesizing cited report...</span>
        </div>
      ) : report ? (
        <div className="space-y-4">
          <div className="p-2.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1">
            <h4 className="text-[10.5px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] font-semibold">
              Executive Summary
            </h4>
            <p className="text-[var(--text-primary)] leading-relaxed">{report.executive_summary}</p>
          </div>

          <div className="space-y-1.5">
            <h4 className="flex items-center gap-1 text-[10.5px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] font-semibold">
              <CheckCircle2 className="w-3 h-3 text-emerald-500" />
              <span>Important Findings ({report.important_findings.length})</span>
            </h4>
            {renderFindingList(report.important_findings, "No key findings extracted.", "blue")}
          </div>

          <div className="space-y-1.5">
            <h4 className="flex items-center gap-1 text-[10.5px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] font-semibold">
              <AlertTriangle className="w-3 h-3 text-amber-500" />
              <span>Risks &amp; Anomaly Signals ({report.risks.length})</span>
            </h4>
            {renderFindingList(report.risks, "No risk clauses or anomaly flags detected.", "amber")}
          </div>

          <div className="space-y-1.5">
            <h4 className="flex items-center gap-1 text-[10.5px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] font-semibold">
              <Lightbulb className="w-3 h-3 text-[var(--color-accent)]" />
              <span>Recommendations ({report.recommendations.length})</span>
            </h4>
            {renderFindingList(report.recommendations, "No recommendations generated.", "emerald")}
          </div>
        </div>
      ) : (
        <div className="py-8 text-center space-y-2 text-[var(--text-muted)]">
          <FileBarChart className="w-8 h-8 mx-auto opacity-40" />
          <p className="font-medium text-[var(--text-primary)]">No Report Generated Yet</p>
          <p className="text-[11px]">
            Click &ldquo;Generate Report&rdquo; to combine summary, entities, flags, and risk citations.
          </p>
        </div>
      )}
    </div>
  );
}

