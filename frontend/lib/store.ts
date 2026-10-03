/**
 * DocuMind AI — Global State Store (Zustand)
 * Manages application state: session, messages, UI state.
 */

import { create } from "zustand";
import type {
  CitationInfo,
  SourceInfo,
  InsightsResponse,
} from "./api";

// === Types ===

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: CitationInfo[];
  sources?: SourceInfo[];
  confidence_score?: number;
  claim_verifications?: Array<{
    claim: string;
    score: number;
    status: "verified" | "inferred" | "hallucinated";
    is_supported: boolean;
    numeric_grounded?: boolean;
    best_source_page?: number;
    source_file?: string;
  }>;
  verified_claims?: number;
  inferred_claims?: number;
  hallucinated_claims?: number;
  isStreaming?: boolean;
  timestamp: Date;
}

export interface UploadedFile {
  name: string;
  size: number;
  type: string;
  pages?: number;
}

export interface DocViewState {
  page: number;
  scale: number;
}

interface AppState {
  // Session
  sessionId: string | null;
  files: UploadedFile[];
  isUploading: boolean;
  uploadProgress: number;
  uploadStage: string;

  // Chat
  messages: ChatMessage[];
  isQuerying: boolean;
  currentStreamingId: string | null;

  // Insights
  insights: InsightsResponse | null;
  isLoadingInsights: boolean;

  // PDF Viewer
  currentPage: number;
  totalPages: number;
  highlightedCitation: CitationInfo | null;
  pdfScale: number;

  // Local file Blob URLs for instant 0ms PDF viewer rendering
  localFileUrls: Record<string, string>;
  setLocalFileUrls: (urls: Record<string, string>) => void;
  setLocalFileUrl: (fileName: string, url: string) => void;

  // Workspace Context & Layout
  activeDocumentName: string | null;
  selectedFileNames: string[];
  docViewStates: Record<string, DocViewState>;
  leftSidebarCollapsed: boolean;
  rightSidebarCollapsed: boolean;
  leftSidebarWidth: number;
  rightSidebarWidth: number;
  activePanelTab: "chat" | "insights" | "sources";

  // Actions
  setSession: (sessionId: string, files: UploadedFile[]) => void;
  clearSession: () => void;
  setUploading: (isUploading: boolean) => void;
  setUploadProgress: (progress: number, stage?: string) => void;
  addMessage: (message: ChatMessage) => void;
  updateMessage: (id: string, update: Partial<ChatMessage>) => void;
  appendToMessage: (id: string, token: string) => void;
  setQuerying: (isQuerying: boolean) => void;
  setCurrentStreamingId: (id: string | null) => void;
  setInsights: (insights: InsightsResponse) => void;
  setLoadingInsights: (loading: boolean) => void;
  setCurrentPage: (page: number) => void;
  setTotalPages: (pages: number) => void;
  highlightCitation: (citation: CitationInfo | null) => void;
  setPdfScale: (scale: number) => void;
  setActivePanelTab: (tab: "chat" | "insights" | "sources") => void;

  // Workspace Actions
  setActiveDocument: (fileName: string | null) => void;
  toggleFileSelection: (fileName: string) => void;
  selectAllFiles: () => void;
  deselectAllFiles: () => void;
  setLeftSidebarCollapsed: (collapsed: boolean) => void;
  setRightSidebarCollapsed: (collapsed: boolean) => void;
  setLeftSidebarWidth: (width: number) => void;
  setRightSidebarWidth: (width: number) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Initial state
  sessionId: null,
  files: [],
  isUploading: false,
  uploadProgress: 0,
  uploadStage: "",

  messages: [],
  isQuerying: false,
  currentStreamingId: null,

  insights: null,
  isLoadingInsights: false,

  currentPage: 1,
  totalPages: 0,
  highlightedCitation: null,
  pdfScale: 1.0,
  localFileUrls: {},

  // Workspace Context Defaults
  activeDocumentName: null,
  selectedFileNames: [],
  docViewStates: {},
  leftSidebarCollapsed: false,
  rightSidebarCollapsed: false,
  leftSidebarWidth: 240,
  rightSidebarWidth: 580,
  activePanelTab: "chat",

  setLocalFileUrls: (urls) =>
    set((state) => ({
      localFileUrls: { ...state.localFileUrls, ...urls },
    })),

  setLocalFileUrl: (fileName, url) =>
    set((state) => ({
      localFileUrls: { ...state.localFileUrls, [fileName]: url },
    })),

