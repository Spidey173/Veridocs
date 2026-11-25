"use client";

import { useState } from "react";
import { useAppStore } from "@/lib/store";
import { Tag, ExternalLink, Filter, DollarSign, Calendar, Building, User, FileText, Scale } from "lucide-react";
import type { EntityItem } from "@/lib/api";

const LABEL_ICONS: Record<string, any> = {
  money: DollarSign,
  date: Calendar,
  organization: Building,
  person: User,
  jurisdiction: Scale,
  party: Tag,
  term: FileText,
};

export default function EntitiesViewer({ entities }: { entities: EntityItem[] }) {
  const [selectedLabel, setSelectedLabel] = useState<string>("all");
  const { setCurrentPage } = useAppStore();

  const labels = Array.from(new Set(entities.map((e) => e.label.toLowerCase())));
  const filtered = selectedLabel === "all"
    ? entities
    : entities.filter((e) => e.label.toLowerCase() === selectedLabel);

  const handleEntityClick = (page: number) => {
    setCurrentPage(page);
  };

  if (!entities || entities.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-center text-muted-foreground">
        <Tag className="w-10 h-10 mb-2 opacity-40" />
        <p className="text-sm font-medium">No entities extracted yet</p>
        <p className="text-xs text-muted-foreground mt-1">
          Entities are automatically discovered when documents are processed.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 p-3">
      {/* Label Filter Pills */}
      <div className="flex flex-wrap gap-1.5 items-center pb-2 border-b border-border/50">
        <button
          onClick={() => setSelectedLabel("all")}
          className={`px-2 py-0.5 text-xs rounded-full transition-colors flex items-center gap-1 ${
            selectedLabel === "all"
              ? "bg-primary text-primary-foreground font-semibold"
              : "bg-muted text-muted-foreground hover:bg-muted/80"
          }`}
        >
          <Filter className="w-3 h-3" />
          All ({entities.length})
        </button>
        {labels.map((lbl) => {
          const count = entities.filter((e) => e.label.toLowerCase() === lbl).length;
          const IconComponent = LABEL_ICONS[lbl] || Tag;
          return (
            <button
              key={lbl}
              onClick={() => setSelectedLabel(lbl)}
              className={`px-2 py-0.5 text-xs rounded-full transition-colors flex items-center gap-1 capitalize ${
                selectedLabel === lbl
                  ? "bg-primary text-primary-foreground font-semibold"
                  : "bg-muted text-muted-foreground hover:bg-muted/80"
              }`}
            >
              <IconComponent className="w-3 h-3" />
              {lbl} ({count})
            </button>
          );
        })}
      </div>

      {/* Entity Cards List */}
      <div className="space-y-2">
        {filtered.map((ent, idx) => {
          const Icon = LABEL_ICONS[ent.label.toLowerCase()] || Tag;
          const normStr = typeof ent.normalized === "object" && ent.normalized !== null
            ? (ent.normalized.amount !== undefined ? `${ent.normalized.currency} ${ent.normalized.amount}` : JSON.stringify(ent.normalized))
            : (ent.normalized || "");

          return (
            <div
              key={`${ent.id || idx}-${ent.text}`}
              onClick={() => handleEntityClick(ent.page_number)}
              className="p-2.5 rounded-lg border border-border bg-card/50 hover:bg-muted/50 cursor-pointer transition-all hover:border-primary/40 group text-left"
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-1.5 min-w-0">
                  <span className="p-1 rounded bg-muted text-muted-foreground group-hover:text-primary transition-colors">
                    <Icon className="w-3.5 h-3.5" />
                  </span>
                  <span className="text-sm font-medium text-foreground truncate">
                    {ent.text}
                  </span>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  <span className="text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded bg-primary/10 text-primary">
                    {ent.label}
                  </span>
                  <span className="text-[10px] text-muted-foreground flex items-center gap-0.5">
                    P.{ent.page_number}
                    <ExternalLink className="w-2.5 h-2.5 opacity-60 group-hover:opacity-100" />
                  </span>
                </div>
              </div>

              {normStr && (
                <div className="mt-1 text-xs text-muted-foreground pl-6">
                  <span className="text-foreground/70 font-mono text-[11px] bg-muted/60 px-1 py-0.5 rounded">
                    {normStr}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

