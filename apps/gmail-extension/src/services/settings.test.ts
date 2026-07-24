import { afterEach, describe, expect, it, vi } from "vitest";
import { loadSettings, normalizeBackendUrl } from "./settings";

describe("tracking setting", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("keeps automatic Gmail tracking disabled by default", async () => {
    vi.stubGlobal("chrome", { storage: { local: { get: vi.fn().mockResolvedValue({}) } } });
    expect((await loadSettings()).automaticTracking).toBe(false);
  });
});

describe("backend URL migration", () => {
  it("moves stale local URLs away from the dashboard origin", () => {
    expect(normalizeBackendUrl("http://localhost:8000/")).toBe("http://127.0.0.1:8000");
    expect(normalizeBackendUrl("http://localhost:5173")).toBe("http://127.0.0.1:8000");
    expect(normalizeBackendUrl("https://api.example.com/")).toBe("https://api.example.com");
  });
});
