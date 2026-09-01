import { act, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { AUTH_EVENT_KEY } from "@/lib/auth-events";
import { api, ApiError, type SessionData, type User } from "@/lib/api";
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

const session: SessionData = { user, csrf_token: "csrf" };

function AuthState() {
  const { status, user: currentUser } = useAuth();
  return <p>{`${status}:${currentUser?.email ?? "anonymous"}`}</p>;
}

function dispatchAuthEvent(type: "login" | "logout" | "session") {
  const newValue = JSON.stringify({ type, at: Date.now() });
  window.dispatchEvent(new StorageEvent("storage", { key: AUTH_EVENT_KEY, newValue }));
}

describe("AuthProvider session state", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("resolves an absent session without flashing authenticated content", async () => {
    vi.spyOn(api, "session").mockRejectedValue(new ApiError("Missing session", 401));

    render(<AuthProvider><AuthState /></AuthProvider>);

    expect(screen.getByText("checking:anonymous")).toBeInTheDocument();
    expect(await screen.findByText("unauthenticated:anonymous")).toBeInTheDocument();
  });

  it("hydrates the current user from the server-controlled session", async () => {
    vi.spyOn(api, "session").mockResolvedValue(session);

    render(<AuthProvider><AuthState /></AuthProvider>);

    expect(await screen.findByText("authenticated:investor@example.com")).toBeInTheDocument();
  });

  it("revalidates an open tab when another tab logs in", async () => {
    vi.spyOn(api, "session")
      .mockRejectedValueOnce(new ApiError("Missing session", 401))
      .mockResolvedValueOnce(session);

    render(<AuthProvider><AuthState /></AuthProvider>);
    expect(await screen.findByText("unauthenticated:anonymous")).toBeInTheDocument();

    act(() => dispatchAuthEvent("login"));

    expect(await screen.findByText("authenticated:investor@example.com")).toBeInTheDocument();
  });

  it("clears authenticated UI when another tab logs out", async () => {
    vi.spyOn(api, "session").mockResolvedValue(session);

    render(<AuthProvider><AuthState /></AuthProvider>);
    expect(await screen.findByText("authenticated:investor@example.com")).toBeInTheDocument();

    act(() => dispatchAuthEvent("logout"));

    expect(await screen.findByText("unauthenticated:anonymous")).toBeInTheDocument();
  });

  it("keeps a backend outage distinct from an unauthenticated session", async () => {
    vi.spyOn(api, "session").mockRejectedValue(new TypeError("network unavailable"));

    render(<AuthProvider><AuthState /></AuthProvider>);

    expect(await screen.findByText("unavailable:anonymous")).toBeInTheDocument();
  });

  it("marks a previously authenticated session as expired", async () => {
    vi.spyOn(api, "session")
      .mockResolvedValueOnce(session)
      .mockRejectedValueOnce(new ApiError("Expired", 401));

    render(<AuthProvider><AuthState /></AuthProvider>);
    expect(await screen.findByText("authenticated:investor@example.com")).toBeInTheDocument();

    act(() => dispatchAuthEvent("session"));

    expect(await screen.findByText("expired:anonymous")).toBeInTheDocument();
  });
});
