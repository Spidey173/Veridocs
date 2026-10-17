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
    <div className="w-full h-full flex flex-col bg-midnight-900 border-l border-white/5 overflow-hidden">
      {/* Top Tab Switcher */}
      <div className="h-11 px-3 border-b border-white/5 bg-midnight-950/80 backdrop-blur-sm flex items-center justify-between shrink-0">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setActiveWorkspaceTab("chat")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeWorkspaceTab === "chat"
                ? "bg-white/10 text-white shadow-sm"
                : "text-text-muted hover:text-text-secondary hover:bg-white/5"
            }`}
          >
            <MessageSquare className="w-3.5 h-3.5 text-accent-primary" />
            Chat & Evidence
          </button>

          <button
            onClick={() => setActiveWorkspaceTab("contradictions")}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all relative ${
              activeWorkspaceTab === "contradictions"
                ? "bg-rose-500/15 text-rose-300 border border-rose-500/30 shadow-sm"
                : "text-text-muted hover:text-text-secondary hover:bg-white/5"
            }`}
          >
            <Scale className="w-3.5 h-3.5 text-rose-400" />
            Contradiction Matrix
            {files.length >= 2 && conflictCount > 0 ? (
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
            ) : files.length >= 2 ? (
              <span className="text-[9px] font-mono px-1 rounded bg-rose-500/20 text-rose-300 font-bold">
                DIFF
              </span>
            ) : null}
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
