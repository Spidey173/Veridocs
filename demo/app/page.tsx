"use client";

import { motion, AnimatePresence } from "framer-motion";
import {
  Sparkles,
  Search,
  Layers,
  Shield,
  Zap,
} from "lucide-react";
import { useAppStore } from "@/lib/store";
import DropZone from "@/components/upload/DropZone";
import WorkspaceLayout from "@/components/workspace/WorkspaceLayout";

export default function Home() {
  const { sessionId } = useAppStore();

  return (
    <AnimatePresence mode="wait">
      {!sessionId ? (
        <div key="landing-layout" className="h-screen flex flex-col overflow-hidden bg-midnight-950 text-text-primary">
          <Header />
          <div className="flex-1 overflow-hidden">
            <LandingScreen />
          </div>
        </div>
      ) : (
        <div key="workspace-layout" className="h-screen flex flex-col overflow-hidden bg-midnight-950 text-text-primary">
          <WorkspaceLayout />
        </div>
      )}
    </AnimatePresence>
  );
}

// ──────────────────────────────────────
// Header
// ──────────────────────────────────────

function Header() {
  const { sessionId, clearSession } = useAppStore();

  return (
    <header className="h-14 px-6 flex items-center justify-between border-b border-white/6 bg-surface-primary/60 backdrop-blur-xl z-50">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-accent-primary to-accent-secondary flex items-center justify-center shadow-lg shadow-accent-primary/20">
            <Sparkles className="w-4 h-4 text-white" />
          </div>
          <h1 className="text-base font-bold tracking-tight">
            <span className="text-gradient">Veridocs</span>
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-2">
        {sessionId && (
          <button
            onClick={clearSession}
            className="px-3 py-1.5 rounded-lg text-xs text-text-muted hover:text-text-secondary hover:bg-white/5 transition-all"
          >
            New Session
          </button>
        )}
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-accent-primary/30 to-accent-secondary/30 border border-white/10" />
      </div>
    </header>
  );
}

// ──────────────────────────────────────
// Clean, Focused Premium Landing Screen
// ──────────────────────────────────────

function LandingScreen() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="h-full flex flex-col items-center justify-center px-6"
    >
      <div className="w-full max-w-2xl mx-auto text-center">
        {/* Hero */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
        >
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-accent-primary to-accent-secondary flex items-center justify-center mx-auto mb-5 shadow-xl shadow-accent-primary/20">
            <Sparkles className="w-7 h-7 text-white" />
          </div>

          <h2 className="text-3xl sm:text-4xl font-bold tracking-tight mb-3">
            <span className="text-gradient">Document Intelligence</span>
            <br />
            <span className="text-text-primary">Engineered for Accuracy</span>
          </h2>
          <p className="text-sm sm:text-base text-text-muted max-w-md mx-auto mb-8 font-normal leading-relaxed">
            Upload PDFs or reports to chat with source citations, claim verification, and real-time RAG audit telemetry.
          </p>
        </motion.div>

        {/* Upload Zone */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15, duration: 0.4 }}
        >
          <DropZone />
        </motion.div>

        {/* Feature Pills */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="flex flex-wrap items-center justify-center gap-2.5 mt-8"
        >
          {[
            { icon: <Search className="w-3.5 h-3.5 text-accent-primary" />, text: "Hybrid Search (BM25 + FAISS)" },
            { icon: <Layers className="w-3.5 h-3.5 text-accent-primary" />, text: "Neural Re-Ranking" },
            { icon: <Shield className="w-3.5 h-3.5 text-emerald-400" />, text: "Lexical & Numeric Grounding" },
            { icon: <Zap className="w-3.5 h-3.5 text-accent-secondary" />, text: "RAG Triad Telemetry" },
          ].map((feature, i) => (
            <span
              key={i}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs text-text-muted border border-white/6 bg-white/[0.02]"
            >
              {feature.icon}
              {feature.text}
            </span>
          ))}
        </motion.div>
      </div>
    </motion.div>
  );
}
