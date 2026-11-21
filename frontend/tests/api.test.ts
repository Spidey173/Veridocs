import { describe, it, expect, beforeEach, vi } from "vitest";
import { getApiBase, checkBackendHealth } from "../lib/api";

describe("API Client Unit Test Suite", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          status: "healthy",
          version: "0.2.0",
          llm_configured: false,
          active_sessions: 1,
          embedding_model_loaded: true,
        }),
      })
    );
  });

  it("resolves default API base URL", () => {
    const base = getApiBase();
    expect(base).toBe("");
  });

  it("checks backend health status accurately", async () => {
    const health = await checkBackendHealth();
    expect(health.ok).toBe(true);
    expect(health.waking).toBe(false);
    expect(health.data?.status).toBe("healthy");
    expect(health.data?.version).toBe("0.2.0");
  });
});
