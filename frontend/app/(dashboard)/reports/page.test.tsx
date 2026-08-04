import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { reportsApi } from "@/lib/api";

import ReportsPage from "./page";

vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...actual,
    reportsApi: {
      ...actual.reportsApi,
      list: vi.fn(),
      generate: vi.fn(),
    },
  };
});

describe("ReportsPage loading", () => {
  beforeEach(() => {
    vi.mocked(reportsApi.list).mockResolvedValue([
      { id: 7, report_type: "daily", created_at: "2024-01-02T10:00:00+00:00" },
    ]);
  });

  it("loads the first report page after mount", async () => {
    render(<ReportsPage />);

    expect(await screen.findByRole("link", { name: "Open →" })).toHaveAttribute(
      "href",
      "/reports/7",
    );
    expect(reportsApi.list).toHaveBeenCalledWith({
      report_type: undefined,
      start_date: undefined,
      end_date: undefined,
      limit: 10,
      offset: 0,
    });
  });
});
