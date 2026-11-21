import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { getApiBase, checkBackendHealth, getUserApiKey, setUserApiKey } from "../lib/api";

describe("API Client", () => {
  const originalEnv = process.env.NEXT_PUBLIC_API_URL;

  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_API_URL = originalEnv;
  });

  it("returns configured API URL without trailing slash", () => {
    process.env.NEXT_PUBLIC_API_URL = "http://localhost:8000/";
    expect(getApiBase()).toBe("http://localhost:8000");

    process.env.NEXT_PUBLIC_API_URL = "https://veridocs-api.onrender.com";
    expect(getApiBase()).toBe("https://veridocs-api.onrender.com");
  });

  it("returns empty string when NEXT_PUBLIC_API_URL is unset to use proxy rewrites", () => {
    delete process.env.NEXT_PUBLIC_API_URL;
    expect(getApiBase()).toBe("");
  });

  it("checkBackendHealth returns ok=true when backend responds healthy", async () => {
    const mockHealth = {
      status: "healthy",
      version: "0.2.0",
      llm_configured: true,
      active_sessions: 1,
      embedding_model_loaded: true,
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockHealth,
    });

    const res = await checkBackendHealth();
    expect(res.ok).toBe(true);
    expect(res.waking).toBe(false);
    expect(res.data?.status).toBe("healthy");
  });

  it("checkBackendHealth detects cold start waking when request times out", async () => {
    global.fetch = vi.fn().mockImplementation(() => {
      const err = new Error("Aborted");
      err.name = "AbortError";
      return Promise.reject(err);
    });

    const res = await checkBackendHealth();
    expect(res.ok).toBe(false);
    expect(res.waking).toBe(true);
  });

  it("saves and retrieves custom API key from browser storage", () => {
    const mockStorage: Record<string, string> = {};
    global.localStorage = {
      getItem: (k: string) => mockStorage[k] || null,
      setItem: (k: string, v: string) => { mockStorage[k] = v; },
      removeItem: (k: string) => { delete mockStorage[k]; },
      clear: () => {},
      length: 0,
      key: () => null,
    };

    setUserApiKey("gsk_test123");
    expect(getUserApiKey()).toBe("gsk_test123");

    setUserApiKey("");
    expect(getUserApiKey()).toBe("");
  });
});

