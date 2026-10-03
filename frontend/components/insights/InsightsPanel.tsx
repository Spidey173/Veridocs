"use client";

import { motion } from "framer-motion";
import {
  Brain,
  Users,
  MapPin,
  Calendar,
  DollarSign,
  Building2,
  TrendingUp,
  AlertTriangle,
  CheckCircle2,
  Lightbulb,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { useState } from "react";
import { useAppStore } from "@/lib/store";
import type { InsightsResponse } from "@/lib/api";

const ENTITY_ICONS: Record<string, React.ReactNode> = {
  PERSON: <Users className="w-3.5 h-3.5" />,
  ORGANIZATION: <Building2 className="w-3.5 h-3.5" />,
  LOCATION: <MapPin className="w-3.5 h-3.5" />,
  DATE: <Calendar className="w-3.5 h-3.5" />,
  MONEY: <DollarSign className="w-3.5 h-3.5" />,
  PERCENTAGE: <TrendingUp className="w-3.5 h-3.5" />,
};

const ENTITY_COLORS: Record<string, string> = {
  PERSON: "text-blue-400 bg-blue-400/10 border-blue-400/20",
  ORGANIZATION: "text-purple-400 bg-purple-400/10 border-purple-400/20",
  LOCATION: "text-emerald-400 bg-emerald-400/10 border-emerald-400/20",
  DATE: "text-amber-400 bg-amber-400/10 border-amber-400/20",
  MONEY: "text-green-400 bg-green-400/10 border-green-400/20",
  PERCENTAGE: "text-cyan-400 bg-cyan-400/10 border-cyan-400/20",
};

export default function InsightsPanel() {
  const { insights, isLoadingInsights } = useAppStore();

  if (isLoadingInsights) {
    return (
      <div className="p-4 space-y-6 overflow-y-auto h-full animate-fade-in-up">
        {/* Executive Summary Card Skeleton */}
        <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-5 space-y-4 relative overflow-hidden backdrop-blur-md">
          <div className="flex items-center gap-2">
            <Brain className="w-5 h-5 text-accent-primary animate-pulse" />
            <div className="animate-shimmer h-5 w-40 rounded-lg" />
          </div>
          <div className="space-y-3 pt-2">
            <div className="animate-shimmer h-3.5 w-full rounded-md" />
            <div className="animate-shimmer h-3.5 w-11/12 rounded-md" />
            <div className="animate-shimmer h-3.5 w-4/5 rounded-md" />
          </div>
          
          <div className="space-y-4 pt-4 border-t border-white/5">
            <div className="flex items-start gap-3">
              <div className="animate-shimmer w-2 h-2 rounded-full mt-1.5 bg-white/20 shrink-0" />
              <div className="space-y-1.5 flex-1">
                <div className="animate-shimmer h-3 w-full rounded-md" />
                <div className="animate-shimmer h-3 w-3/4 rounded-md" />
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="animate-shimmer w-2 h-2 rounded-full mt-1.5 bg-white/20 shrink-0" />
              <div className="space-y-1.5 flex-1">
                <div className="animate-shimmer h-3 w-11/12 rounded-md" />
                <div className="animate-shimmer h-3 w-4/5 rounded-md" />
              </div>
            </div>
          </div>
        </div>

        {/* Key Entities Skeleton */}
        <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-5 space-y-4 relative overflow-hidden backdrop-blur-md">
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5 text-white/30" />
            <div className="animate-shimmer h-5 w-32 rounded-lg" />
          </div>
          <div className="flex flex-wrap gap-2 pt-2">
            <div className="animate-shimmer h-7 w-20 rounded-full border border-white/5 animate-pulse" />
            <div className="animate-shimmer h-7 w-28 rounded-full border border-white/5 animate-pulse" />
            <div className="animate-shimmer h-7 w-24 rounded-full border border-white/5 animate-pulse" />
            <div className="animate-shimmer h-7 w-32 rounded-full border border-white/5 animate-pulse" />
            <div className="animate-shimmer h-7 w-16 rounded-full border border-white/5 animate-pulse" />
            <div className="animate-shimmer h-7 w-26 rounded-full border border-white/5 animate-pulse" />
          </div>
        </div>

        {/* Document Metrics Card Skeleton */}
        <div className="bg-white/[0.02] border border-white/5 rounded-2xl p-4 flex justify-between gap-4 backdrop-blur-md">
          <div className="flex-1 space-y-2">
            <div className="animate-shimmer h-3 w-12 rounded bg-white/10" />
            <div className="animate-shimmer h-6 w-8 rounded-lg bg-white/10" />
          </div>
          <div className="w-px bg-white/5 h-10 self-center" />
          <div className="flex-1 space-y-2">
            <div className="animate-shimmer h-3 w-16 rounded bg-white/10" />
            <div className="animate-shimmer h-6 w-10 rounded-lg bg-white/10" />
          </div>
          <div className="w-px bg-white/5 h-10 self-center" />
          <div className="flex-1 space-y-2">
            <div className="animate-shimmer h-3 w-14 rounded bg-white/10" />
            <div className="animate-shimmer h-6 w-12 rounded-lg bg-white/10" />
          </div>
        </div>
      </div>
    );
  }

  if (!insights) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center p-6">
        <Brain className="w-10 h-10 text-text-muted mb-3 opacity-50" />
        <p className="text-sm text-text-muted">
          Upload a document to see AI-generated insights
        </p>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-5 overflow-y-auto h-full">
      {/* Executive Summary */}
      {insights.executive_summary && (
        <SummarySection summary={insights.executive_summary} />
      )}

      {/* Key Entities */}
      {insights.key_entities && insights.key_entities.length > 0 && (
        <EntitiesSection entities={insights.key_entities} />
      )}

      {/* Document Stats */}
      <StatsSection insights={insights} />
    </div>
  );
}

