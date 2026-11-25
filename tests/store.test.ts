import { describe, it, expect, beforeEach } from "vitest";
import { useAppStore } from "../lib/store";

describe("useAppStore", () => {
  beforeEach(() => {
    useAppStore.setState({
      sessionId: null,
      files: [],
      messages: [],
      currentPage: 1,
      totalPages: 1,
      activeDocumentName: null,
      highlightedCitation: null,
    });
  });

  it("initializes with clean default values", () => {
    const state = useAppStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.files).toHaveLength(0);
    expect(state.messages).toHaveLength(0);
    expect(state.currentPage).toBe(1);
  });

  it("sets active document and updates total pages", () => {
    useAppStore.getState().setActiveDocument("contract.pdf");
    useAppStore.getState().setTotalPages(6);
    const state = useAppStore.getState();
    expect(state.activeDocumentName).toBe("contract.pdf");
    expect(state.totalPages).toBe(6);
    expect(state.currentPage).toBe(1);
  });

  it("adds chat messages correctly", () => {
    useAppStore.getState().addMessage({
      id: "msg-1",
      role: "user",
      content: "What is the liability cap?",
      timestamp: new Date().toISOString(),
    });

    const state = useAppStore.getState();
    expect(state.messages).toHaveLength(1);
    expect(state.messages[0].content).toBe("What is the liability cap?");
  });

  it("handles citation highlighting and page navigation", () => {
    const citation = {
      citation_id: 1,
      page: 4,
      source_file: "contract.pdf",
      highlighted_text: "Guaranteed Availability of 99.9%",
    };

    useAppStore.getState().highlightCitation(citation);
    const state = useAppStore.getState();
    expect(state.currentPage).toBe(4);
    expect(state.activeDocumentName).toBe("contract.pdf");
    expect(state.highlightedCitation).toEqual(citation);
  });

  it("switches active sidebar tab", () => {
    useAppStore.getState().setActiveSidebarTab("compare");
    expect(useAppStore.getState().activeSidebarTab).toBe("compare");

    useAppStore.getState().setActiveSidebarTab("documents");
    expect(useAppStore.getState().activeSidebarTab).toBe("documents");
  });

  it("stores and clears suggested questions with session", () => {
    useAppStore.getState().setSuggestedQuestions(["Summarize this document", "What are the key points?"]);
    expect(useAppStore.getState().suggestedQuestions).toHaveLength(2);

    useAppStore.getState().clearSession();
    expect(useAppStore.getState().suggestedQuestions).toHaveLength(0);
  });

  it("persists documents and session info across simulated page refresh", () => {
    useAppStore.getState().setSession("session-123", [
      { name: "test_report.pdf", size: 2048, type: "application/pdf" },
    ]);
    useAppStore.getState().setActiveDocument("test_report.pdf");

    const state = useAppStore.getState();
    expect(state.sessionId).toBe("session-123");
    expect(state.files).toHaveLength(1);
    expect(state.files[0].name).toBe("test_report.pdf");
    expect(state.activeDocumentName).toBe("test_report.pdf");
  });

  it("resets cleanly to empty dropzone when a stale session is cleared", () => {
    useAppStore.getState().setSession("stale-session-456", [
      { name: "stale_doc.pdf", size: 1024, type: "application/pdf" },
    ]);
    useAppStore.getState().addMessage({
      id: "msg-old",
      role: "user",
      content: "old question",
      timestamp: "12:00",
    });

    // Clear stale session
    useAppStore.getState().clearSession();

    const state = useAppStore.getState();
    expect(state.sessionId).toBeNull();
    expect(state.files).toHaveLength(0);
    expect(state.activeDocumentName).toBeNull();
    expect(state.messages).toHaveLength(0);
  });
});
