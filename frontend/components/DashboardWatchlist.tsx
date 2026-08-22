import Link from "next/link";

import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { WatchlistItem } from "@/lib/api";
import { cn, money, pct, signClass } from "@/lib/utils";

export interface DashboardWatchlistProps {
  items: WatchlistItem[];
  maxItems?: number;
}

/** Compact real-data watchlist for the dashboard's daily overview. */
export function DashboardWatchlist({
  items,
  maxItems = 5,
}: DashboardWatchlistProps) {
  const visibleItems = items.slice(0, maxItems);

  return (
    <Card aria-labelledby="dashboard-watchlist-title">
      <CardHeader className="border-b">
        <div className="flex items-center justify-between gap-4">
          <div>
            <CardTitle id="dashboard-watchlist-title">Your Watchlist</CardTitle>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {items.length} {items.length === 1 ? "stock" : "stocks"} tracked
            </p>
          </div>
          <Link
            href="/watchlist"
            className="shrink-0 text-xs font-medium text-primary hover:underline"
          >
            Manage watchlist
          </Link>
        </div>
      </CardHeader>
      <CardContent className="p-0">
        {visibleItems.length === 0 ? (
          <div className="px-4 py-6">
            <p className="text-sm text-muted-foreground">
              Add stocks to keep their latest price and daily move close at hand.
            </p>
          </div>
        ) : (
          <ul aria-label="Watched stocks" className="divide-y divide-foreground/10">
            {visibleItems.map((item) => (
              <li
                key={item.id}
                className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-4 px-4 py-3"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span
                    aria-hidden="true"
                    className={cn(
                      "h-5 w-0.5 shrink-0 rounded-full",
                      item.pinned ? "bg-primary" : "bg-foreground/15",
                    )}
                  />
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="truncate text-sm font-semibold">{item.symbol}</p>
                      {item.pinned && <span className="sr-only">Pinned</span>}
                    </div>
                    <p className="truncate text-xs text-muted-foreground">
                      {item.name ?? item.sector ?? "Company details unavailable"}
                    </p>
                  </div>
                </div>
                <div className="text-right tabular-nums">
                  <p className="text-sm font-medium">{money(item.current_price)}</p>
                  <p className={cn("text-xs font-medium", signClass(item.change_percent))}>
                    {pct(item.change_percent)}
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
        {items.length > maxItems && (
          <p className="border-t px-4 py-2 text-xs text-muted-foreground">
            Showing {maxItems} of {items.length} tracked stocks.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