// ──────────────────────────────────────
// Executive Summary
// ──────────────────────────────────────

function SummarySection({
  summary,
}: {
  summary: NonNullable<InsightsResponse["executive_summary"]>;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass rounded-xl overflow-hidden"
    >
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center justify-between p-3 hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-accent-primary/10">
            <Brain className="w-4 h-4 text-accent-primary" />
          </div>
          <h3 className="text-sm font-semibold text-text-primary">
            Executive Summary
          </h3>
        </div>
        {expanded ? (
          <ChevronUp className="w-4 h-4 text-text-muted" />
        ) : (
          <ChevronDown className="w-4 h-4 text-text-muted" />
        )}
      </button>

      {expanded && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: "auto", opacity: 1 }}
          className="px-3 pb-3 space-y-3"
        >
          {/* Purpose */}
          <p className="text-sm text-text-secondary leading-relaxed">
            {summary.purpose}
          </p>

          {/* Key Findings */}
          {summary.key_findings && summary.key_findings.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Lightbulb className="w-3.5 h-3.5 text-amber-400" />
                <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
                  Key Findings
                </span>
              </div>
              <ul className="space-y-1.5">
                {summary.key_findings.map((finding, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm text-text-secondary"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5 text-accent-primary shrink-0 mt-0.5" />
                    <span>{finding}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Risks */}
          {summary.risks && summary.risks.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <AlertTriangle className="w-3.5 h-3.5 text-warning" />
                <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
                  Risks & Concerns
                </span>
              </div>
              <ul className="space-y-1.5">
                {summary.risks.map((risk, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm text-text-secondary"
                  >
                    <AlertTriangle className="w-3.5 h-3.5 text-warning shrink-0 mt-0.5" />
                    <span>{risk}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Conclusions */}
          {summary.conclusions && summary.conclusions.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-success" />
                <span className="text-xs font-medium text-text-muted uppercase tracking-wider">
                  Conclusions
                </span>
              </div>
              <ul className="space-y-1.5">
                {summary.conclusions.map((conclusion, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-sm text-text-secondary"
                  >
                    <span className="w-1 h-1 rounded-full bg-accent-primary mt-2 shrink-0" />
                    <span>{conclusion}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </motion.div>
      )}
    </motion.div>
  );
}

// ──────────────────────────────────────
// Key Entities
// ──────────────────────────────────────

function EntitiesSection({
  entities,
}: {
  entities: InsightsResponse["key_entities"];
}) {
  const [showAll, setShowAll] = useState(false);
  const displayEntities = showAll ? entities : entities.slice(0, 12);

  // Group by type
  const grouped = displayEntities.reduce(
    (acc, entity) => {
      if (!acc[entity.entity_type]) acc[entity.entity_type] = [];
      acc[entity.entity_type].push(entity);
      return acc;
    },
    {} as Record<string, typeof entities>
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="glass rounded-xl p-3"
    >
      <div className="flex items-center gap-2 mb-3">
        <div className="p-1.5 rounded-lg bg-purple-500/10">
          <Users className="w-4 h-4 text-purple-400" />
        </div>
        <h3 className="text-sm font-semibold text-text-primary">
          Key Entities
        </h3>
        <span className="text-xs text-text-muted ml-auto">
          {entities.length} found
        </span>
      </div>

      <div className="space-y-3">
        {Object.entries(grouped).map(([type, items]) => (
          <div key={type}>
            <p className="text-[10px] font-medium text-text-muted uppercase tracking-wider mb-1.5">
              {type.replace("_", " ")}
            </p>
            <div className="flex flex-wrap gap-1.5">
              {items.map((entity, i) => (
                <span
                  key={i}
                  className={`
                    inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs
                    border transition-colors
                    ${ENTITY_COLORS[type] || "text-text-secondary bg-white/5 border-white/10"}
                  `}
                >
                  {ENTITY_ICONS[type]}
                  {entity.value}
                  {entity.count > 1 && (
                    <span className="opacity-50">×{entity.count}</span>
                  )}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>

      {entities.length > 12 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="mt-3 text-xs text-accent-secondary hover:text-accent-primary transition-colors"
        >
          {showAll ? "Show less" : `Show all ${entities.length} entities`}
        </button>
      )}
    </motion.div>
  );
}

// ──────────────────────────────────────
// Document Stats
// ──────────────────────────────────────

function StatsSection({ insights }: { insights: InsightsResponse }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="glass rounded-xl p-3"
    >
      <h3 className="text-sm font-semibold text-text-primary mb-3">
        Document Statistics
      </h3>
      <div className="grid grid-cols-2 gap-2">
        {[
          {
            label: "Pages",
            value: insights.total_pages || "—",
          },
          {
            label: "Chunks",
            value: insights.total_chunks,
          },
          {
            label: "Entities",
            value: insights.key_entities?.length || 0,
          },
          {
            label: "Analysis",
            value: insights.processing_time_ms
              ? `${(insights.processing_time_ms / 1000).toFixed(1)}s`
              : "—",
          },
        ].map((stat) => (
          <div
            key={stat.label}
            className="p-2.5 rounded-lg bg-white/[0.02] border border-white/5"
          >
            <p className="text-lg font-bold text-text-primary">{stat.value}</p>
            <p className="text-[10px] text-text-muted uppercase tracking-wider">
              {stat.label}
            </p>
          </div>
        ))}
      </div>
    </motion.div>
  );
}
