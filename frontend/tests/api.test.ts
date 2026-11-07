import { describe, it, expect, beforeEach, vi } from "vitest";
import { isLocalDev, getApiBase, getAuthToken, getOrFetchAuthToken } from "../lib/api";

describe("API Client Unit Test Suite (Headless Vitest)", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ access_token: "mocked_jwt_token" }),
    }));
  });

  it("determines local development environment accurately in jsdom", () => {
    // In jsdom default window.location.hostname is "localhost"
    expect(isLocalDev()).toBe(true);
  });

  it("resolves default API base URL in development environment", () => {
    const base = getApiBase();
    expect(base).toBe("http://localhost:8000");
  });

  it("reads and stores auth tokens in localStorage", async () => {
    expect(getAuthToken()).toBe("");

    localStorage.setItem("veridocs_auth_token", "jwt_test_token_xyz");
    expect(getAuthToken()).toBe("jwt_test_token_xyz");

    const fetched = await getOrFetchAuthToken();
    expect(fetched).toBe("jwt_test_token_xyz");
  });
});
