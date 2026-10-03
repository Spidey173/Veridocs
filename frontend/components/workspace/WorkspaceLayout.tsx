"use client";

import { useEffect } from "react";
import { useAppStore } from "@/lib/store";
import { getInsights } from "@/lib/api";
import ResizablePanel from "./ResizablePanel";
import FileManager from "./FileManager";
import WorkspaceHeader from "./WorkspaceHeader";
import PDFViewer from "../pdf-viewer/PDFViewer";
import AIWorkspace from "./AIWorkspace";

export default function WorkspaceLayout() {
  const {
    sessionId,
    leftSidebarCollapsed,
    rightSidebarCollapsed,
    leftSidebarWidth,
    rightSidebarWidth,
    activeDocumentName,
    setLeftSidebarWidth,
    setRightSidebarWidth,
    setInsights,
    setLoadingInsights,
  } = useAppStore();

  // Load document-specific insights dynamically when active document changes
  useEffect(() => {
    if (!sessionId || !activeDocumentName) return;

    async function loadDocInsights() {
      setLoadingInsights(true);
      try {
        const docInsights = await getInsights(sessionId!, activeDocumentName!);
        setInsights(docInsights);
      } catch (err) {
        console.error("Failed to load document insights:", err);
      } finally {
        setLoadingInsights(false);
      }
    }

    loadDocInsights();
  }, [sessionId, activeDocumentName, setInsights, setLoadingInsights]);

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-midnight-950 text-text-primary">
      {/* Global Workspace Header */}
      <WorkspaceHeader />

      {/* 3-Column Shell */}
      <div className="flex-1 flex overflow-hidden relative">
        {/* Left sidebar: File & Session Manager */}
        <ResizablePanel
          width={leftSidebarWidth}
          minWidth={220}
          maxWidth={400}
          direction="left"
          onWidthChange={setLeftSidebarWidth}
          isCollapsed={leftSidebarCollapsed}
        >
          <FileManager />
        </ResizablePanel>

        {/* Center Panel: Focus Mode PDF Viewer */}
        <div className="flex-1 h-full min-w-[320px] overflow-hidden flex flex-col bg-midnight-950">
          <PDFViewer key={activeDocumentName || "empty"} />
        </div>

        {/* Right sidebar: AI Workspace (Chat + Insights + Sources) */}
        <ResizablePanel
          width={rightSidebarWidth}
          minWidth={320}
          maxWidth={800}
          direction="right"
          onWidthChange={setRightSidebarWidth}
          isCollapsed={rightSidebarCollapsed}
        >
          <AIWorkspace />
        </ResizablePanel>
      </div>
    </div>
  );
}
