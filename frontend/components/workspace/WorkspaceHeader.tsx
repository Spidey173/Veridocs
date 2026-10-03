"use client";

import { useAppStore } from "@/lib/store";
import {
  Sparkles,
  Columns,
  FolderOpen,
  Plus,
  PanelLeftClose,
  PanelLeft,
  PanelRightClose,
  PanelRight,
} from "lucide-react";
import { motion } from "framer-motion";

export default function WorkspaceHeader() {
  const {
    sessionId,
    files,
    selectedFileNames,
    activeDocumentName,
    leftSidebarCollapsed,
    rightSidebarCollapsed,
    setLeftSidebarCollapsed,
    setRightSidebarCollapsed,
    clearSession,
  } = useAppStore();

  return (
    <>
      <header className="h-14 px-5 flex items-center justify-between border-b border-white/5 bg-midnight-900/80 backdrop-blur-md z-50">
        <div className="flex items-center gap-3">
          {/* Toggle Left Sidebar */}
          {sessionId && (
            <button
              onClick={() => setLeftSidebarCollapsed(!leftSidebarCollapsed)}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-white/5 transition-all"
              title={leftSidebarCollapsed ? "Expand Sidebar" : "Collapse Sidebar"}
            >
              {leftSidebarCollapsed ? <PanelLeft className="w-4.5 h-4.5 text-accent-primary" /> : <PanelLeftClose className="w-4.5 h-4.5" />}
            </button>
          )}

          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-accent-primary to-amber-500 flex items-center justify-center shadow-lg shadow-accent-primary/10">
              <Sparkles className="w-4 h-4 text-midnight-950 font-bold" />
            </div>
            <h1 className="text-sm font-bold tracking-tight">
              Veridocs
            </h1>
          </div>

          {/* Active document indicator / context details */}
          {sessionId && (
            <div className="hidden md:flex items-center gap-2.5 ml-4 pl-4 border-l border-white/10">
              <div className="flex items-center gap-1.5 bg-accent-soft px-2.5 py-1 rounded-md border border-accent-primary/20">
                <span className="w-1.5 h-1.5 rounded-full bg-accent-primary animate-pulse" />
                <span className="text-[11px] font-semibold text-accent-primary uppercase tracking-wider">
                  {selectedFileNames.length} active
                </span>
              </div>
              {activeDocumentName && (
                <span className="text-xs text-text-muted truncate max-w-[220px]">
                  Viewing: <span className="text-text-secondary font-medium">{activeDocumentName}</span>
                </span>
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-2 sm:gap-3">
          {sessionId && (
            <motion.button
              whileHover={{ scale: 1.02 }}
              whileTap={{ scale: 0.98 }}
              onClick={clearSession}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold
                bg-white/5 hover:bg-white/10 text-text-secondary transition-all"
            >
              <Plus className="w-3.5 h-3.5" />
              New Workspace
            </motion.button>
          )}

          {/* Toggle Right Sidebar */}
          {sessionId && (
            <button
              onClick={() => setRightSidebarCollapsed(!rightSidebarCollapsed)}
              className="p-1.5 rounded-lg text-text-muted hover:text-text-secondary hover:bg-white/5 transition-all"
              title={rightSidebarCollapsed ? "Expand AI Workspace" : "Collapse AI Workspace"}
            >
              {rightSidebarCollapsed ? <PanelRight className="w-4.5 h-4.5 text-accent-primary" /> : <PanelRightClose className="w-4.5 h-4.5" />}
            </button>
          )}
        </div>
      </header>
    </>
  );
}
