"use client";

/**
 * Watchlist page — add/remove/pin stocks, with live quotes from Phase 2 data.
 * Uses the Management template shape (Header → Table/Form → Actions).
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ApiError, watchlistApi, type WatchlistItem } from "@/lib/api";

const money = (n: number | null) =>
  n == null ? "—" : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const pct = (n: number | null) =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
const signClass = (n: number | null) =>
  n == null ? "" : n > 0 ? "text-green-600" : n < 0 ? "text-red-600" : "";

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

      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-3" />
              <th className="py-2 pr-3">Symbol</th>
              <th className="py-2 pr-3">Name</th>
              <th className="py-2 pr-3">Sector</th>
              <th className="py-2 pr-3 text-right">Price</th>
              <th className="py-2 pr-3 text-right">Change</th>
              <th className="py-2 pr-3" />
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="py-4 text-muted-foreground">Loading…</td></tr>
            )}
            {!loading && items.length === 0 && (
              <tr><td colSpan={7} className="py-4 text-muted-foreground">Your watchlist is empty.</td></tr>
            )}
            {items.map((item) => (
              <tr key={item.id} className="border-b">
                <td className="py-2 pr-3">
                  <button
                    aria-label={item.pinned ? "Unpin" : "Pin"}
                    onClick={() => togglePin(item)}
                    className={item.pinned ? "text-amber-500" : "text-muted-foreground hover:text-foreground"}
                  >
                    {item.pinned ? "★" : "☆"}
                  </button>
                </td>
                <td className="py-2 pr-3 font-medium">{item.symbol}</td>
                <td className="py-2 pr-3">{item.name ?? "—"}</td>
                <td className="py-2 pr-3">{item.sector ?? "—"}</td>
                <td className="py-2 pr-3 text-right">{money(item.current_price)}</td>
                <td className={`py-2 pr-3 text-right ${signClass(item.change_percent)}`}>
                  {pct(item.change_percent)}
                </td>
                <td className="py-2 pr-3 text-right">
                  <button className="text-red-600 hover:underline" onClick={() => remove(item.id)}>
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
