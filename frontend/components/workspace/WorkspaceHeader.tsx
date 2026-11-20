"use client";

import { useAppStore } from "@/lib/store";
import {
  Plus,
  PanelLeftClose,
  PanelLeft,
  PanelRightClose,
  PanelRight,
  FileText,
  Keyboard,
} from "lucide-react";

export default function WorkspaceHeader() {
  const {
    sessionId,
    selectedFileNames,
    activeDocumentName,
    currentPage,
    totalPages,
    leftSidebarCollapsed,
    rightSidebarCollapsed,
    setLeftSidebarCollapsed,
    setRightSidebarCollapsed,
    clearSession,
  } = useAppStore();

  return (
    <header className="h-11 px-3.5 flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-primary)] shrink-0 z-40 select-none">
      <div className="flex items-center gap-2.5">
        {/* Toggle Left Sidebar */}
        {sessionId && (
          <button
            type="button"
            onClick={() => setLeftSidebarCollapsed(!leftSidebarCollapsed)}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
            title={leftSidebarCollapsed ? "Expand Documents & Insights (Cmd+B)" : "Collapse Sidebar"}
          >
            {leftSidebarCollapsed ? (
              <PanelLeft className="w-4 h-4 text-[var(--color-accent)]" />
            ) : (
              <PanelLeftClose className="w-4 h-4" />
            )}
          </button>
        )}

        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-[var(--color-accent)] flex items-center justify-center text-white font-bold text-[10px] font-mono-data">
            V
          </div>
          <span className="text-xs font-serif-doc font-semibold tracking-tight text-[var(--text-primary)]">
            Veridocs
          </span>
        </div>

        {/* Active Document Breadcrumb */}
        {sessionId && (
          <div className="hidden sm:flex items-center gap-2 pl-3 ml-1 border-l border-[var(--border-subtle)] text-xs">
            <span className="text-[10px] font-mono-data px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] text-[var(--text-muted)] border border-[var(--border-subtle)]">
              {selectedFileNames.length} {selectedFileNames.length === 1 ? "doc" : "docs"}
            </span>

            {activeDocumentName && (
              <div className="flex items-center gap-1.5 text-[var(--text-secondary)] font-medium truncate max-w-[280px]">
                <FileText className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
                <span className="truncate">{activeDocumentName}</span>
                {totalPages > 0 && (
                  <span className="text-[10px] text-[var(--text-muted)] font-mono-data shrink-0">
                    (p. {currentPage}/{totalPages})
                  </span>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        {/* Keyboard navigation quick hints */}
        <div className="hidden lg:flex items-center gap-2 text-[10px] text-[var(--text-muted)] font-mono-data pr-2 border-r border-[var(--border-subtle)]">
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)]">⌘K</kbd>
            <span>Ask</span>
          </span>
          <span className="flex items-center gap-1">
            <kbd className="px-1 py-0.5 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)]">J</kbd>
            <kbd className="px-1 py-0.5 rounded bg-[var(--bg-subtle)] border border-[var(--border-subtle)]">K</kbd>
            <span>Citations</span>
          </span>
        </div>

        {sessionId && (
          <button
            type="button"
            onClick={clearSession}
            className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] border border-transparent hover:border-[var(--border-subtle)] transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>New Workspace</span>
          </button>
        )}

        {/* Toggle Right Sidebar */}
        {sessionId && (
          <button
            type="button"
            onClick={() => setRightSidebarCollapsed(!rightSidebarCollapsed)}
            className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
            title={rightSidebarCollapsed ? "Expand Answers & Evidence" : "Collapse Right Panel"}
          >
            {rightSidebarCollapsed ? (
              <PanelRight className="w-4 h-4 text-[var(--color-accent)]" />
            ) : (
              <PanelRightClose className="w-4 h-4" />
            )}
          </button>
        )}
      </div>
    </header>
  );
}
