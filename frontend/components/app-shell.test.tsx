import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { marketApi } from "@/lib/api";

import { AppShell } from "./app-shell";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  usePathname: () => "/dashboard",
  useRouter: () => ({ push }),
}));

vi.mock("@/lib/api", () => ({
  marketApi: { stocks: vi.fn().mockResolvedValue([]) },
}));

describe("premium application shell", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
  });

  it("preserves the complete route map and account controls", () => {
    render(<AppShell email="analyst@example.com" onLogout={vi.fn()}><p>Workspace</p></AppShell>);

    expect(screen.getByRole("navigation", { name: "Primary navigation" })).toBeVisible();
    expect(screen.getAllByRole("link", { name: "Overview" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: "Strategies" }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Open account settings" })).toBeVisible();
    expect(screen.getByText("analyst@example.com")).toBeVisible();
  });

  it("opens the command palette with the platform shortcut and supports keyboard navigation", async () => {
    const user = userEvent.setup();
    vi.mocked(marketApi.stocks).mockResolvedValue([
      { symbol: "RELIANCE.NS", name: "Reliance Industries", sector: "Energy", date: "2026-01-01", close: 1, previous_close: 1, change: 0, change_percent: 0, volume: 1, rsi_14: 50, ema_20: 1, ema_50: 1, macd_histogram: 0, trend: "neutral" },
    ]);
    render(<AppShell email="analyst@example.com" onLogout={vi.fn()}><p>Workspace</p></AppShell>);

    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    expect(screen.getByRole("dialog", { name: "FinSight command palette" })).toBeVisible();

    const input = screen.getByLabelText("Search commands and instruments");
    await user.type(input, "Reliance");
    expect(await screen.findByText("RELIANCE.NS")).toBeVisible();
    await user.keyboard("{Enter}");

    await waitFor(() => expect(push).toHaveBeenCalledWith("/market/RELIANCE.NS"));
  });

  it("moves focus into overlays and restores it when they close", async () => {
    const user = userEvent.setup();
    render(<AppShell email="analyst@example.com" onLogout={vi.fn()}><p>Workspace</p></AppShell>);
    const trigger = screen.getByRole("button", { name: "Open command palette" });

    await user.click(trigger);
    await waitFor(() => expect(screen.getByLabelText("Search commands and instruments")).toHaveFocus());
    await user.keyboard("{Escape}");
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
