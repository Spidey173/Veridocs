import { test, expect } from "@playwright/test";

test.describe("Frontend State Store & API Unit Specifications", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Ensure the application store is mounted and ready
    await page.waitForFunction(() => (window as any).__VERIDOCS_STORE__ !== undefined);
  });

  test("initializes store with verified clean baseline state", async ({ page }) => {
    const initialState = await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      const s = store.getState();
      return {
        sessionId: s.sessionId,
        filesCount: s.files.length,
        messagesCount: s.messages.length,
        currentPage: s.currentPage,
        pdfScale: s.pdfScale,
        activeDoc: s.activeDocumentName,
        leftSidebarCollapsed: s.leftSidebarCollapsed,
        activeTab: s.activeWorkspaceTab,
      };
    });

    expect(initialState.sessionId).toBeNull();
    expect(initialState.filesCount).toBe(0);
    expect(initialState.messagesCount).toBe(0);
    expect(initialState.currentPage).toBe(1);
    expect(initialState.pdfScale).toBe(0.6);
    expect(initialState.activeDoc).toBeNull();
    expect(initialState.leftSidebarCollapsed).toBe(false);
    expect(initialState.activeTab).toBe("chat");
  });

  test("manages session lifecycle and active document selection", async ({ page }) => {
    const sessionResult = await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      store.getState().setSession("test-session-123", [
        { name: "contract_v1.pdf", size: 1024, type: "application/pdf", pages: 5 },
        { name: "contract_v2.pdf", size: 2048, type: "application/pdf", pages: 8 },
      ]);
      const s = store.getState();
      return {
        sessionId: s.sessionId,
        fileNames: s.files.map((f: any) => f.name),
        selectedNames: s.selectedFileNames,
        activeDoc: s.activeDocumentName,
      };
    });

    expect(sessionResult.sessionId).toBe("test-session-123");
    expect(sessionResult.fileNames).toEqual(["contract_v1.pdf", "contract_v2.pdf"]);
    expect(sessionResult.selectedNames).toEqual(["contract_v1.pdf", "contract_v2.pdf"]);
    expect(sessionResult.activeDoc).toBe("contract_v1.pdf");
  });

  test("handles streaming chat message updates and token appending", async ({ page }) => {
    const chatResult = await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      const msgId = "stream-msg-456";

      // 1. Add user message
      store.getState().addMessage({
        id: "user-1",
        role: "user",
        content: "What are the indemnity clauses?",
        timestamp: new Date(),
      });

      // 2. Add empty streaming assistant message
      store.getState().addMessage({
        id: msgId,
        role: "assistant",
        content: "",
        isStreaming: true,
        timestamp: new Date(),
      });

      // 3. Append tokens
      store.getState().appendToMessage(msgId, "Section 14.2 ");
      store.getState().appendToMessage(msgId, "specifies full indemnity.");

      // 4. Finalize message with confidence and citations
      store.getState().updateMessage(msgId, {
        isStreaming: false,
        confidence_score: 0.94,
        citations: [
          {
            page: 4,
            snippet: "The Vendor agrees to indemnify and hold harmless...",
            source_file: "contract_v1.pdf",
            confidence: 0.95,
          },
        ],
      });

      const s = store.getState();
      const finalMsg = s.messages.find((m: any) => m.id === msgId);
      return {
        totalMessages: s.messages.length,
        finalContent: finalMsg?.content,
        isStreaming: finalMsg?.isStreaming,
        confidence: finalMsg?.confidence_score,
        citationsCount: finalMsg?.citations?.length,
      };
    });

    expect(chatResult.totalMessages).toBe(2);
    expect(chatResult.finalContent).toBe("Section 14.2 specifies full indemnity.");
    expect(chatResult.isStreaming).toBe(false);
    expect(chatResult.confidence).toBe(0.94);
    expect(chatResult.citationsCount).toBe(1);
  });

  test("persists per-document view state when switching documents and pages", async ({ page }) => {
    const viewResult = await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      store.getState().setSession("session-view-test", [
        { name: "docA.pdf", size: 1000, type: "application/pdf" },
        { name: "docB.pdf", size: 2000, type: "application/pdf" },
      ]);

      // Set page 3 and scale 1.25 on docA
      store.getState().setActiveDocument("docA.pdf");
      store.getState().setCurrentPage(3);
      store.getState().setPdfScale(1.25);

      // Switch to docB and set page 7 and scale 1.5
      store.getState().setActiveDocument("docB.pdf");
      store.getState().setCurrentPage(7);
      store.getState().setPdfScale(1.5);

      const stateWhileOnB = {
        activeDoc: store.getState().activeDocumentName,
        currentPage: store.getState().currentPage,
        pdfScale: store.getState().pdfScale,
      };

      // Switch back to docA — verify page 3 and scale 1.25 are restored
      store.getState().setActiveDocument("docA.pdf");
      const stateRestoredToA = {
        activeDoc: store.getState().activeDocumentName,
        currentPage: store.getState().currentPage,
        pdfScale: store.getState().pdfScale,
      };

      return { stateWhileOnB, stateRestoredToA };
    });

    expect(viewResult.stateWhileOnB.activeDoc).toBe("docB.pdf");
    expect(viewResult.stateWhileOnB.currentPage).toBe(7);
    expect(viewResult.stateWhileOnB.pdfScale).toBe(1.5);

    expect(viewResult.stateRestoredToA.activeDoc).toBe("docA.pdf");
    expect(viewResult.stateRestoredToA.currentPage).toBe(3);
    expect(viewResult.stateRestoredToA.pdfScale).toBe(1.25);
  });

  test("highlightCitation correctly cross-navigates document and sets visual highlight", async ({ page }) => {
    const highlightResult = await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      store.getState().setSession("session-citation-test", [
        { name: "doc1.pdf", size: 500, type: "application/pdf" },
        { name: "doc2.pdf", size: 800, type: "application/pdf" },
      ]);

      store.getState().setActiveDocument("doc1.pdf");
      store.getState().setCurrentPage(1);

      // Trigger citation on doc2 page 6
      store.getState().highlightCitation({
        citation_id: 1,
        page: 6,
        source_file: "doc2.pdf",
        highlighted_text: "Arbitration will occur in New York",
        confidence: 0.98,
      });

      const s = store.getState();
      return {
        activeDoc: s.activeDocumentName,
        currentPage: s.currentPage,
        highlightDoc: s.activeVisualHighlight?.documentName,
        highlightPage: s.activeVisualHighlight?.page,
        highlightSnippet: s.activeVisualHighlight?.snippet,
        highlightSeverity: s.activeVisualHighlight?.severity,
      };
    });

    expect(highlightResult.activeDoc).toBe("doc2.pdf");
    expect(highlightResult.currentPage).toBe(6);
    expect(highlightResult.highlightDoc).toBe("doc2.pdf");
    expect(highlightResult.highlightPage).toBe(6);
    expect(highlightResult.highlightSnippet).toBe("Arbitration will occur in New York");
    expect(highlightResult.highlightSeverity).toBe("citation");
  });

  test("clearSession resets all workspace and visual state cleanly", async ({ page }) => {
    const clearedResult = await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      store.getState().setSession("session-to-clear", [
        { name: "file1.pdf", size: 500, type: "application/pdf" },
      ]);
      store.getState().addMessage({
        id: "msg-1",
        role: "user",
        content: "hello",
        timestamp: new Date(),
      });
      store.getState().setCurrentPage(5);

      // Now clear
      store.getState().clearSession();

      const s = store.getState();
      return {
        sessionId: s.sessionId,
        filesLength: s.files.length,
        messagesLength: s.messages.length,
        currentPage: s.currentPage,
        activeDoc: s.activeDocumentName,
        selectedNames: s.selectedFileNames,
      };
    });

    expect(clearedResult.sessionId).toBeNull();
    expect(clearedResult.filesLength).toBe(0);
    expect(clearedResult.messagesLength).toBe(0);
    expect(clearedResult.currentPage).toBe(1);
    expect(clearedResult.activeDoc).toBeNull();
    expect(clearedResult.selectedNames).toEqual([]);
  });

  test("verifies API client environment detection and authentication storage helpers", async ({ page }) => {
    const apiResult = await page.evaluate(async () => {
      const api = (window as any).__VERIDOCS_API__;
      const isDev = api.isLocalDev();
      const base = api.getApiBase();

      // Test auth token caching
      localStorage.setItem("veridocs_auth_token", "test-bearer-token-999");
      const readToken = api.getAuthToken();
      const fetchedToken = await api.getOrFetchAuthToken();

      return {
        isDev,
        base,
        readToken,
        fetchedToken,
      };
    });

    expect(apiResult.isDev).toBe(true);
    expect(apiResult.base).toBe("http://localhost:8000");
    expect(apiResult.readToken).toBe("test-bearer-token-999");
    expect(apiResult.fetchedToken).toBe("test-bearer-token-999");
  });
});
