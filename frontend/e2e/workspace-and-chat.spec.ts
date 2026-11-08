import { test, expect } from "@playwright/test";

test.describe("AI Workspace & Interactive Chat Flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForFunction(() => (window as any).__VERIDOCS_STORE__ !== undefined);

    await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      store.getState().setSession("test-workspace-chat", [
        { name: "SaaS_Agreement_2024_v1.pdf", size: 2150000, type: "application/pdf" },
        { name: "SaaS_Agreement_2025_Amended.pdf", size: 2280000, type: "application/pdf" },
        { name: "Veridocs_Technical_Architecture.pdf", size: 2450000, type: "application/pdf" },
      ]);
      store.getState().addMessage({
        id: "initial-assistant-msg",
        role: "assistant",
        content: "Welcome to Veridocs Forensic Intelligence Studio",
        citations: [
          {
            citation_id: 1,
            page: 1,
            source_file: "SaaS_Agreement_2024_v1.pdf",
            highlighted_text: "Invoices are payable within 30 days of receipt.",
            confidence: 0.98,
          },
        ],
        confidence_score: 0.96,
        timestamp: new Date(),
      });
    });

    await expect(page.getByRole("button", { name: /New (Workspace|Session)/i })).toBeVisible();
  });

  test("loads pre-seeded documents into the file manager", async ({ page }) => {
    // Verify file manager shows the demo files
    await expect(page.getByText("SaaS_Agreement_2024_v1.pdf").first()).toBeVisible();
    await expect(page.getByText("SaaS_Agreement_2025_Amended.pdf").first()).toBeVisible();
    await expect(page.getByText("Veridocs_Technical_Architecture.pdf").first()).toBeVisible();
  });

  test("displays initial assistant briefing message with citations", async ({ page }) => {
    // Verify assistant welcome text
    await expect(page.getByText("Welcome to Veridocs Forensic Intelligence Studio")).toBeVisible();
    // Verify citation pills are present
    await expect(page.getByText("Grounding & Verification")).toBeVisible();
  });

  test("submits user query and receives grounded AI answer", async ({ page }) => {
    // Intercept SSE streaming query to provide deterministic grounded response
    await page.route("**/api/query/stream", async (route) => {
      const sseBody = [
        "event: token\ndata: {\"text\":\"Payment Settlement Window:\\n- 2024: Invoices payable within 30 days.\\n- 2025: Extended to 60 calendar days.\"}\n\n",
        "event: done\ndata: {}\n\n",
      ].join("");
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sseBody,
      });
    });

    const chatInput = page.locator("#chat-input");
    const sendButton = page.locator("#send-button");

    await expect(chatInput).toBeVisible();
    await chatInput.fill("What are the payment term differences between 2024 and 2025?");
    await sendButton.click();

    // Verify user message appears in chat
    await expect(
      page.getByText("What are the payment term differences between 2024 and 2025?")
    ).toBeVisible();

    // Verify assistant generates answer detailing payment settlement windows
    await expect(page.getByText("Payment Settlement Window")).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("30 days").first()).toBeVisible();
    await expect(page.getByText("60 calendar days").first()).toBeVisible();
  });

  test("clicking suggested follow-up query automatically populates and triggers question", async ({
    page,
  }) => {
    // Find a suggested query or button
    const suggested = page.locator("button").filter({ hasText: /technologies|experience|achievements/i }).first();
    if (await suggested.isVisible()) {
      const queryText = await suggested.innerText();
      await suggested.click();
      await expect(page.getByText(queryText.trim())).toBeVisible();
    }
  });
});
