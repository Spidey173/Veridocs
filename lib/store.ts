/**
 * Veridocs — Global State Store (Zustand)
 * Clean, minimal state for document RAG, PDF viewing, and citation check.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { CitationInfo, SourceInfo, CitationCheckResult } from "./api";
import { deleteSession } from "./api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: CitationInfo[];
  sources?: SourceInfo[];
  citation_check?: CitationCheckResult;
  isStreaming?: boolean;
  timestamp: string;
}

export interface UploadedFile {
  name: string;
  size: number;
  type: string;
  pages?: number;
}

interface AppState {
  // Session
  sessionId: string | null;
  files: UploadedFile[];
  isUploading: boolean;
  uploadProgress: number;

  // Backend Health / Cold start
  isBackendWaking: boolean;
  setIsBackendWaking: (waking: boolean) => void;

  // Chat
  messages: ChatMessage[];
  isQuerying: boolean;
  currentStreamingId: string | null;
  pendingQuestion: string | null;

  // PDF Viewer
  currentPage: number;
  totalPages: number;
  highlightedCitation: CitationInfo | null;
  pdfScale: number;

  // Local file blob URLs for client-side fallback preview
  localFileUrls: Record<string, string>;
  setLocalFileUrls: (urls: Record<string, string>) => void;

  // Active Document
  activeDocumentName: string | null;

  // Layout Sidebars
  leftSidebarCollapsed: boolean;
  rightSidebarCollapsed: boolean;
  leftSidebarWidth: number;
  rightSidebarWidth: number;
  setLeftSidebarCollapsed: (collapsed: boolean) => void;
  setRightSidebarCollapsed: (collapsed: boolean) => void;
  setLeftSidebarWidth: (width: number) => void;
  setRightSidebarWidth: (width: number) => void;

  // Actions
  setSession: (sessionId: string, files: UploadedFile[]) => void;
  clearSession: () => void;
  setUploading: (isUploading: boolean) => void;
  setUploadProgress: (progress: number) => void;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, update: Partial<ChatMessage>) => void;
  appendToMessage: (id: string, token: string) => void;
  setQuerying: (isQuerying: boolean) => void;
  setCurrentStreamingId: (id: string | null) => void;
  setPendingQuestion: (q: string | null) => void;
  setCurrentPage: (page: number) => void;
  setTotalPages: (pages: number) => void;
  highlightCitation: (citation: CitationInfo | null) => void;
  setPdfScale: (scale: number) => void;
  setActiveDocument: (fileName: string | null) => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      sessionId: null,
      files: [],
      isUploading: false,
      uploadProgress: 0,
      isBackendWaking: false,

      setIsBackendWaking: (waking) => set({ isBackendWaking: waking }),

      messages: [],
      isQuerying: false,
      currentStreamingId: null,
      pendingQuestion: null,

      currentPage: 1,
      totalPages: 1,
      highlightedCitation: null,
      pdfScale: 1.0,
      localFileUrls: {},

      activeDocumentName: null,

      leftSidebarCollapsed: false,
      rightSidebarCollapsed: false,
      leftSidebarWidth: 260,
      rightSidebarWidth: 420,
      setLeftSidebarCollapsed: (collapsed) => set({ leftSidebarCollapsed: collapsed }),
      setRightSidebarCollapsed: (collapsed) => set({ rightSidebarCollapsed: collapsed }),
      setLeftSidebarWidth: (width) => set({ leftSidebarWidth: width }),
      setRightSidebarWidth: (width) => set({ rightSidebarWidth: width }),

      setSession: (sessionId, files) => {
        const activeDoc = files.length > 0 ? files[0].name : null;
        set({
          sessionId,
          files,
          activeDocumentName: activeDoc,
          currentPage: 1,
          messages: [],
        });
      },

      clearSession: () => {
        const sid = get().sessionId;
        if (sid) {
          deleteSession(sid).catch(() => {});
        }
        set({
          sessionId: null,
          files: [],
          messages: [],
          activeDocumentName: null,
          currentPage: 1,
          totalPages: 1,
          highlightedCitation: null,
          localFileUrls: {},
        });
      },

      setUploading: (isUploading) => set({ isUploading }),
      setUploadProgress: (progress) => set({ uploadProgress: progress }),

      addMessage: (msg) => set((state) => ({ messages: [...state.messages, msg] })),

      updateMessage: (id, update) =>
        set((state) => ({
          messages: state.messages.map((m) => (m.id === id ? { ...m, ...update } : m)),
        })),

      appendToMessage: (id, token) =>
        set((state) => ({
          messages: state.messages.map((m) =>
            m.id === id ? { ...m, content: m.content + token } : m
          ),
        })),

      setQuerying: (isQuerying) => set({ isQuerying }),
      setCurrentStreamingId: (id) => set({ currentStreamingId: id }),
      setPendingQuestion: (q) => set({ pendingQuestion: q }),

      setCurrentPage: (page) => set({ currentPage: Math.max(1, page) }),
      setTotalPages: (pages) => set({ totalPages: Math.max(1, pages) }),
      highlightCitation: (citation) => {
        set({ highlightedCitation: citation });
        if (citation) {
          set({ currentPage: citation.page });
          if (citation.source_file) {
            set({ activeDocumentName: citation.source_file });
          }
        }
      },

      setPdfScale: (scale) => set({ pdfScale: Math.max(0.5, Math.min(2.5, scale)) }),
      setLocalFileUrls: (urls) => set({ localFileUrls: urls }),
      setActiveDocument: (name) => set({ activeDocumentName: name, currentPage: 1 }),
    }),
    {
      name: "veridocs-workspace-storage",
      partialize: (state) => ({
        sessionId: state.sessionId,
        files: state.files,
        activeDocumentName: state.activeDocumentName,
        messages: state.messages.slice(-20),
      }),
    }
  )
);
