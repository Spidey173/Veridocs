import { describe, it, expect, beforeEach, vi } from "vitest";
import { useAppStore } from "../lib/store";

describe("useAppStore Unit Test Suite (Headless Vitest)", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ status: "ok" }),
    }));
    useAppStore.getState().clearSession();
  });

  it("initializes with clean default state", () => {
    const s = useAppStore.getState();
    expect(s.sessionId).toBeNull();
    expect(s.files).toEqual([]);
    expect(s.messages).toEqual([]);
    expect(s.currentPage).toBe(1);
    expect(s.pdfScale).toBe(0.6);
    expect(s.activeDocumentName).toBeNull();
  });

  it("sets session and auto-selects first document", () => {
    useAppStore.getState().setSession("sess_abc", [
      { name: "doc1.pdf", size: 100, type: "application/pdf" },
      { name: "doc2.pdf", size: 200, type: "application/pdf" },
    ]);

    const s = useAppStore.getState();
    expect(s.sessionId).toBe("sess_abc");
    expect(s.files).toHaveLength(2);
    expect(s.activeDocumentName).toBe("doc1.pdf");
    expect(s.selectedFileNames).toEqual(["doc1.pdf", "doc2.pdf"]);
  });

  it("handles streaming token appends and message updates", () => {
    useAppStore.getState().addMessage({
      id: "msg_1",
      role: "assistant",
      content: "Hello",
      isStreaming: true,
      timestamp: new Date(),
    });

    useAppStore.getState().appendToMessage("msg_1", " world!");
    expect(useAppStore.getState().messages[0].content).toBe("Hello world!");

    useAppStore.getState().updateMessage("msg_1", {
      isStreaming: false,
      confidence_score: 0.96,
    });

    const msg = useAppStore.getState().messages[0];
    expect(msg.isStreaming).toBe(false);
    expect(msg.confidence_score).toBe(0.96);
  });

  it("maintains per-document view state when switching documents", () => {
    useAppStore.getState().setSession("sess_views", [
      { name: "alpha.pdf", size: 100, type: "application/pdf" },
      { name: "beta.pdf", size: 200, type: "application/pdf" },
    ]);

    useAppStore.getState().setActiveDocument("alpha.pdf");
    useAppStore.getState().setCurrentPage(4);
    useAppStore.getState().setPdfScale(1.5);

    useAppStore.getState().setActiveDocument("beta.pdf");
    useAppStore.getState().setCurrentPage(9);
    useAppStore.getState().setPdfScale(1.8);

    // Switch back to alpha.pdf
    useAppStore.getState().setActiveDocument("alpha.pdf");
    expect(useAppStore.getState().currentPage).toBe(4);
    expect(useAppStore.getState().pdfScale).toBe(1.5);
  });

  it("cross-navigates active document on citation highlight", () => {
    useAppStore.getState().setSession("sess_cite", [
      { name: "terms.pdf", size: 100, type: "application/pdf" },
      { name: "privacy.pdf", size: 200, type: "application/pdf" },
    ]);

    useAppStore.getState().setActiveDocument("terms.pdf");
    useAppStore.getState().setCurrentPage(1);

    useAppStore.getState().highlightCitation({
      citation_id: 1,
      page: 8,
      source_file: "privacy.pdf",
      highlighted_text: "User data is encrypted at rest.",
      confidence: 0.99,
    });

    const s = useAppStore.getState();
    expect(s.activeDocumentName).toBe("privacy.pdf");
    expect(s.currentPage).toBe(8);
    expect(s.activeVisualHighlight?.snippet).toBe("User data is encrypted at rest.");
    expect(s.activeVisualHighlight?.severity).toBe("citation");
  });
});
