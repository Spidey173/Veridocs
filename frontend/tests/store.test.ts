import { describe, it, expect, beforeEach, vi } from "vitest";
import { useAppStore } from "../lib/store";

describe("useAppStore Unit Test Suite", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: "ok" }),
      })
    );
    useAppStore.getState().clearSession();
  });

  it("initializes with clean default state", () => {
    const s = useAppStore.getState();
    expect(s.sessionId).toBeNull();
    expect(s.files).toEqual([]);
    expect(s.messages).toEqual([]);
    expect(s.currentPage).toBe(1);
    expect(s.pdfScale).toBe(1.0);
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
  });

  it("handles streaming token appends and message updates", () => {
    useAppStore.getState().addMessage({
      id: "msg_1",
      role: "assistant",
      content: "Hello",
      isStreaming: true,
      timestamp: "12:00",
    });

    useAppStore.getState().appendToMessage("msg_1", " world!");
    expect(useAppStore.getState().messages[0].content).toBe("Hello world!");

    useAppStore.getState().updateMessage("msg_1", {
      isStreaming: false,
    });

    const msg = useAppStore.getState().messages[0];
    expect(msg.isStreaming).toBe(false);
  });

  it("cross-navigates active document and page on citation highlight", () => {
    useAppStore.getState().setSession("sess_cite", [
      { name: "terms.pdf", size: 100, type: "application/pdf" },
      { name: "privacy.pdf", size: 200, type: "application/pdf" },
    ]);

    useAppStore.getState().setActiveDocument("terms.pdf");
    useAppStore.getState().setCurrentPage(1);

    useAppStore.getState().highlightCitation({
      citation_id: 1,
      page: 3,
      source_file: "privacy.pdf",
      highlighted_text: "User data is encrypted at rest.",
    });

    const s = useAppStore.getState();
    expect(s.activeDocumentName).toBe("privacy.pdf");
    expect(s.currentPage).toBe(3);
    expect(s.highlightedCitation?.page).toBe(3);
  });

  it("persists active workspace session to localStorage and clears it on clearSession", () => {
    useAppStore.getState().setSession("sess_persist", [
      { name: "contract.pdf", size: 1024, type: "application/pdf" },
    ]);

    const storedRaw = localStorage.getItem("veridocs-workspace-storage");
    expect(storedRaw).toBeTruthy();
    const stored = JSON.parse(storedRaw!);
    expect(stored.state.sessionId).toBe("sess_persist");
    expect(stored.state.files[0].name).toBe("contract.pdf");

    useAppStore.getState().clearSession();
    const clearedRaw = localStorage.getItem("veridocs-workspace-storage");
    expect(clearedRaw).toBeTruthy();
    const cleared = JSON.parse(clearedRaw!);
    expect(cleared.state.sessionId).toBeNull();
    expect(cleared.state.files).toEqual([]);
  });
});
