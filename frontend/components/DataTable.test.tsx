import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DataTable, type Column } from "./DataTable";

interface Row {
  id: number;
  symbol: string;
}

const columns = (onRemove = vi.fn()): Column<Row>[] => [
  { key: "symbol", header: "Symbol", render: (row) => row.symbol },
  {
    key: "actions",
    header: <span className="sr-only">Actions</span>,
    render: (row) => <button onClick={() => onRemove(row.id)}>Remove</button>,
  },
];

describe("DataTable", () => {
  it("renders its loading state without stale rows", () => {
    render(
      <DataTable
        columns={columns()}
        rows={[{ id: 1, symbol: "AAA.NS" }]}
        rowKey={(row) => row.id}
        loading
      />,
    );
    expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByText("Loading…")).toBeInTheDocument();
    expect(screen.queryByText("AAA.NS")).not.toBeInTheDocument();
  });

  it("renders a caller-provided empty state", () => {
    render(
      <DataTable
        columns={columns()}
        rows={[]}
        rowKey={(row) => row.id}
        emptyMessage="No holdings yet."
      />,
    );
    expect(screen.getByText("No holdings yet.")).toBeInTheDocument();
  });

  it("renders rows with stable keys and delegates row actions", async () => {
    const onRemove = vi.fn();
    const user = userEvent.setup();
    render(
      <DataTable
        columns={columns(onRemove)}
        rows={[{ id: 7, symbol: "AAA.NS" }]}
        rowKey={(row) => row.id}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Remove" }));
    expect(onRemove).toHaveBeenCalledWith(7);
  });
});
