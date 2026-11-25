/**
 * Veridocs — Global State Store (Zustand)
 * Clean state for document RAG, PDF viewing, citation verification, OCR status, and tables.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";
import type {
  CitationInfo,
  SourceInfo,
  CitationCheckResult,
  ExtractedTable,
  EntityItem,
  ExtractionResult,
  VisionResult,
  ComparisonData,
  DocumentFlagsResult,
  GraphResult,
  DocumentSummaryResult,
  DocumentReportResult,
} from "./api";
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
  documentId?: string;
  status?: "queued" | "parsing" | "ocr" | "chunking" | "embedding" | "ready" | "failed";
  extractionMethod?: "text_layer" | "ocr";
  ocrConfidence?: number;
  doc_type?: string;
  doc_type_confidence?: number;
  error?: string;
}

interface AppState {
  // Session
  sessionId: string | null;
  files: UploadedFile[];
  isUploading: boolean;
  uploadProgress: number;

  // Chat
  messages: ChatMessage[];
  suggestedQuestions: string[];
  isQuerying: boolean;
  currentStreamingId: string | null;
  pendingQuestion: string | null;

  // PDF Viewer
  currentPage: number;
  totalPages: number;
  highlightedCitation: CitationInfo | null;
  pdfScale: number;

  // Extracted Tables, Entities, Extractions, Flags, Graph, Comparisons
  documentTables: Record<string, ExtractedTable[]>;
  documentEntities: Record<string, EntityItem[]>;
  documentExtractions: Record<string, ExtractionResult>;
  documentVision: Record<string, VisionResult>;
  documentFlags: Record<string, DocumentFlagsResult>;
  documentGraphs: Record<string, GraphResult>;
  documentSummaries: Record<string, DocumentSummaryResult>;
  documentReports: Record<string, DocumentReportResult>;
  crossDocumentGraph: GraphResult | null;
  activeComparison: ComparisonData | null;
  isComparing: boolean;

  activeSidebarTab: "documents" | "tables" | "entities" | "fields" | "summary" | "report" | "compare" | "flags" | "graph";
  setActiveSidebarTab: (tab: "documents" | "tables" | "entities" | "fields" | "summary" | "report" | "compare" | "flags" | "graph") => void;
  setDocumentTables: (documentId: string, tables: ExtractedTable[]) => void;
  setDocumentEntities: (documentId: string, entities: EntityItem[]) => void;
  setDocumentExtraction: (documentId: string, extraction: ExtractionResult) => void;
  updateExtractionUserEdit: (documentId: string, fieldName: string, value: any) => void;
  setDocumentVision: (documentId: string, vision: VisionResult) => void;
  setDocumentFlags: (documentId: string, flags: DocumentFlagsResult) => void;
  setDocumentGraph: (documentId: string, graph: GraphResult) => void;
  setDocumentSummary: (documentId: string, summary: DocumentSummaryResult) => void;
  setDocumentReport: (documentId: string, report: DocumentReportResult) => void;
  setCrossDocumentGraph: (graph: GraphResult | null) => void;
  setActiveComparison: (comp: ComparisonData | null) => void;
  setIsComparing: (val: boolean) => void;

  // Local file blob URLs
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
  setSuggestedQuestions: (q: string[]) => void;
  setSession: (sessionId: string, files: UploadedFile[], suggestedQuestions?: string[]) => void;
  updateFile: (fileName: string, update: Partial<UploadedFile>) => void;
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

      messages: [],
      suggestedQuestions: [],
      isQuerying: false,
      currentStreamingId: null,
      pendingQuestion: null,

      currentPage: 1,
      totalPages: 1,
      highlightedCitation: null,
      pdfScale: 1.0,
      localFileUrls: {},

      documentTables: {},
      documentEntities: {},
      documentExtractions: {},
      documentVision: {},
      documentFlags: {},
      documentGraphs: {},
      documentSummaries: {},
      documentReports: {},
      crossDocumentGraph: null,
      activeComparison: null,
      isComparing: false,

      activeSidebarTab: "documents",
      setActiveSidebarTab: (activeSidebarTab) => set({ activeSidebarTab }),
      setDocumentTables: (docId, tables) =>
        set((state) => ({
          documentTables: { ...state.documentTables, [docId]: tables },
        })),
      setDocumentEntities: (docId, entities) =>
        set((state) => ({
          documentEntities: { ...state.documentEntities, [docId]: entities },
        })),
      setDocumentExtraction: (docId, extraction) =>
        set((state) => ({
          documentExtractions: { ...state.documentExtractions, [docId]: extraction },
        })),
      updateExtractionUserEdit: (docId, fieldName, value) =>
        set((state) => {
          const current = state.documentExtractions[docId] || {
            document_id: docId,
            schema_type: "other",
            fields: {},
            verified_ratio: 0.0,
            user_edits: {},
          };
          const updatedEdits = { ...(current.user_edits || {}), [fieldName]: value };
          return {
            documentExtractions: {
              ...state.documentExtractions,
              [docId]: { ...current, user_edits: updatedEdits },
            },
          };
        }),
      setDocumentVision: (docId, vision) =>
        set((state) => ({
          documentVision: { ...state.documentVision, [docId]: vision },
        })),
      setDocumentFlags: (docId, flags) =>
        set((state) => ({
          documentFlags: { ...state.documentFlags, [docId]: flags },
        })),
      setDocumentGraph: (docId, graph) =>
        set((state) => ({
          documentGraphs: { ...state.documentGraphs, [docId]: graph },
        })),
      setDocumentSummary: (docId, summary) =>
        set((state) => ({
          documentSummaries: { ...state.documentSummaries, [docId]: summary },
        })),
      setDocumentReport: (docId, report) =>
        set((state) => ({
          documentReports: { ...state.documentReports, [docId]: report },
        })),
      setCrossDocumentGraph: (crossDocumentGraph) => set({ crossDocumentGraph }),
      setActiveComparison: (activeComparison) => set({ activeComparison }),
      setIsComparing: (isComparing) => set({ isComparing }),

      activeDocumentName: null,

      leftSidebarCollapsed: false,
      rightSidebarCollapsed: false,
      leftSidebarWidth: 280,
      rightSidebarWidth: 420,
      setLeftSidebarCollapsed: (collapsed) => set({ leftSidebarCollapsed: collapsed }),
      setRightSidebarCollapsed: (collapsed) => set({ rightSidebarCollapsed: collapsed }),
      setLeftSidebarWidth: (width) => set({ leftSidebarWidth: width }),
      setRightSidebarWidth: (width) => set({ rightSidebarWidth: width }),

      setSuggestedQuestions: (suggestedQuestions) => set({ suggestedQuestions }),

      setSession: (sessionId, files, suggestedQuestions) => {
        const activeDoc = files.length > 0 ? files[0].name : null;
        set({
          sessionId,
          files,
          suggestedQuestions: suggestedQuestions || [],
          activeDocumentName: activeDoc,
          currentPage: 1,
          messages: [],
        });
      },

      updateFile: (fileName, update) =>
        set((state) => ({
          files: state.files.map((f) => (f.name === fileName ? { ...f, ...update } : f)),
        })),

      clearSession: () => {
        const sid = get().sessionId;
        if (sid) {
          deleteSession(sid).catch(() => {});
        }
        set({
          sessionId: null,
          files: [],
          suggestedQuestions: [],
          messages: [],
          activeDocumentName: null,
          currentPage: 1,
          totalPages: 1,
          highlightedCitation: null,
          localFileUrls: {},
          documentTables: {},
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
        messages: state.messages,
        suggestedQuestions: state.suggestedQuestions,
        leftSidebarCollapsed: state.leftSidebarCollapsed,
        rightSidebarCollapsed: state.rightSidebarCollapsed,
        leftSidebarWidth: state.leftSidebarWidth,
        rightSidebarWidth: state.rightSidebarWidth,
        pdfScale: state.pdfScale,
      }),
    }
  )
);
