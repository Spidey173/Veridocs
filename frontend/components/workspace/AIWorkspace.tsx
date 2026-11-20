"use client";

import { useAppStore } from "@/lib/store";
import { MessageSquare, Scale } from "lucide-react";
import ChatPanel from "../chat/ChatPanel";
import ContradictionMatrix from "../audit/ContradictionMatrix";

export default function AIWorkspace() {
  const {
    activeWorkspaceTab,
    files,
    activeDiffReport,
    setActiveWorkspaceTab,
  } = useAppStore();

  const conflictCount = activeDiffReport?.conflicts?.length || 0;

  return (
    <div className="w-full h-full flex flex-col bg-[var(--bg-surface)] border-l border-[var(--border-subtle)] overflow-hidden select-none">
      {/* Top Tab Switcher: Dense, Tabular, High-Contrast */}
      <div className="h-10 px-3 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] flex items-center justify-between shrink-0">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setActiveWorkspaceTab("chat")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors ${
              activeWorkspaceTab === "chat"
                ? "bg-[var(--bg-subtle)] text-[var(--text-primary)] font-semibold border border-[var(--border-subtle)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-surface-raised)]"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 text-[var(--color-accent)]" />
            <span>Chat & Evidence</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveWorkspaceTab("contradictions")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium transition-colors relative ${
              activeWorkspaceTab === "contradictions"
                ? "bg-[var(--bg-subtle)] text-[var(--text-primary)] font-semibold border border-[var(--border-subtle)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)] hover:bg-[var(--bg-surface-raised)]"
            }`}
          >
            <Scale className="w-3.5 h-3.5 text-[var(--text-muted)]" />
            <span>Contradiction Matrix</span>
            {conflictCount > 0 && (
              <span className="text-[10px] font-mono-data px-1 py-0.2 rounded bg-[var(--color-accent-subtle)] text-[var(--color-accent)] border border-[var(--color-accent-border)] font-bold">
                {conflictCount}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Tab Panels */}
      <div className="flex-1 overflow-hidden">
        {activeWorkspaceTab === "chat" ? (
          <ChatPanel />
        ) : (
          <ContradictionMatrix />
        )}
      </div>
    </div>
  );
}
