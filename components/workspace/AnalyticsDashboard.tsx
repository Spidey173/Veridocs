"use client";

import { useEffect, useState } from "react";
import {
  BarChart3,
  FileText,
  CheckCircle2,
  MessageSquare,
  ShieldAlert,
  ShieldCheck,
  X,
  Loader2,
  RefreshCw,
} from "lucide-react";
import { fetchAnalytics, type AnalyticsResult } from "@/lib/api";

interface AnalyticsDashboardProps {
  isOpen: boolean;
  onClose: () => void;
}

export default function AnalyticsDashboard({ isOpen, onClose }: AnalyticsDashboardProps) {
  const [data, setData] = useState<AnalyticsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetchAnalytics();
      setData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load analytics");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      load();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const days = data?.by_day || [];
  const maxActivity = Math.max(
    1,
    ...days.map((d) => Math.max(d.documents_uploaded, d.questions_asked, d.flags_found))
  );

  return (
    <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="w-full max-w-3xl bg-[var(--bg-surface)] border border-[var(--border-default)] rounded-xl shadow-2xl overflow-hidden flex flex-col max-h-[88vh]">
        {/* Header */}
        <div className="px-4 py-3 border-b border-[var(--border-subtle)] flex items-center justify-between bg-[var(--bg-canvas)]">
          <div className="flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-[var(--color-accent)]" />
            <h2 className="text-sm font-semibold text-[var(--text-primary)]">
              Workspace Analytics Dashboard
            </h2>
          </div>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
              title="Refresh analytics"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            </button>
            <button
              type="button"
              onClick={onClose}
              className="p-1.5 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
              title="Close dashboard"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="p-4 overflow-y-auto space-y-5 text-xs">
          {error && (
            <div className="p-2.5 rounded bg-rose-500/10 border border-rose-500/20 text-rose-500">
              {error}
            </div>
          )}

          {loading && !data ? (
            <div className="py-12 flex items-center justify-center gap-2 text-[var(--text-muted)]">
              <Loader2 className="w-5 h-5 animate-spin text-[var(--color-accent)]" />
              <span>Loading workspace metrics...</span>
            </div>
          ) : data ? (
            <>
              {/* Metric Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
                <div className="p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1">
                  <div className="flex items-center gap-1.5 text-[var(--text-muted)] text-[10.5px] font-mono-data">
                    <FileText className="w-3.5 h-3.5 text-[var(--color-accent)]" />
                    <span>Uploaded</span>
                  </div>
                  <p className="text-xl font-bold text-[var(--text-primary)] font-mono-data">
                    {data.documents_uploaded}
                  </p>
                </div>

                <div className="p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1">
                  <div className="flex items-center gap-1.5 text-[var(--text-muted)] text-[10.5px] font-mono-data">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                    <span>Analyzed</span>
                  </div>
                  <p className="text-xl font-bold text-[var(--text-primary)] font-mono-data">
                    {data.documents_analyzed}
                  </p>
                </div>

                <div className="p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1">
                  <div className="flex items-center gap-1.5 text-[var(--text-muted)] text-[10.5px] font-mono-data">
                    <MessageSquare className="w-3.5 h-3.5 text-blue-400" />
                    <span>Questions</span>
                  </div>
                  <p className="text-xl font-bold text-[var(--text-primary)] font-mono-data">
                    {data.questions_asked}
                  </p>
                </div>

                <div className="p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1">
                  <div className="flex items-center gap-1.5 text-[var(--text-muted)] text-[10.5px] font-mono-data">
                    <ShieldAlert className="w-3.5 h-3.5 text-amber-500" />
                    <span>Flags</span>
                  </div>
                  <p className="text-xl font-bold text-[var(--text-primary)] font-mono-data">
                    {data.flags_found}
                  </p>
                </div>

                <div className="p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-1 col-span-2 sm:col-span-1">
                  <div className="flex items-center gap-1.5 text-[var(--text-muted)] text-[10.5px] font-mono-data">
                    <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
                    <span>Avg Verify</span>
                  </div>
                  <p className="text-xl font-bold text-emerald-500 font-mono-data">
                    {Math.round((data.avg_verification_score ?? 0) * 100)}%
                  </p>
                </div>
              </div>

              {/* Daily Activity Chart */}
              <div className="p-3.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-canvas)] space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-semibold text-[var(--text-primary)]">
                    Daily Activity Breakdown
                  </h3>
                  <div className="flex items-center gap-3 text-[10px] font-mono-data text-[var(--text-muted)]">
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-sm bg-[var(--color-accent)]" /> Docs
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-sm bg-blue-400" /> Questions
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="w-2 h-2 rounded-sm bg-amber-500" /> Flags
                    </span>
                  </div>
                </div>

                {days.length === 0 ? (
                  <p className="text-center py-6 text-[var(--text-muted)]">
                    No activity recorded yet. Upload documents or ask questions to populate metrics.
                  </p>
                ) : (
                  <div className="space-y-2.5">
                    {days.slice(-14).map((d) => (
                      <div key={d.date} className="space-y-1">
                        <div className="flex items-center justify-between text-[10.5px] font-mono-data text-[var(--text-secondary)]">
                          <span>{d.date}</span>
                          <span>
                            {d.documents_uploaded} docs · {d.questions_asked} Qs · {d.flags_found} flags
                            {d.avg_verification_score !== null && d.avg_verification_score !== undefined
                              ? ` · ${Math.round(d.avg_verification_score * 100)}% verified`
                              : ""}
                          </span>
                        </div>
                        <div className="space-y-1">
                          <div className="h-1.5 w-full rounded bg-[var(--bg-subtle)] overflow-hidden">
                            <div
                              className="h-full bg-[var(--color-accent)] rounded"
                              style={{ width: `${Math.round((d.documents_uploaded / maxActivity) * 100)}%` }}
                            />
                          </div>
                          <div className="h-1.5 w-full rounded bg-[var(--bg-subtle)] overflow-hidden">
                            <div
                              className="h-full bg-blue-400 rounded"
                              style={{ width: `${Math.round((d.questions_asked / maxActivity) * 100)}%` }}
                            />
                          </div>
                          <div className="h-1.5 w-full rounded bg-[var(--bg-subtle)] overflow-hidden">
                            <div
                              className="h-full bg-amber-500 rounded"
                              style={{ width: `${Math.round((d.flags_found / maxActivity) * 100)}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}

