import { beforeEach, describe, expect, it, vi } from "vitest";

import { reportsApi, tokenStore } from "./api";

const envelope = (data: unknown) =>
  JSON.stringify({ success: true, message: "ok", data });

describe("reportsApi.generate", () => {
  beforeEach(() => {
    localStorage.clear();
    tokenStore.set({ access_token: "old-access", refresh_token: "refresh", token_type: "bearer" });
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
        new Response(
          envelope({
            access_token: "new-access",
            refresh_token: "new-refresh",
            token_type: "bearer",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(envelope({ id: 7 }), { status: 200 }),
      );

    await expect(reportsApi.generate()).resolves.toMatchObject({ id: 7 });

    const firstHeaders = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    const retryHeaders = fetchMock.mock.calls[2][1]?.headers as Record<string, string>;
    expect(firstHeaders["Idempotency-Key"]).toBe(
      "123e4567-e89b-42d3-a456-426614174000",
    );
    expect(retryHeaders["Idempotency-Key"]).toBe(firstHeaders["Idempotency-Key"]);
    expect(retryHeaders.Authorization).toBe("Bearer new-access");
  });
});
