import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * DataTable — a small generic table matching the app's table styling, so
 * gainers/losers/holdings/similar-sessions all render consistently instead of
 * bespoke <table> markup per screen. Pure and generic over the row type.
 */
export interface Column<T> {
  key: string;
  header: ReactNode;
  align?: "left" | "right";
  render: (row: T) => ReactNode;
  className?: string;
}

export interface DataTableProps<T> {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T, index: number) => string | number;
  loading?: boolean;
  loadingMessage?: string;
  emptyMessage?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  loadingMessage = "Loading…",
  emptyMessage = "No data.",
}: DataTableProps<T>) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm" aria-busy={loading}>
        <thead>
          <tr className="border-b text-left text-muted-foreground">
            {columns.map((c) => (
              <th
                key={c.key}
                className={cn("py-2 pr-3", c.align === "right" && "text-right")}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={columns.length} className="py-4 text-muted-foreground">
                {loadingMessage}
              </td>
            </tr>
          )}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="py-4 text-muted-foreground">
                {emptyMessage}
              </td>
            </tr>
          )}
          {!loading && rows.map((row, i) => (
            <tr key={rowKey(row, i)} className="border-b">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn("py-2 pr-3", c.align === "right" && "text-right", c.className)}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