  // Actions
  setSession: (sessionId, files) =>
    set((state) => {
      const existingNames = state.files.map((f) => f.name);
      const newFile = files.find((f) => !existingNames.includes(f.name));

      const activeDoc = newFile
        ? newFile.name
        : (state.activeDocumentName && files.some((f) => f.name === state.activeDocumentName))
          ? state.activeDocumentName
          : (files.length > 0 ? files[0].name : null);

      return {
        sessionId,
        files,
        messages: state.sessionId === sessionId ? state.messages : [],
        insights: state.sessionId === sessionId ? state.insights : null,
        selectedFileNames: files.map((f) => f.name),
        activeDocumentName: activeDoc,
      };
    }),

  clearSession: () =>
    set((state) => {
      try {
        Object.values(state.localFileUrls).forEach((url) => {
          if (url && url.startsWith("blob:")) URL.revokeObjectURL(url);
        });
      } catch {}
      return {
        sessionId: null,
        files: [],
        messages: [],
        insights: null,
        currentPage: 1,
        totalPages: 0,
        highlightedCitation: null,
        activeDocumentName: null,
        selectedFileNames: [],
        docViewStates: {},
        localFileUrls: {},
      };
    }),

  setUploading: (isUploading) => set({ isUploading }),
  setUploadProgress: (progress, stage) =>
    set({ uploadProgress: progress, ...(stage ? { uploadStage: stage } : {}) }),

  addMessage: (message) =>
    set((state) => ({ messages: [...state.messages, message] })),

  updateMessage: (id, update) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, ...update } : m
      ),
    })),

  appendToMessage: (id, token) =>
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + token } : m
      ),
    })),

  setQuerying: (isQuerying) => set({ isQuerying }),
  setCurrentStreamingId: (id) => set({ currentStreamingId: id }),

  setInsights: (insights) => set({ insights, isLoadingInsights: false }),
  setLoadingInsights: (loading) => set({ isLoadingInsights: loading }),

  setCurrentPage: (page) =>
    set((state) => {
      // Persist page in active document viewstate
      if (state.activeDocumentName) {
        const currentViewState = state.docViewStates[state.activeDocumentName] || { page: 1, scale: state.pdfScale };
        return {
          currentPage: page,
          docViewStates: {
            ...state.docViewStates,
            [state.activeDocumentName]: { ...currentViewState, page },
          },
        };
      }
      return { currentPage: page };
    }),

  setTotalPages: (pages) => set({ totalPages: pages }),

  highlightCitation: (citation) =>
    set((state) => {
      const updates: Partial<AppState> = { highlightedCitation: citation };
      if (citation) {
        updates.currentPage = citation.page;
        // Switch to the cited file if it is different
        if (citation.source_file && citation.source_file !== state.activeDocumentName) {
          updates.activeDocumentName = citation.source_file;
          // Load document state
          const docState = state.docViewStates[citation.source_file];
          if (docState) {
            updates.pdfScale = docState.scale;
          }
        }
        
        // Persist page in viewstate
        const activeDoc = citation.source_file || state.activeDocumentName;
        if (activeDoc) {
          const currentViewState = state.docViewStates[activeDoc] || { page: 1, scale: state.pdfScale };
          updates.docViewStates = {
            ...state.docViewStates,
            [activeDoc]: { ...currentViewState, page: citation.page },
          };
        }
      }
      return updates;
    }),

  setPdfScale: (scale) =>
    set((state) => {
      if (state.activeDocumentName) {
        const currentViewState = state.docViewStates[state.activeDocumentName] || { page: state.currentPage, scale: 1.0 };
        return {
          pdfScale: scale,
          docViewStates: {
            ...state.docViewStates,
            [state.activeDocumentName]: { ...currentViewState, scale },
          },
        };
      }
      return { pdfScale: scale };
    }),

  setActivePanelTab: (tab) => set({ activePanelTab: tab }),

  // Workspace Actions
  setActiveDocument: (fileName) =>
    set((state) => {
      if (!fileName) return { activeDocumentName: null };
      const docState = state.docViewStates[fileName] || { page: 1, scale: 1.0 };
      return {
        activeDocumentName: fileName,
        currentPage: docState.page,
        pdfScale: docState.scale,
      };
    }),

  toggleFileSelection: (fileName) =>
    set((state) => {
      const selected = state.selectedFileNames.includes(fileName)
        ? state.selectedFileNames.filter((name) => name !== fileName)
        : [...state.selectedFileNames, fileName];
      return { selectedFileNames: selected };
    }),

  selectAllFiles: () =>
    set((state) => ({ selectedFileNames: state.files.map((f) => f.name) })),

  deselectAllFiles: () => set({ selectedFileNames: [] }),

  setLeftSidebarCollapsed: (collapsed) => set({ leftSidebarCollapsed: collapsed }),
  setRightSidebarCollapsed: (collapsed) => set({ rightSidebarCollapsed: collapsed }),
  setLeftSidebarWidth: (width) => set({ leftSidebarWidth: width }),
  setRightSidebarWidth: (width) => set({ rightSidebarWidth: width }),
}));
