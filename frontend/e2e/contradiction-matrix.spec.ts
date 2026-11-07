import { test, expect } from "@playwright/test";

test.describe("Cross-Document Contradiction Matrix & Audit Engine", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.getByRole("button", { name: /Launch Interactive Demo Workspace/i }).click();
    // Switch to Contradiction Matrix tab
    await page.getByRole("button", { name: /Contradiction Matrix/i }).click();
  });

  test("renders contradiction matrix layout and comparative document selectors", async ({
    page,
  }) => {
    await expect(page.getByText("Forensic Contradiction Matrix")).toBeVisible();
    await expect(page.getByText("68% Alignment")).toBeVisible();
  });

  test("displays critical discrepancies with side-by-side contract excerpts", async ({ page }) => {
    // 1. Payment Terms conflict
    await expect(page.getByText("Payment Terms & Late Penalties")).toBeVisible();
    await expect(
      page.getByText(/Invoices are payable within 30 days/i).first()
    ).toBeVisible();
    await expect(
      page.getByText(/Customer shall remit payment within 60 calendar days/i).first()
    ).toBeVisible();

    // 2. Liability Cap conflict
    await expect(page.getByText("Limitation of Liability Cap")).toBeVisible();
    await expect(
      page.getByText(/total aggregate liability/i).first()
    ).toBeVisible();
    await expect(
      page.getByText(/capped at \$250,000/i).first()
    ).toBeVisible();
  });

  test("filters conflicts by severity level", async ({ page }) => {
    // Check initial count of conflict cards
    await expect(page.getByText("Payment Terms & Late Penalties")).toBeVisible();
    await expect(page.getByText("Limitation of Liability Cap")).toBeVisible();

    // Filter by 'Critical' only
    const criticalButton = page.getByRole("button", { name: /Critical/i });
    if (await criticalButton.isVisible()) {
      await criticalButton.click();
      await expect(page.getByText("Payment Terms & Late Penalties")).toBeVisible();
      await expect(page.getByText("Limitation of Liability Cap")).toBeVisible();
    }

    // Filter by 'Warnings' only
    const warningButton = page.getByRole("button", { name: /Warnings/i });
    if (await warningButton.isVisible()) {
      await warningButton.click();
      await expect(
        page.getByText("Service Level Agreement (SLA) & Uptime")
      ).toBeVisible();
      // Critical item should now be hidden
      await expect(page.getByText("Payment Terms & Late Penalties")).not.toBeVisible();
    }
  });

  test("searches conflict cards by keyword", async ({ page }) => {
    const searchInput = page.getByPlaceholder("Search conflicts...");
    await expect(searchInput).toBeVisible();

    // Search for 'Liability'
    await searchInput.fill("Liability");
    await expect(page.getByText("Limitation of Liability Cap")).toBeVisible();
    await expect(page.getByText("Payment Terms & Late Penalties")).not.toBeVisible();

    // Clear search
    await searchInput.fill("");
    await expect(page.getByText("Payment Terms & Late Penalties")).toBeVisible();
  });
});
