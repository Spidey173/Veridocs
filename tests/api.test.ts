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

    process.env.NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000";
    expect(getApiBase()).toBe("http://127.0.0.1:8000");
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
    expect(res.data?.status).toBe("healthy");
  });

  it("checkBackendHealth returns ok=false when request times out or fails", async () => {
    global.fetch = vi.fn().mockImplementation(() => {
      const err = new Error("Aborted");
      err.name = "AbortError";
      return Promise.reject(err);
    });

    const res = await checkBackendHealth();
    expect(res.ok).toBe(false);
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

  it("streamQuery throws error with server detail when rate limit 429 is received", async () => {
    const { streamQuery } = await import("../lib/api");
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({
        detail: "Rate limit reached (20 requests per hour). Resets in 45 minutes.",
      }),
    });

    const generator = streamQuery("demo-session", "Any question?");
    await expect(generator.next()).rejects.toThrow(
      "Rate limit reached (20 requests per hour). Resets in 45 minutes."
    );
  });
});

