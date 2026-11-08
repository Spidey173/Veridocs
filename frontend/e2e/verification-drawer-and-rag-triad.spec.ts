import { test, expect } from "@playwright/test";

test.describe("Verification Drawer & RAG Triad Telemetry", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForFunction(() => (window as any).__VERIDOCS_STORE__ !== undefined);

    await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      store.getState().setSession("test-verification-session", [
        { name: "SaaS_Agreement_2024_v1.pdf", size: 2150000, type: "application/pdf" },
      ]);
      store.getState().addMessage({
        id: "msg-with-rag-triad",
        role: "assistant",
        content: "Here is the verified contractual analysis with grounding.",
        confidence_score: 0.95,
        rag_triad: {
          context_relevance: 0.95,
          groundedness: 0.97,
          answer_relevance: 0.96,
          numeric_accuracy: 1.0,
          latency_ms: 185.0,
          retrieval_pipeline: "Hybrid Full-Text + pgvector HNSW + Cross-Encoder RRF",
        },
        citations: [
          {
            citation_id: 1,
            page: 1,
            source_file: "SaaS_Agreement_2024_v1.pdf",
            highlighted_text: "Invoices are payable within 30 days of receipt.",
            confidence: 0.98,
          },
        ],
        claim_verifications: [
          {
            claim: "Payment is required within 30 days.",
            score: 0.98,
            status: "verified",
            is_supported: true,
            numeric_grounded: true,
            best_source_page: 1,
            source_file: "SaaS_Agreement_2024_v1.pdf",
          },
        ],
        timestamp: new Date(),
      });
    });
  });

  test("expands verification drawer on assistant message", async ({ page }) => {
    const drawerTrigger = page.getByRole("button", { name: /Grounding & Verification/i }).first();
    await expect(drawerTrigger).toBeVisible();

    // Verify verified confidence badge
    await expect(page.getByText("% verified").first()).toBeVisible();

    // Click to expand drawer
    await drawerTrigger.click();

    // Verify sub-tabs appear: Claims, RAG Triad, Citations
    await expect(page.getByRole("button", { name: /Claims/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /RAG Triad/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Citations/i })).toBeVisible();
  });

  test("displays RAG triad telemetry metrics when tab selected", async ({ page }) => {
    const drawerTrigger = page.getByRole("button", { name: /Grounding & Verification/i }).first();
    await drawerTrigger.click();

    // Select RAG Triad tab
    const triadTab = page.getByRole("button", { name: /RAG Triad/i });
    await triadTab.click();

    // Verify core triad metrics are displayed
    await expect(page.getByText("Context Relevance")).toBeVisible();
    await expect(page.getByText("Groundedness")).toBeVisible();
    await expect(page.getByText("Answer Relevance")).toBeVisible();
    await expect(page.getByText(/Numeric Token Fidelity/i)).toBeVisible();
  });

  test("displays source citations with page numbers and confidence", async ({ page }) => {
    const drawerTrigger = page.getByRole("button", { name: /Grounding & Verification/i }).first();
    await drawerTrigger.click();

    // Select Citations tab
    const citationsTab = page.getByRole("button", { name: /Citations/i });
    await citationsTab.click();

    // Verify citation cards
    await expect(page.getByText("SaaS_Agreement_2024_v1.pdf").first()).toBeVisible();
    await expect(page.getByText("Page 1").first()).toBeVisible();
  });
});
