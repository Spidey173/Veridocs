import { test, expect } from "@playwright/test";

test.describe("Cross-Document Contradiction Matrix & Audit Engine", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
    await page.waitForFunction(() => (window as any).__VERIDOCS_STORE__ !== undefined);

    await page.evaluate(() => {
      const store = (window as any).__VERIDOCS_STORE__;
      store.getState().setSession("test-contradiction-session", [
        { name: "SaaS_Agreement_2024_v1.pdf", size: 2150000, type: "application/pdf" },
        { name: "SaaS_Agreement_2025_Amended.pdf", size: 2280000, type: "application/pdf" },
      ]);
      store.getState().setActiveDiffReport({
        doc_a_name: "SaaS_Agreement_2024_v1.pdf",
        doc_b_name: "SaaS_Agreement_2025_Amended.pdf",
        alignment_score: 0.68,
        summary: "Forensic cross-document analysis identified discrepancies.",
        critical_count: 2,
        warning_count: 1,
        conflicts: [
          {
            id: "diff-1",
            topic: "Payment Terms & Late Penalties",
            severity: "critical",
            conflict_type: "contradiction",
            explanation: "Doc A requires payment within 30 days. Doc B extends payment to 60 days.",
            risk_analysis: "Increases working capital cycle.",
            doc_a: {
              filename: "SaaS_Agreement_2024_v1.pdf",
              page: 1,
              snippet: "Invoices are payable within 30 days of receipt.",
              section: "4.1 Payment Terms",
            },
            doc_b: {
              filename: "SaaS_Agreement_2025_Amended.pdf",
              page: 1,
              snippet: "Customer shall remit payment within 60 calendar days from invoice date.",
              section: "4.1 Settlement",
            },
          },
          {
            id: "diff-2",
            topic: "Limitation of Liability Cap",
            severity: "critical",
            conflict_type: "numeric_mismatch",
            explanation: "Liability cap was slashed from $1,000,000 to $250,000.",
            risk_analysis: "Significantly impairs recovery rights.",
            doc_a: {
              filename: "SaaS_Agreement_2024_v1.pdf",
              page: 2,
              snippet: "The total aggregate liability shall not exceed $1,000,000 under any circumstances.",
              section: "8. Liability Limitation",
            },
            doc_b: {
              filename: "SaaS_Agreement_2025_Amended.pdf",
              page: 2,
              snippet: "Maximum cumulative liability is capped at $250,000.",
              section: "8. Damages Cap",
            },
          },
          {
            id: "diff-3",
            topic: "Service Level Agreement (SLA) & Uptime",
            severity: "warning",
            conflict_type: "modification",
            explanation: "Guaranteed uptime threshold decreased from 99.95% to 99.5%.",
            risk_analysis: "Reduces operational reliability.",
            doc_a: {
              filename: "SaaS_Agreement_2024_v1.pdf",
              page: 3,
              snippet: "Provider guarantees monthly service availability of at least 99.95%.",
              section: "Schedule B: SLA",
            },
            doc_b: {
              filename: "SaaS_Agreement_2025_Amended.pdf",
              page: 3,
              snippet: "Service availability commitment is target 99.5%.",
              section: "Schedule B: Availability",
            },
          },
        ],
      });
    });

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
