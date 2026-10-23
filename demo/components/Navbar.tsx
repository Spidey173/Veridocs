"use client";

import { FileText, GitCompare, Shield, Sparkles, ChevronDown } from "lucide-react";
import { DEMO_SCENARIOS, DemoScenario } from "../lib/demoData";

interface NavbarProps {
  currentScenario: DemoScenario;
  onSelectScenario: (scenario: DemoScenario) => void;
  activeView: "qa" | "matrix";
  onSelectView: (view: "qa" | "matrix") => void;
  onOpenArchitecture: () => void;
}

export function Navbar({
  currentScenario,
  onSelectScenario,
  activeView,
  onSelectView,
  onOpenArchitecture,
}: NavbarProps) {
  const hasContradictions = Boolean(currentScenario.contradictions && currentScenario.contradictions.length > 0);

  return (
    <header className="sticky top-0 z-40 w-full border-b border-white/10 bg-midnight-950/80 backdrop-blur-xl px-4 sm:px-6 py-3">
      <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
        {/* Left: Brand Identity */}
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-9 h-9 rounded-xl bg-gradient-to-br from-amber-500 to-amber-600 shadow-lg shadow-amber-500/20 text-black font-black">
            <span className="text-base tracking-tighter">V</span>
            <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-base tracking-tight text-white">Veridocs</span>
              <span className="px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">
                Interactive Showcase
              </span>
            </div>
            <p className="hidden sm:block text-[11px] text-text-muted">
              Forensic Document Intelligence & Canvas Visual Grounding
            </p>
          </div>
        </div>

        {/* Center: Scenario Dropdown & View Mode Switcher */}
        <div className="flex items-center gap-2">
          {/* Scenario Selector */}
          <div className="relative group">
            <select
              value={currentScenario.id}
              onChange={(e) => {
                const s = DEMO_SCENARIOS.find((item) => item.id === e.target.value);
                if (s) {
                  onSelectScenario(s);
                  if (!s.contradictions || s.contradictions.length === 0) {
                    onSelectView("qa");
                  }
                }
              }}
              className="appearance-none cursor-pointer pl-3 pr-8 py-1.5 text-xs font-medium rounded-lg bg-white/5 border border-white/10 text-text-secondary hover:text-white hover:border-white/20 transition-all focus:outline-none focus:ring-1 focus:ring-amber-500"
            >
              {DEMO_SCENARIOS.map((s) => (
                <option key={s.id} value={s.id} className="bg-midnight-900 text-white">
                  {s.name}
                </option>
              ))}
            </select>
            <ChevronDown className="w-3.5 h-3.5 text-text-muted absolute right-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
          </div>

          {/* View Mode Switcher */}
          <div className="flex p-0.5 rounded-lg bg-white/5 border border-white/10 text-xs">
            <button
              onClick={() => onSelectView("qa")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all ${
                activeView === "qa"
                  ? "bg-amber-500/20 text-amber-400 shadow-sm border border-amber-500/30"
                  : "text-text-muted hover:text-text-secondary"
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              <span>Canvas Q&A</span>
            </button>

            {hasContradictions && (
              <button
                onClick={() => onSelectView("matrix")}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md font-medium transition-all ${
                  activeView === "matrix"
                    ? "bg-amber-500/20 text-amber-400 shadow-sm border border-amber-500/30"
                    : "text-text-muted hover:text-text-secondary"
                }`}
              >
                <GitCompare className="w-3.5 h-3.5" />
                <span>Contradiction Matrix</span>
                <span className="px-1.5 py-0.2 text-[9px] font-bold rounded-full bg-rose-500/20 text-rose-300">
                  {currentScenario.contradictions?.length}
                </span>
              </button>
            )}
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2">
          {/* Architecture Modal Button */}
          <button
            onClick={onOpenArchitecture}
            className="hidden md:flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border border-white/10 bg-white/[0.02] hover:bg-white/[0.06] text-text-secondary hover:text-white transition-all"
          >
            <Shield className="w-3.5 h-3.5 text-emerald-400" />
            <span>Architecture & Security</span>
          </button>

          {/* GitHub Repo */}
          <a
            href="https://github.com/Spidey173/Veridocs"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-white text-black hover:bg-white/90 transition-all shadow-sm"
          >
            <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z"/>
            </svg>
            <span className="hidden sm:inline">GitHub</span>
          </a>
        </div>
      </div>
    </header>
  );
}
