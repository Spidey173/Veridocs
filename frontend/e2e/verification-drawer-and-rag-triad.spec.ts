import { test, expect } from "@playwright/test";

test.describe("Verification Drawer & RAG Triad Telemetry", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Launch Interactive Demo Workspace/i }).click();
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
