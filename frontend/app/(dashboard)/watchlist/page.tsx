"use client";

/**
 * Watchlist page — add/remove/pin stocks, with live quotes from Phase 2 data.
 * Uses the Management template shape (Header → Table/Form → Actions).
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, watchlistApi, type WatchlistItem } from "@/lib/api";
import { money, pct, signClass } from "@/lib/utils";

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [symbol, setSymbol] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    setItems(await watchlistApi.list());
  }, []);

  useEffect(() => {
    let cancelled = false;
    watchlistApi
      .list()
      .then((d) => !cancelled && setItems(d))
      .catch(() => !cancelled && setError("Could not load your watchlist."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function onAdd(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await watchlistApi.add(symbol.trim().toUpperCase());
      setSymbol("");
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not add to watchlist.");
    } finally {
      setBusy(false);
    }
  }

  async function togglePin(item: WatchlistItem) {
    await watchlistApi.update(item.id, { pinned: !item.pinned });
    await reload();
  }

  async function remove(id: number) {
    await watchlistApi.remove(id);
    await reload();
  }

  return (
    <div className="mx-auto max-w-4xl">
      <h2 className="text-2xl font-bold">Watchlist</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Track stocks you care about. Pinned items stay on top.
      </p>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Add a stock</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onAdd} className="flex items-end gap-3">
            <Input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="RELIANCE.NS"
              className="w-48"
              required
            />
            <Button type="submit" disabled={busy}>{busy ? "Adding…" : "Add"}</Button>
          </form>
          {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
        </CardContent>
      </Card>

      <div className="mt-6">
        <DataTable<WatchlistItem>
          columns={[
            {
              key: "pin",
              header: <span className="sr-only">Pin</span>,
              render: (item) => (
                <button
                  type="button"
                  aria-label={item.pinned ? "Unpin" : "Pin"}
                  onClick={() => togglePin(item)}
                  className={
                    item.pinned
                      ? "text-amber-500"
                      : "text-muted-foreground hover:text-foreground"
                  }
                >
                  {item.pinned ? "★" : "☆"}
                </button>
              ),
            },
            {
              key: "symbol",
              header: "Symbol",
              className: "font-medium",
              render: (item) => item.symbol,
            },
            { key: "name", header: "Name", render: (item) => item.name ?? "—" },
            { key: "sector", header: "Sector", render: (item) => item.sector ?? "—" },
            {
              key: "price",
              header: "Price",
              align: "right",
              render: (item) => money(item.current_price),
            },
            {
              key: "change",
              header: "Change",
              align: "right",
              render: (item) => (
                <span className={signClass(item.change_percent)}>
                  {pct(item.change_percent)}
                </span>
              ),
            },
            {
              key: "actions",
              header: <span className="sr-only">Actions</span>,
              align: "right",
              render: (item) => (
                <button
                  type="button"
                  className="text-red-600 hover:underline"
                  onClick={() => remove(item.id)}
                >
                  Remove
                </button>
              ),
            },
          ] satisfies Column<WatchlistItem>[]}
          rows={items}
          rowKey={(item) => item.id}
          loading={loading}
          emptyMessage="Your watchlist is empty."
        />
      </div>
    </div>
  );
}
