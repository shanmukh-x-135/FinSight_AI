import { beforeEach, describe, expect, it, vi } from "vitest";

import { reportsApi } from "./api";

const envelope = (data: unknown) =>
  JSON.stringify({ success: true, message: "ok", data });

describe("reportsApi.generate", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("preserves one opaque idempotency key through an authentication retry", async () => {
    vi.spyOn(globalThis.crypto, "randomUUID").mockReturnValue(
      "123e4567-e89b-42d3-a456-426614174000",
    );
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(
        new Response(envelope({ csrf_token: "old-csrf" }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(envelope({
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
          csrf_token: "new-csrf",
        }), { status: 200 }),
      )
      .mockResolvedValueOnce(
        new Response(envelope({ id: 7 }), { status: 200 }),
      );

    await expect(reportsApi.generate()).resolves.toMatchObject({ id: 7 });

    const firstHeaders = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    const retryHeaders = fetchMock.mock.calls[3][1]?.headers as Record<string, string>;
    expect(firstHeaders["Idempotency-Key"]).toBe(
      "123e4567-e89b-42d3-a456-426614174000",
    );
    expect(retryHeaders["Idempotency-Key"]).toBe(firstHeaders["Idempotency-Key"]);
    expect(retryHeaders["X-CSRF-Token"]).toBe("new-csrf");
    expect(fetchMock.mock.calls[2][0]).toBe("/api-proxy/api/v1/auth/refresh");
  });
});
