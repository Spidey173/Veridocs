"use client";

import React, { useState } from "react";
import { Navbar } from "../components/Navbar";
import { DocumentCanvas } from "../components/DocumentCanvas";
import { ContradictionMatrixView } from "../components/ContradictionMatrixView";
import { ChatAndAuditPanel } from "../components/ChatAndAuditPanel";
import { ArchitectureModal } from "../components/ArchitectureModal";
import { DEMO_SCENARIOS, DemoScenario, DemoCitation } from "../lib/demoData";
import { Shield, Sparkles, FileText, CheckCircle2, ExternalLink } from "lucide-react";

export default function DemoPage() {
  const [currentScenario, setCurrentScenario] = useState<DemoScenario>(DEMO_SCENARIOS[0]);
  const [activeDoc, setActiveDoc] = useState<"docA" | "docB">("docB"); // Default to amendment for richer diffs
  const [activePage, setActivePage] = useState<number>(1);
  const [activeClauseId, setActiveClauseId] = useState<string | null>("docB-sec3");
  const [activeView, setActiveView] = useState<"qa" | "matrix">("qa");
  const [isArchitectureOpen, setIsArchitectureOpen] = useState(false);

  // When scenario changes
  const handleSelectScenario = (scenario: DemoScenario) => {
    setCurrentScenario(scenario);
    setActiveDoc(scenario.docB ? "docB" : "docA");
    setActivePage(1);
    setActiveClauseId(scenario.presetQuestions[0]?.citations[0]?.clauseId || null);
  };

  // When citation clicked in chat
  const handleCitationClick = (citation: DemoCitation) => {
    // If citation is in docA or docB, switch active document
    if (citation.source_file.includes("Original") || citation.source_file.includes("2023")) {
      setActiveDoc("docA");
    } else {
      setActiveDoc("docB");
    }
    setActivePage(citation.page);
    setActiveClauseId(citation.clauseId);
  };

  // When clause clicked on document canvas
  const handleClauseClick = (clauseId: string) => {
    setActiveClauseId(clauseId);
  };

  // Inspect clause from Contradiction Matrix
  const handleInspectClause = (doc: "docA" | "docB", clauseId: string, page: number) => {
    setActiveDoc(doc);
    setActivePage(page);
    setActiveClauseId(clauseId);
    setActiveView("qa");
  };

  return (
    <div className="flex flex-col min-h-screen bg-midnight-950 text-text-primary">
      {/* Top Navigation */}
      <Navbar
        currentScenario={currentScenario}
        onSelectScenario={handleSelectScenario}
        activeView={activeView}
        onSelectView={setActiveView}
        onOpenArchitecture={() => setIsArchitectureOpen(true)}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 sm:p-6 flex flex-col gap-4">
        {/* Sub-Header Notice / Quick Explanation */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 px-4 py-3 rounded-xl border border-white/10 bg-white/[0.02]">
          <div className="flex items-center gap-2.5">
            <div className="p-1.5 rounded-lg bg-amber-500/10 text-amber-400">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-xs sm:text-sm font-bold text-white">
                {currentScenario.name}
              </h2>
              <p className="text-[11px] text-text-muted">
                {currentScenario.subtitle}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 self-stretch sm:self-auto justify-end">
            <span className="flex items-center gap-1.5 text-[11px] text-emerald-400 font-medium px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/20">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>105 Tests Passing (83% Coverage)</span>
            </span>
          </div>
        </div>

        {/* Dual-Panel Workspace Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-4 flex-1 min-h-[680px]">
          {/* Left / Center Panel (7 Cols): Document Canvas OR Contradiction Matrix */}
          <div className="lg:col-span-7 h-[680px]">
            {activeView === "qa" ? (
              <DocumentCanvas
                scenario={currentScenario}
                activeDoc={activeDoc}
                onSelectDoc={setActiveDoc}
                activeClauseId={activeClauseId}
                onClauseClick={handleClauseClick}
                activePage={activePage}
                onPageChange={setActivePage}
              />
            ) : (
              <ContradictionMatrixView
                scenario={currentScenario}
                onInspectClause={handleInspectClause}
              />
            )}
          </div>

          {/* Right Panel (5 Cols): Chat & Claim Verification Drawer */}
          <div className="lg:col-span-5 h-[680px]">
            <ChatAndAuditPanel
              scenario={currentScenario}
              onCitationClick={handleCitationClick}
              onClauseHighlight={handleClauseClick}
            />
          </div>
        </div>
      </main>

      {/* Footer / Portfolio Context */}
      <footer className="w-full border-t border-white/10 bg-midnight-950/80 px-4 sm:px-6 py-4 text-xs text-text-muted">
        <div className="max-w-7xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <span className="font-semibold text-white">Veridocs</span>
            <span>• Full-Stack Forensic Document QA & Visual Grounding Platform</span>
          </div>

          <div className="flex items-center gap-4">
            <button
              onClick={() => setIsArchitectureOpen(true)}
              className="text-amber-400 hover:text-amber-300 font-medium transition-colors"
            >
              Architecture & Security Model
            </button>
            <span>•</span>
            <a
              href="https://github.com/Spidey173/Veridocs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-text-secondary hover:text-white flex items-center gap-1 transition-colors"
            >
              <span>GitHub Repository</span>
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
        </div>
      </footer>

      {/* Architecture Modal */}
      <ArchitectureModal
        isOpen={isArchitectureOpen}
        onClose={() => setIsArchitectureOpen(false)}
      />
    </div>
  );
}
