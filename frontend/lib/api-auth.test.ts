import { beforeEach, describe, expect, it, vi } from "vitest";

const envelope = (data: unknown) =>
  JSON.stringify({ success: true, message: "ok", data });

describe("authenticated transport", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.resetModules();
  });

  it("shares one refresh across concurrent 401 responses", async () => {
    const attempts = new Map<string, number>();
    let csrfCalls = 0;
    let refreshCalls = 0;
    const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
      const path = String(input);
      if (path.endsWith("/auth/csrf")) {
        csrfCalls += 1;
        return new Response(envelope({ csrf_token: "csrf-before" }), { status: 200 });
      }
      if (path.endsWith("/auth/refresh")) {
        refreshCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 5));
        return new Response(envelope({
          user: {
            id: 1,
            email: "investor@example.com",
            is_active: true,
            created_at: "2026-01-01T00:00:00Z",
            preferences: {
              risk_tolerance: "moderate",
              investment_horizon: "medium",
              preferred_market: "IN",
              preferred_sectors: [],
            },
          },
          csrf_token: "csrf-after",
        }), { status: 200 });
      }
      const count = attempts.get(path) ?? 0;
      attempts.set(path, count + 1);
      return count === 0
        ? new Response("{}", { status: 401 })
        : new Response(envelope([]), { status: 200 });
    });
    const { portfolioApi, watchlistApi } = await import("./api");

    const [portfolios, watchlist] = await Promise.all([
      portfolioApi.list(),
      watchlistApi.list(),
    ]);

    expect(portfolios).toEqual([]);
    expect(watchlist).toEqual([]);
    expect(csrfCalls).toBe(1);
    expect(refreshCalls).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(6);
  });
});
