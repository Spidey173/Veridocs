import { test, expect } from "@playwright/test";

test.describe("Document Upload & API Network Interception", () => {
  test("handles document upload with stage progress and workspace transition", async ({ page }) => {
    // Intercept backend /api/upload to provide deterministic response
    await page.route("**/api/upload", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "test-session-e2e-123",
          files: ["Financial_Report_Q4.pdf"],
          chunks_created: 18,
          message: "Upload and indexing completed successfully",
        }),
      });
    });

    // Intercept /api/insights
    await page.route("**/api/insights/*", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          session_id: "test-session-e2e-123",
          executive_summary: {
            purpose: "Q4 Financial Overview",
            key_findings: ["Revenue grew 14% year over year."],
            risks: ["Supply chain fluctuations."],
            conclusions: ["Healthy balance sheet."],
          },
          suggested_questions: ["What was Q4 operating income?"],
          key_entities: [],
          total_pages: 5,
          total_chunks: 18,
          processing_time_ms: 150,
        }),
      });
    });

    await page.goto("/");

    // Prepare simulated PDF file upload which automatically executes upload
    const fileInput = page.locator("#file-upload-input");
    await fileInput.setInputFiles({
      name: "Financial_Report_Q4.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 simulated pdf test content"),
    });

    // Verify workspace layout loads with uploaded document name
    await expect(page.getByRole("button", { name: /New (Workspace|Session)/i })).toBeVisible({ timeout: 10000 });
    await expect(page.getByText("Financial_Report_Q4.pdf").first()).toBeVisible();
  });
});
