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
  caption?: string;
  compact?: boolean;
  scrollClassName?: string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading = false,
  loadingMessage = "Loading…",
  emptyMessage = "No data.",
  caption,
  compact = true,
  scrollClassName,
}: DataTableProps<T>) {
  return (
    <div className="max-w-full overflow-hidden rounded-xl border border-border/45 bg-card/55 [contain:paint]">
      <div className={cn("w-full overflow-x-auto overscroll-contain", scrollClassName)}>
        <table className="w-full min-w-max text-sm" aria-busy={loading}>
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead className="sticky top-0 z-10 bg-card/95 backdrop-blur">
          <tr className="border-b border-border/70 bg-muted/35 text-left text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
            {columns.map((c) => (
              <th
                key={c.key}
                className={cn("whitespace-nowrap px-3 py-2.5", c.align === "right" && "text-right")}
              >
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-5 text-muted-foreground">
                <span className="sr-only">{loadingMessage}</span>
                <div className="space-y-2" aria-hidden>
                  {Array.from({ length: 4 }, (_, index) => <div key={index} className="h-6 animate-pulse rounded bg-muted/70 motion-reduce:animate-none" />)}
                </div>
              </td>
            </tr>
          )}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={columns.length} className="px-3 py-10 text-center text-xs text-muted-foreground">
                {emptyMessage}
              </td>
            </tr>
          )}
          {!loading && rows.map((row, i) => (
            <tr key={rowKey(row, i)} className="border-b border-border/45 transition-colors last:border-b-0 hover:bg-muted/35 focus-within:bg-primary/6">
              {columns.map((c) => (
                <td
                  key={c.key}
                  className={cn(compact ? "px-3 py-2.5" : "px-4 py-3.5", c.align === "right" && "text-right", c.className)}
                >
                  {c.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        </table>
      </div>
    </div>
  );
}
