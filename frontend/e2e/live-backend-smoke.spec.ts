import { test, expect } from "@playwright/test";

test.describe("Live Backend Integration & End-to-End Smoke Suite", () => {
  test("performs unmocked roundtrip: upload, indexing, and chat query against live backend", async ({
    page,
    request,
  }) => {
    // 1. Probe live backend health directly without mock
    let backendLive = false;
    try {
      const healthRes = await request.get("http://127.0.0.1:8000/api/health", {
        headers: { Host: "localhost" },
        timeout: 2500,
      });
      backendLive = healthRes.ok();
    } catch {
      backendLive = false;
    }

    if (!backendLive) {
      // Check via Next.js proxy rewrite /api/health
      try {
        const proxyHealth = await request.get("/api/health", { timeout: 2500 });
        backendLive = proxyHealth.ok();
      } catch {
        backendLive = false;
      }
    }

    // If backend container / process is not currently running, verify graceful readiness check
    if (!backendLive) {
      test.skip(
        !backendLive,
        "Live backend not detected on :8000 or /api/health. Run 'docker compose up' or 'uvicorn main:app' for live smoke tests."
      );
      return;
    }

    // 2. Open frontend landing page
    await page.goto("/");
    await expect(page.locator("header")).toContainText("Veridocs");

    // 3. Real Unmocked Document Upload (NO page.route interception)
    const sampleDocumentContent = `MASTER SERVICES AGREEMENT ADDENDUM 2025

Section 1. Liability Provisions
The maximum cumulative aggregate liability shall not exceed $500,000 under any circumstances.

Section 2. Settlement Terms
Invoices are payable within 45 calendar days of receipt.
`;

    const fileInput = page.locator("#file-upload-input");
    await fileInput.setInputFiles({
      name: "Live_Smoke_Agreement_2025.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(sampleDocumentContent),
    });

    // 4. Verify live workspace transitions automatically once backend processes upload
    const newWorkspaceBtn = page.getByRole("button", { name: /New (Workspace|Session)/i });
    await expect(newWorkspaceBtn).toBeVisible({ timeout: 15000 });
    await expect(page.getByText("Live_Smoke_Agreement_2025.txt").first()).toBeVisible();

    // 5. Submit real chat query to live backend
    const chatInput = page.locator("#chat-input");
    const sendButton = page.locator("#send-button");

    await chatInput.fill("What is the maximum cumulative aggregate liability?");
    await sendButton.click();

    // 6. Verify real live assistant response appears in chat
    await expect(page.getByText(/Cumulative Liability Cap|liability/i).first()).toBeVisible({ timeout: 20000 });
    await expect(page.getByRole("button", { name: /Grounding & Verification/i }).first()).toBeVisible();

    // 7. Reset session via live workspace header
    await newWorkspaceBtn.click();
    await expect(page.getByText("Document Intelligence")).toBeVisible();
  });
});
