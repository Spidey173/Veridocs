"use client";

import { useState, useRef, useEffect } from "react";
import dynamic from "next/dynamic";
import { useAppStore } from "@/lib/store";
import {
  Plus,
  PanelLeftClose,
  PanelLeft,
  PanelRightClose,
  PanelRight,
  FileText,
  Search,
  BarChart3,
  Loader2,
  X,
} from "lucide-react";
import {
  searchLibrary,
  getSessionInfo,
  type CrossDocSearchResult,
  type SearchDocumentGroup,
  type SearchChunkMatch,
} from "@/lib/api";

const AnalyticsDashboard = dynamic(() => import("./AnalyticsDashboard"), { ssr: false });

export default function WorkspaceHeader() {
  const {
    sessionId,
    files,
    activeDocumentName,
    currentPage,
    totalPages,
    leftSidebarCollapsed,
    rightSidebarCollapsed,
    setLeftSidebarCollapsed,
    setRightSidebarCollapsed,
    clearSession,
    setActiveDocument,
    setCurrentPage,
    setSession,
  } = useAppStore();

  const [showDashboard, setShowDashboard] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchResults, setSearchResults] = useState<CrossDocSearchResult | null>(null);
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);
  const searchContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target as Node)) {
        setShowSearchDropdown(false);
      }
    };
    document.addEventListener("mousedown", onDocClick);
    return () => document.removeEventListener("mousedown", onDocClick);
  }, []);

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const q = searchQuery.trim();
    if (!q) return;
    setSearching(true);
    setShowSearchDropdown(true);
    try {
      const res = await searchLibrary(q, { scope: "library", topK: 12 });
      setSearchResults(res);
    } catch {
      setSearchResults({ query: q, scope: "library", total_matches: 0, documents: [] });
    } finally {
      setSearching(false);
    }
  };

  const handleSelectMatch = async (docGroup: SearchDocumentGroup, match: SearchChunkMatch) => {
    setShowSearchDropdown(false);
    if (docGroup.session_id && docGroup.session_id !== sessionId) {
      try {
        const info = await getSessionInfo(docGroup.session_id);
        setSession(
          docGroup.session_id,
          info.file_names.map((name) => ({ name, size: 0, type: "" })),
          info.suggested_questions
        );
      } catch {
        // Fallback if session lookup fails
      }
    }
    setActiveDocument(docGroup.filename);
    setCurrentPage(match.page || 1);
  };

  return (
    <>
      <header className="h-11 px-3.5 flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] bg-[var(--bg-surface)] text-[var(--text-primary)] shrink-0 z-40 select-none">
        <div className="flex items-center gap-2.5 min-w-0">
          {/* Toggle Left Sidebar */}
          {sessionId && (
            <button
              type="button"
              onClick={() => setLeftSidebarCollapsed(!leftSidebarCollapsed)}
              className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
              title={leftSidebarCollapsed ? "Expand Documents" : "Collapse Sidebar"}
            >
              {leftSidebarCollapsed ? (
                <PanelLeft className="w-4 h-4 text-[var(--color-accent)]" />
              ) : (
                <PanelLeftClose className="w-4 h-4" />
              )}
            </button>
          )}

          <div className="flex items-center gap-2 shrink-0">
            <div className="w-5 h-5 rounded bg-[var(--color-accent)] flex items-center justify-center text-white font-bold text-[10px] font-mono-data">
              V
            </div>
            <span className="text-xs font-serif-doc font-semibold tracking-tight text-[var(--text-primary)]">
              Veridocs
            </span>
          </div>

          {/* Active Document Breadcrumb */}
          {sessionId && (
            <div className="hidden lg:flex items-center gap-2 pl-3 ml-1 border-l border-[var(--border-subtle)] text-xs min-w-0">
              <span className="text-[10px] font-mono-data px-1.5 py-0.5 rounded bg-[var(--bg-subtle)] text-[var(--text-muted)] border border-[var(--border-subtle)] shrink-0">
                {files.length} {files.length === 1 ? "doc" : "docs"}
              </span>

              {activeDocumentName && (
                <div className="flex items-center gap-1.5 text-[var(--text-secondary)] font-medium truncate max-w-[200px]">
                  <FileText className="w-3.5 h-3.5 text-[var(--text-muted)] shrink-0" />
                  <span className="truncate">{activeDocumentName}</span>
                  {totalPages > 0 && (
                    <span className="text-[10px] text-[var(--text-muted)] font-mono-data shrink-0">
                      (p. {currentPage}/{totalPages})
                    </span>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Global Cross-Document Library Search Bar */}
        <div ref={searchContainerRef} className="relative flex-1 max-w-md hidden sm:block">
          <form onSubmit={handleSearch} className="relative flex items-center">
            <Search className="w-3.5 h-3.5 text-[var(--text-muted)] absolute left-2.5 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => {
                if (searchResults) setShowSearchDropdown(true);
              }}
              placeholder="Search across all documents..."
              className="w-full h-7 pl-8 pr-7 text-xs rounded-md border border-[var(--border-subtle)] bg-[var(--bg-canvas)] text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-[var(--color-accent)]"
            />
            {searching ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--color-accent)] absolute right-2" />
            ) : searchQuery ? (
              <button
                type="button"
                onClick={() => {
                  setSearchQuery("");
                  setSearchResults(null);
                  setShowSearchDropdown(false);
                }}
                className="absolute right-2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
              >
                <X className="w-3 h-3" />
              </button>
            ) : null}
          </form>

          {showSearchDropdown && searchResults && (
            <div className="absolute left-0 right-0 mt-1.5 max-h-96 overflow-y-auto rounded-lg border border-[var(--border-default)] bg-[var(--bg-surface)] shadow-xl z-50 p-2 space-y-2 text-xs">
              <div className="flex items-center justify-between px-1 pb-1 border-b border-[var(--border-subtle)] text-[10.5px] font-mono-data text-[var(--text-muted)]">
                <span>
                  {searchResults.total_matches} match(es) across {searchResults.documents.length} document(s)
                </span>
                <button
                  type="button"
                  onClick={() => setShowSearchDropdown(false)}
                  className="hover:text-[var(--text-primary)]"
                >
                  Close
                </button>
              </div>

              {searchResults.documents.length === 0 ? (
                <p className="py-4 text-center text-[var(--text-muted)]">
                  No matching chunks found across library.
                </p>
              ) : (
                searchResults.documents.map((docGrp, gIdx) => (
                  <div key={gIdx} className="space-y-1">
                    <div className="flex items-center justify-between px-1 text-[11px] font-semibold text-[var(--text-primary)]">
                      <span className="flex items-center gap-1.5 truncate">
                        <FileText className="w-3 h-3 text-[var(--color-accent)] shrink-0" />
                        <span className="truncate">{docGrp.filename}</span>
                      </span>
                      <span className="text-[10px] font-mono-data text-[var(--text-muted)]">
                        {docGrp.matches.length} hit(s)
                      </span>
                    </div>
                    <div className="space-y-1 pl-2">
                      {docGrp.matches.map((m, mIdx) => (
                        <button
                          key={mIdx}
                          type="button"
                          onClick={() => handleSelectMatch(docGrp, m)}
                          className="w-full text-left p-2 rounded border border-[var(--border-subtle)] bg-[var(--bg-canvas)] hover:border-[var(--color-accent)] transition-colors space-y-0.5"
                        >
                          <div className="flex items-center justify-between text-[10px] font-mono-data text-[var(--color-accent)]">
                            <span className="truncate">
                              {m.section_path ? `${m.section_path} · ` : ""}p.{m.page}
                            </span>
                            <span className="text-[var(--text-muted)] shrink-0 ml-2">
                              score {m.score.toFixed(2)}
                            </span>
                          </div>
                          <p className="text-[11px] text-[var(--text-secondary)] line-clamp-2">
                            {m.content}
                          </p>
                        </button>
                      ))}
                    </div>
                  </div>
                ))
              )}
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <button
            type="button"
            onClick={() => setShowDashboard(true)}
            className="flex items-center gap-1 px-2 py-1 rounded text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] border border-transparent hover:border-[var(--border-subtle)] transition-colors"
            title="Open Analytics Dashboard"
          >
            <BarChart3 className="w-3.5 h-3.5 text-[var(--color-accent)]" />
            <span className="hidden md:inline">Dashboard</span>
          </button>

          {sessionId && (
            <button
              type="button"
              onClick={clearSession}
              className="flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] border border-transparent hover:border-[var(--border-subtle)] transition-colors"
            >
              <Plus className="w-3.5 h-3.5" />
              <span>New Session</span>
            </button>
          )}

          {/* Toggle Right Sidebar */}
          {sessionId && (
            <button
              type="button"
              onClick={() => setRightSidebarCollapsed(!rightSidebarCollapsed)}
              className="p-1 rounded text-[var(--text-muted)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-subtle)] transition-colors"
              title={rightSidebarCollapsed ? "Expand Answers" : "Collapse Answers"}
            >
              {rightSidebarCollapsed ? (
                <PanelRight className="w-4 h-4 text-[var(--color-accent)]" />
              ) : (
                <PanelRightClose className="w-4 h-4" />
              )}
            </button>
          )}
        </div>
      </header>

      {showDashboard && (
        <AnalyticsDashboard isOpen={showDashboard} onClose={() => setShowDashboard(false)} />
      )}
    </>
  );
}
