"use client";

import { useEffect, useState } from "react";
import { useAppStore } from "@/lib/store";
import WorkspaceLayout from "@/components/workspace/WorkspaceLayout";
import DropZone from "@/components/upload/DropZone";
import { Loader2, Sparkles } from "lucide-react";
import { checkBackendHealth, getSessionInfo } from "@/lib/api";

export default function Home() {
  const {
    sessionId,
    files,
    isBackendWaking,
    setIsBackendWaking,
    clearSession,
  } = useAppStore();

  const [hasHydrated, setHasHydrated] = useState(false);

  // Initialize and check backend connection
  useEffect(() => {
    setHasHydrated(true);

    async function initWorkspace() {
      const verifyPersistedSession = async () => {
        const currentSid = useAppStore.getState().sessionId;
        if (currentSid) {
          try {
            await getSessionInfo(currentSid);
          } catch {
            // If session expired or 404s (e.g. backend restarted), reset cleanly to empty dropzone
            clearSession();
          }
        }
      };

      const health = await checkBackendHealth();
      if (health.waking) {
        setIsBackendWaking(true);
        // Poll every 3 seconds until awake
        const poller = setInterval(async () => {
          const check = await checkBackendHealth();
          if (check.ok) {
            setIsBackendWaking(false);
            clearInterval(poller);
            await verifyPersistedSession();
          }
        }, 3000);
      } else {
        setIsBackendWaking(false);
        await verifyPersistedSession();
      }
    }

    initWorkspace();
  }, [setIsBackendWaking, clearSession]);

  if (!hasHydrated) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-[var(--bg-canvas)]">
        <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] font-mono-data">
          <span className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-pulse" />
          <span>Starting Veridocs...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-[var(--bg-canvas)] text-[var(--text-primary)]">
      {/* Cold Start Banner for Free-Tier Hosting (Render) */}
      {isBackendWaking && (
        <div className="bg-amber-500/10 border-b border-amber-500/20 text-amber-500 px-4 py-2 text-xs flex items-center justify-center gap-2 shrink-0">
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
          <span className="font-medium">
            Backend is waking up (free-tier spin up)... Please wait ~20–30s.
          </span>
        </div>
      )}

      {sessionId && files.length > 0 ? (
        <WorkspaceLayout />
      ) : (
        <div className="flex-1 overflow-y-auto flex flex-col items-center justify-center p-6">
          <div className="w-full max-w-xl space-y-6">
            <div className="text-center space-y-2">
              <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[var(--color-accent-subtle)] text-[var(--color-accent)] border border-[var(--color-accent-border)] text-xs font-mono-data font-semibold">
                <Sparkles className="w-3.5 h-3.5" />
                <span>VERIDOCS AI</span>
              </div>
              <h1 className="text-2xl font-serif-doc font-bold tracking-tight text-[var(--text-primary)]">
                Document Intelligence & Verification
              </h1>
              <p className="text-xs text-[var(--text-secondary)] max-w-md mx-auto leading-relaxed">
                Upload a PDF or TXT contract to ask questions, view exact page citations, and verify claim grounding.
              </p>
            </div>

            <DropZone />
          </div>
        </div>
      )}
    </div>
  );
}
