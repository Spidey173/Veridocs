"use client";

import { useEffect, useState } from "react";
import { useAppStore } from "@/lib/store";
import WorkspaceLayout from "@/components/workspace/WorkspaceLayout";
import DropZone from "@/components/upload/DropZone";
import { X, FileText, Upload } from "lucide-react";

export default function Home() {
  const { sessionId, setSession, setActiveDocument, setPendingQuestion } = useAppStore();
  const [showDemoBanner, setShowDemoBanner] = useState(true);
  const [intakeMode, setIntakeMode] = useState(false);
  const [hasHydrated, setHasHydrated] = useState(false);

  useEffect(() => {
    setHasHydrated(true);

    const params = new URLSearchParams(window.location.search);
    const urlSession = params.get("session");

    if (urlSession === "intake") {
      setIntakeMode(true);
      return;
    }

    // Default to showcase workspace so visitors immediately experience the product
    if (!sessionId || sessionId === "demo-session") {
      setSession("demo-session", [
        { name: "SaaS_Agreement_2024_v1.pdf", size: 2150000, type: "application/pdf" },
        { name: "SaaS_Agreement_2025_Amended.pdf", size: 2280000, type: "application/pdf" },
        { name: "Veridocs_Technical_Architecture.pdf", size: 2450000, type: "application/pdf" },
      ]);
      setActiveDocument("SaaS_Agreement_2024_v1.pdf");
      setPendingQuestion(
        "What are the payment term differences and liability changes between the 2024 and 2025 agreements?"
      );
    }
  }, [sessionId, setSession, setActiveDocument, setPendingQuestion]);

  if (!hasHydrated) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[var(--bg-canvas)]">
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] font-mono-data">
          <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-pulse" />
          <span>Initializing workspace...</span>
        </div>
      </div>
    );
  }

  if (intakeMode || !sessionId) {
    return (
      <div className="h-screen flex flex-col overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)]">
        <header className="h-12 px-6 flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] shrink-0 z-30">
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded bg-[var(--color-accent)] flex items-center justify-center text-white font-bold text-[11px] font-mono-data">
              V
            </div>
            <h1 className="text-sm font-serif-doc font-semibold tracking-tight text-[var(--text-primary)]">
              Veridocs
            </h1>
            <span className="text-[10px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] border-l border-[var(--border-default)] pl-2 ml-1">
              Document Intake
            </span>
          </div>

          <button
            type="button"
            onClick={() => {
              setSession("demo-session", [
                { name: "SaaS_Agreement_2024_v1.pdf", size: 2150000, type: "application/pdf" },
                { name: "SaaS_Agreement_2025_Amended.pdf", size: 2280000, type: "application/pdf" },
                { name: "Veridocs_Technical_Architecture.pdf", size: 2450000, type: "application/pdf" },
              ]);
              setActiveDocument("SaaS_Agreement_2024_v1.pdf");
              setIntakeMode(false);
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-[var(--color-accent)] hover:bg-[var(--color-accent-subtle)] border border-[var(--color-accent-border)] transition-colors"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Open Sample Contracts</span>
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6 flex flex-col items-center justify-center">
          <div className="w-full max-w-xl space-y-6">
            <div>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono-data font-semibold text-[var(--color-accent)] bg-[var(--color-accent-subtle)] border border-[var(--color-accent-border)] mb-2">
                UPLOAD CONTRACTS
              </span>
              <h2 className="text-2xl font-serif-doc font-semibold text-[var(--text-primary)] tracking-tight mb-1">
                Import Documents for Analysis
              </h2>
              <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
                Drag and drop your own contract or audit documents to begin cross-examination and verification.
              </p>
            </div>

            <DropZone />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* Small, dismissible guided hint bar */}
      {showDemoBanner && (
        <div className="h-8 px-4 border-b border-[var(--border-subtle)] bg-[var(--bg-surface-raised)] flex items-center justify-between text-[11px] font-mono-data shrink-0 z-50">
          <div className="flex items-center gap-2 truncate">
            <span className="font-semibold text-[var(--color-accent)] uppercase tracking-wider flex items-center gap-1 shrink-0">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] animate-pulse" />
              Showcase Mode
            </span>
            <span className="text-[var(--text-muted)] hidden sm:inline">•</span>
            <span className="text-[var(--text-secondary)] truncate">
              <strong className="text-[var(--text-primary)]">1.</strong> Submit inquiry (Enter) ›{" "}
              <strong className="text-[var(--text-primary)]">2.</strong> Click citation [1] to jump to PDF coordinates ›{" "}
              <strong className="text-[var(--text-primary)]">3.</strong> Open Contradiction Matrix tab
            </span>
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setIntakeMode(true)}
              className="text-[11px] text-[var(--text-muted)] hover:text-[var(--text-primary)] flex items-center gap-1 font-sans"
            >
              <Upload className="w-3 h-3" />
              <span>Upload New File</span>
            </button>

            <button
              type="button"
              onClick={() => setShowDemoBanner(false)}
              className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors shrink-0"
              title="Dismiss hint"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Main 3-Pane Workspace Shell */}
      <div className="flex-1 overflow-hidden">
        <WorkspaceLayout />
      </div>
    </div>
  );
}
