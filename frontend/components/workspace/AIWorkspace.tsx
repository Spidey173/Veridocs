"use client";

import { useAppStore } from "@/lib/store";
import { MessageSquare, Brain, FileText, Database } from "lucide-react";
import ChatPanel from "../chat/ChatPanel";
import InsightsPanel from "../insights/InsightsPanel";
import { motion } from "framer-motion";

export default function AIWorkspace() {
  const { activePanelTab, setActivePanelTab, files } = useAppStore();

  return (
    <div className="w-full h-full flex flex-col bg-midnight-900 border-l border-white/5 overflow-hidden">
      {/* AI Workspace Tabs */}
      <div className="flex items-center gap-1.5 px-4 py-2 bg-midnight-900 border-b border-white/5 select-none shrink-0 h-12">
        <TabButton
          active={activePanelTab === "chat"}
          onClick={() => setActivePanelTab("chat")}
          icon={<MessageSquare className="w-3.5 h-3.5" />}
          label="Chat"
        />
        <TabButton
          active={activePanelTab === "insights"}
          onClick={() => setActivePanelTab("insights")}
          icon={<Brain className="w-3.5 h-3.5" />}
          label="Insights"
        />
        <TabButton
          active={activePanelTab === "sources"}
          onClick={() => setActivePanelTab("sources")}
          icon={<FileText className="w-3.5 h-3.5" />}
          label="Sources"
        />
      </div>

      {/* Tab Contents */}
      <div className="flex-1 overflow-hidden">
        {activePanelTab === "chat" && <ChatPanel />}
        {activePanelTab === "insights" && <InsightsPanel />}
        {activePanelTab === "sources" && <SourcesTabContent />}
      </div>
    </div>
  );
}

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}

function TabButton({ active, onClick, icon, label }: TabButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`
        relative flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold
        transition-all duration-150 cursor-pointer
        ${
          active
            ? "bg-accent-soft text-accent-primary border border-accent-primary/25"
            : "text-text-muted hover:text-text-secondary hover:bg-white/5 border border-transparent"
        }
      `}
    >
      {icon}
      {label}
    </button>
  );
}

function SourcesTabContent() {
  const { files, selectedFileNames } = useAppStore();

  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full select-none">
      <div className="flex items-center gap-2 mb-2">
        <Database className="w-4.5 h-4.5 text-accent-primary" />
        <h3 className="text-sm font-semibold text-text-primary">
          Indexed Data Sources
        </h3>
      </div>
      <p className="text-xs text-text-secondary leading-relaxed">
        The following files define the current knowledge context for the AI workspace. Deselect files in the Left Sidebar to restrict references.
      </p>

      <div className="space-y-2 pt-2">
        {files.map((file) => {
          const isSelected = selectedFileNames.includes(file.name);
          return (
            <div
              key={file.name}
              className={`
                p-3.5 rounded-xl border flex flex-col gap-1 transition-all
                ${
                  isSelected
                    ? "bg-accent-soft/5 border-accent-primary/15"
                    : "bg-white/[0.01] border-white/5 opacity-50"
                }
              `}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 truncate">
                  <FileText className={`w-4 h-4 ${isSelected ? "text-accent-primary" : "text-text-muted"}`} />
                  <span className="text-xs font-bold text-text-primary truncate">
                    {file.name}
                  </span>
                </div>
                <span className={`text-[9px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wider ${
                  isSelected ? "bg-accent-primary/10 text-accent-primary border border-accent-primary/20" : "bg-white/5 text-text-muted"
                }`}>
                  {isSelected ? "Active Context" : "Inactive"}
                </span>
              </div>
              <div className="flex items-center justify-between text-[10px] text-text-muted font-mono mt-1.5 pt-1.5 border-t border-white/5">
                <span>Vector Embeddings: Active</span>
                <span>{(file.size / 1024).toFixed(1)} KB</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
