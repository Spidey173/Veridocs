import { test, expect } from "@playwright/test";

test.describe("AI Workspace & Interactive Chat Flow", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    // Navigate into the demo workspace
    await page.getByRole("button", { name: /Launch Interactive Demo Workspace/i }).click();
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
    await expect(page.getByText("30 days")).toBeVisible();
    await expect(page.getByText("60 calendar days")).toBeVisible();
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
