"use client";

import { useState } from "react";
import { useAppStore } from "@/lib/store";
import ResizablePanel from "./ResizablePanel";
import FileManager from "./FileManager";
import WorkspaceHeader from "./WorkspaceHeader";
import PDFViewer from "../pdf-viewer/PDFViewer";
import ChatPanel from "../chat/ChatPanel";
import { FileText, Eye, MessageSquare } from "lucide-react";

export default function WorkspaceLayout() {
  const {
    leftSidebarCollapsed,
    rightSidebarCollapsed,
    leftSidebarWidth,
    rightSidebarWidth,
    activeDocumentName,
    setLeftSidebarWidth,
    setRightSidebarWidth,
  } = useAppStore();

  const [mobileTab, setMobileTab] = useState<"left" | "center" | "right">("center");

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* Global Workspace Header */}
      <WorkspaceHeader />

      {/* Mobile Tab Strip (< md) */}
      <div className="md:hidden h-9 px-2 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] flex items-center justify-around text-xs shrink-0 font-mono-data">
        <button
          type="button"
          onClick={() => setMobileTab("left")}
          className={`flex items-center gap-1.5 py-1 px-2.5 rounded ${
            mobileTab === "left"
              ? "bg-[var(--bg-subtle)] font-semibold text-[var(--color-accent)]"
              : "text-[var(--text-muted)]"
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Documents</span>
        </button>
        <button
          type="button"
          onClick={() => setMobileTab("center")}
          className={`flex items-center gap-1.5 py-1 px-2.5 rounded ${
            mobileTab === "center"
              ? "bg-[var(--bg-subtle)] font-semibold text-[var(--color-accent)]"
              : "text-[var(--text-muted)]"
          }`}
        >
          <Eye className="w-3.5 h-3.5" />
          <span>PDF Viewer</span>
        </button>
        <button
          type="button"
          onClick={() => setMobileTab("right")}
          className={`flex items-center gap-1.5 py-1 px-2.5 rounded ${
            mobileTab === "right"
              ? "bg-[var(--bg-subtle)] font-semibold text-[var(--color-accent)]"
              : "text-[var(--text-muted)]"
          }`}
        >
          <MessageSquare className="w-3.5 h-3.5" />
          <span>Answers</span>
        </button>
      </div>

      {/* Main 3-Column Shell (Desktop) / Tabbed (Mobile) */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left sidebar: File & Session Manager */}
        <div className={`h-full ${mobileTab === "left" ? "w-full flex" : "hidden"} md:flex md:w-auto`}>
          <ResizablePanel
            width={leftSidebarWidth}
            minWidth={200}
            maxWidth={360}
            direction="left"
            onWidthChange={setLeftSidebarWidth}
            isCollapsed={leftSidebarCollapsed}
          >
            <FileManager />
          </ResizablePanel>
        </div>

        {/* Center Panel: Real PDF Viewer */}
        <div
          className={`flex-1 h-full min-w-0 overflow-hidden ${
            mobileTab === "center" ? "flex" : "hidden"
          } md:flex flex-col bg-[var(--bg-canvas)]`}
        >
          <PDFViewer key={activeDocumentName || "empty"} />
        </div>

        {/* Right sidebar: Real Streaming Q&A Workspace */}
        <div className={`h-full ${mobileTab === "right" ? "w-full flex" : "hidden"} md:flex md:w-auto`}>
          <ResizablePanel
            width={rightSidebarWidth}
            minWidth={300}
            maxWidth={600}
            direction="right"
            onWidthChange={setRightSidebarWidth}
            isCollapsed={rightSidebarCollapsed}
          >
            <div className="w-full h-full flex flex-col bg-[var(--bg-surface)] border-l border-[var(--border-subtle)] overflow-hidden">
              <ChatPanel />
            </div>
          </ResizablePanel>
        </div>
      </div>
    </div>
  );
}
