"use client";

import { useEffect, useState } from "react";
import {
  FileText,
  Search,
  Scale,
  ShieldCheck,
  ChevronRight,
  ArrowRight,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import { getSessionInfo } from "@/lib/api";
import DropZone from "@/components/upload/DropZone";
import WorkspaceLayout from "@/components/workspace/WorkspaceLayout";

export default function Home() {
  const { sessionId, setSession, clearSession } = useAppStore();
  const [hasHydrated, setHasHydrated] = useState(false);

  useEffect(() => {
    setHasHydrated(true);

    const params = new URLSearchParams(window.location.search);
    const urlSession = params.get("session");

    if (!sessionId && urlSession) {
      if (urlSession === "demo-session") {
        setSession("demo-session", [
          { name: "SaaS_Agreement_2024_v1.pdf", size: 2150000, type: "application/pdf" },
          { name: "SaaS_Agreement_2025_Amended.pdf", size: 2280000, type: "application/pdf" },
          { name: "Veridocs_Technical_Architecture.pdf", size: 2450000, type: "application/pdf" },
        ]);
      } else {
        getSessionInfo(urlSession)
          .then((info) => {
            const restoredFiles = (info.file_names || []).map((name) => ({
              name,
              size: 0,
              type: "application/pdf",
            }));
            setSession(urlSession, restoredFiles);
          })
          .catch((err) => {
            console.warn("Session in URL not found on server:", err);
            clearSession();
          });
      }
    } else if (sessionId) {
      if (params.get("session") !== sessionId) {
        window.history.replaceState(null, "", `/?session=${encodeURIComponent(sessionId)}`);
      }
    }
  }, [sessionId, setSession, clearSession]);

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

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {!sessionId ? (
        <div className="h-screen flex flex-col overflow-hidden">
          <IntakeHeader />
          <div className="flex-1 overflow-y-auto">
            <DocumentIntakeScreen />
          </div>
        </div>
      ) : (
        <div className="h-screen flex flex-col overflow-hidden">
          <WorkspaceLayout />
        </div>
      )}
    </div>
  );
}

function IntakeHeader() {
  const { sessionId, clearSession } = useAppStore();

  return (
    <header className="h-12 px-6 flex items-center justify-between border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] shrink-0 z-30">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-[var(--color-accent)] flex items-center justify-center text-white font-bold text-[11px] font-mono-data">
            V
          </div>
          <h1 className="text-sm font-serif-doc font-semibold tracking-tight text-[var(--text-primary)]">
            Veridocs
          </h1>
          <span className="text-[10px] font-mono-data uppercase tracking-wider text-[var(--text-muted)] border-l border-[var(--border-default)] pl-2 ml-1">
            Document Review
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        {sessionId && (
          <button
            onClick={clearSession}
            className="px-2.5 py-1 rounded text-xs text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
          >
            New Session
          </button>
        )}
      </div>
    </header>
  );
}

function DocumentIntakeScreen() {
  const { setSession } = useAppStore();

  const loadSampleContractPair = () => {
    setSession("demo-session", [
      { name: "SaaS_Agreement_2024_v1.pdf", size: 2150000, type: "application/pdf" },
      { name: "SaaS_Agreement_2025_Amended.pdf", size: 2280000, type: "application/pdf" },
      { name: "Veridocs_Technical_Architecture.pdf", size: 2450000, type: "application/pdf" },
    ]);
  };

  return (
    <div className="min-h-full flex flex-col justify-between py-10 px-6">
      <div className="w-full max-w-xl mx-auto my-auto space-y-6">
        {/* Title & Concise Copy */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono-data font-semibold text-[var(--color-accent)] bg-[var(--color-accent-subtle)] border border-[var(--color-accent-border)]">
              WORKSPACE INTAKE
            </span>
          </div>

          <h2 className="text-2xl font-serif-doc font-semibold text-[var(--text-primary)] tracking-tight mb-2">
            Document Intelligence <span className="text-[var(--text-muted)] font-sans font-normal text-base block sm:inline sm:ml-2">Engineered for Accuracy</span>
          </h2>
          <p className="text-xs text-[var(--text-secondary)] leading-relaxed">
            Review contracts, cross-examine clauses with pixel-level coordinate citations, and verify discrepancies in a unified legal/finance workspace.
          </p>
        </div>

        {/* Central Dropzone */}
        <DropZone />

        {/* Recent / Preset Document Workspaces */}
        <div className="border-t border-[var(--border-subtle)] pt-4 space-y-2">
          <div className="flex items-center justify-between text-[11px] text-[var(--text-muted)]">
            <span className="font-medium uppercase tracking-wider font-mono-data text-[10px]">
              Sample Document Pair
            </span>
            <span>Pre-indexed test contracts</span>
          </div>

          <button
            type="button"
            onClick={loadSampleContractPair}
            className="w-full flex items-center justify-between p-3 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-surface)] hover:bg-[var(--bg-surface-raised)] hover:border-[var(--border-strong)] transition-all text-left group"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <FileText className="w-4 h-4 text-[var(--text-muted)] group-hover:text-[var(--color-accent)] shrink-0 transition-colors" />
              <div className="truncate">
                <p className="text-xs font-semibold text-[var(--text-primary)] truncate">
                  SaaS Master Services Agreement (2024 Baseline vs. 2025 Revision)
                </p>
                <p className="text-[11px] text-[var(--text-muted)] truncate font-mono-data">
                  2 contracts • Payment term variance (Net 30 → Net 60) • Liability cap discrepancy
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1 text-xs font-medium text-[var(--color-accent)] shrink-0 pl-2">
              <span>Open</span>
              <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
            </div>
          </button>
        </div>
      </div>

      {/* Quiet Engine Capabilities Spec Footer (replaces floating landing pill grid) */}
      <footer className="w-full max-w-2xl mx-auto pt-8 border-t border-[var(--border-subtle)] text-center">
        <div className="text-[11px] font-mono-data text-[var(--text-muted)] flex flex-wrap items-center justify-center gap-x-3 gap-y-1">
          <span className="font-semibold text-[var(--text-secondary)] uppercase">Engine:</span>
          <span>Hybrid Search (FTS + pgvector HNSW)</span>
          <span className="opacity-40">•</span>
          <span>Neural Re-Ranking</span>
          <span className="opacity-40">•</span>
          <span>Lexical & Numeric Grounding</span>
          <span className="opacity-40">•</span>
          <span>RAG Triad Telemetry</span>
        </div>
      </footer>
    </div>
  );
}
