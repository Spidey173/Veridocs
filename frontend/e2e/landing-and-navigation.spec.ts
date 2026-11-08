import { test, expect } from "@playwright/test";

test.describe("Landing Screen & Navigation", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("renders hero branding, title, and feature badges", async ({ page }) => {
    // 1. Verify app branding in header
    await expect(page.locator("header")).toContainText("Veridocs");

    // 2. Verify hero headlines
    await expect(page.locator("h2")).toContainText("Document Intelligence");
    await expect(page.locator("h2")).toContainText("Engineered for Accuracy");

    // 3. Verify feature pills
    await expect(page.getByText("Hybrid Search (FTS + pgvector HNSW)")).toBeVisible();
    await expect(page.getByText("Neural Re-Ranking")).toBeVisible();
    await expect(page.getByText("Lexical & Numeric Grounding")).toBeVisible();
    await expect(page.getByText("RAG Triad Telemetry")).toBeVisible();
  });

  test("displays drag-and-drop dropzone and format specifications", async ({ page }) => {
    // Verify dropzone instructions
    await expect(page.getByText("Drop documents or click to browse")).toBeVisible();
    await expect(
      page.getByText("Supports PDF, DOCX, TXT • Page-level citations & verification")
    ).toBeVisible();

    // Verify hidden file input exists with correct accept types
    const fileInput = page.locator("#file-upload-input");
    await expect(fileInput).toBeAttached();
  });

  test("transitions into workspace on session activation and resets on new workspace", async ({ page }) => {
    await page.waitForFunction(() => (window as any).__VERIDOCS_STORE__ !== undefined);

    await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      store.getState().setSession("test-workspace-session", [
        { name: "test_agreement.pdf", size: 1024, type: "application/pdf" },
      ]);
    });

    // Verify workspace loads
    const newWorkspaceBtn = page.getByRole("button", { name: /New (Workspace|Session)/i });
    await expect(newWorkspaceBtn).toBeVisible();
    await expect(page.getByRole("button", { name: /Chat & Evidence/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Contradiction Matrix/i })).toBeVisible();

    // Click 'New Workspace' to return to landing view
    await newWorkspaceBtn.click();

    // Verify landing screen is restored
    await expect(page.getByText("Document Intelligence")).toBeVisible();
    await expect(page.getByText("Drop documents or click to browse")).toBeVisible();
  });
});
