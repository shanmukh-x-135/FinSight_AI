import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { api, tokenStore, type User } from "@/lib/api";
import { AuthProvider, useAuth } from "@/lib/auth-context";

const user: User = {
  id: 1,
  email: "investor@example.com",
  is_active: true,
  created_at: "2024-01-02T10:00:00+00:00",
  preferences: {
    risk_tolerance: "moderate",
    investment_horizon: "long_term",
    preferred_market: "NSE",
    preferred_sectors: [],
  },
};

function AuthState() {
  const { loading, user: currentUser } = useAuth();
  return <p>{loading ? "loading" : currentUser?.email ?? "anonymous"}</p>;
}

describe("AuthProvider hydration", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("finishes hydration without requesting a user when no token exists", async () => {
    const me = vi.spyOn(api, "me");

    render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    );

    expect(await screen.findByText("anonymous")).toBeInTheDocument();
    expect(me).not.toHaveBeenCalled();
  });

  it("hydrates the current user when a stored token exists", async () => {
    tokenStore.set({ access_token: "access", refresh_token: "refresh", token_type: "bearer" });
    vi.spyOn(api, "me").mockResolvedValue(user);

    render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    );

    expect(await screen.findByText("investor@example.com")).toBeInTheDocument();
  });

  it("revalidates an open tab when another tab logs in", async () => {
    vi.spyOn(api, "me").mockResolvedValue(user);

    render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    );
    expect(await screen.findByText("anonymous")).toBeInTheDocument();

    tokenStore.set({ access_token: "access", refresh_token: "refresh", token_type: "bearer" });
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "finsight_access",
          newValue: "access",
          oldValue: null,
        }),
      );
    });

    expect(await screen.findByText("investor@example.com")).toBeInTheDocument();
  });

  it("clears authenticated UI when another tab logs out", async () => {
    tokenStore.set({ access_token: "access", refresh_token: "refresh", token_type: "bearer" });
    vi.spyOn(api, "me").mockResolvedValue(user);

    render(
      <AuthProvider>
        <AuthState />
      </AuthProvider>,
    );
    expect(await screen.findByText("investor@example.com")).toBeInTheDocument();

    tokenStore.clear();
    act(() => {
      window.dispatchEvent(
        new StorageEvent("storage", {
          key: "finsight_access",
          newValue: null,
          oldValue: "access",
        }),
      );
    });

    expect(await screen.findByText("anonymous")).toBeInTheDocument();
  });
});
