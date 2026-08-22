"use client";

import { Pin, PinOff, Plus, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState, type FormEvent } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DataState, PageHeader, Panel, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";
import { ApiError, newsApi, watchlistApi, type LatestSentiment, type WatchlistItem } from "@/lib/api";
import { money, pct } from "@/lib/utils";

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [sentiment, setSentiment] = useState<LatestSentiment[]>([]);
  const [loading, setLoading] = useState(true);
  const [symbol, setSymbol] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => setItems(await watchlistApi.list()), []);
  useEffect(() => { let active = true; Promise.all([watchlistApi.list(), newsApi.latestSentiment()]).then(([nextItems, nextSentiment]) => { if (active) { setItems(nextItems); setSentiment(nextSentiment); } }).catch(() => active && setError("Could not load your watchlist.")).finally(() => active && setLoading(false)); return () => { active = false; }; }, []);
  const sentimentMap = useMemo(() => new Map(sentiment.map((row) => [row.symbol, row.latest_sentiment])), [sentiment]);
  const filtered = useMemo(() => items.filter((item) => `${item.symbol} ${item.name ?? ""}`.toLowerCase().includes(query.toLowerCase())), [items, query]);

  async function onAdd(event: FormEvent) { event.preventDefault(); setError(null); setBusy(true); try { await watchlistApi.add(symbol.trim().toUpperCase()); setSymbol(""); await reload(); } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Could not add to watchlist."); } finally { setBusy(false); } }
  async function togglePin(item: WatchlistItem) { await watchlistApi.update(item.id, { pinned: !item.pinned }); await reload(); }
  async function remove(id: number) { await watchlistApi.remove(id); await reload(); }

  const columns: Column<WatchlistItem>[] = [
    { key: "pin", header: <span className="sr-only">Pinned</span>, render: (item) => <button type="button" aria-label={item.pinned ? "Unpin" : "Pin"} onClick={() => togglePin(item)} className={item.pinned ? "text-warning" : "text-muted-foreground hover:text-foreground"}>{item.pinned ? <PinOff className="size-4" /> : <Pin className="size-4" />}</button> },
    { key: "symbol", header: "Instrument", render: (item) => <Link href={`/market/${encodeURIComponent(item.symbol)}`} className="block min-w-40 font-semibold hover:text-primary">{item.symbol}<span className="block text-[11px] font-normal text-muted-foreground">{item.name ?? "Name unavailable"}</span></Link> },
    { key: "sector", header: "Sector", render: (item) => <span className="text-xs text-muted-foreground">{item.sector ?? "—"}</span> },
    { key: "price", header: "Last price", align: "right", render: (item) => money(item.current_price) },
    { key: "change", header: "1D", align: "right", render: (item) => <TrendValue compact value={item.change_percent}>{pct(item.change_percent)}</TrendValue> },
    { key: "rsi", header: "RSI", align: "right", render: (item) => item.rsi_14?.toFixed(1) ?? "—" },
    { key: "trend", header: "Signal", render: (item) => item.trend ? <StatusBadge label={item.trend} tone={item.trend === "bullish" ? "positive" : item.trend === "bearish" ? "negative" : "neutral"} /> : "—" },
    { key: "news", header: "News", align: "right", render: (item) => { const value = sentimentMap.get(item.symbol); return <TrendValue compact value={value}>{value == null ? "—" : value.toFixed(2)}</TrendValue>; } },
    { key: "actions", header: <span className="sr-only">Actions</span>, align: "right", render: (item) => <Button type="button" variant="ghost" size="icon-xs" aria-label={`Remove ${item.symbol}`} onClick={() => remove(item.id)}><Trash2 className="size-3.5 text-negative" /></Button> },
  ];

  return <div className="space-y-5"><PageHeader eyebrow="Monitoring" title="Watchlist" description="Track price, momentum, technical direction, and news tone in one compact view." actions={<form onSubmit={onAdd} className="flex gap-2"><Input aria-label="Stock symbol" value={symbol} onChange={(event) => setSymbol(event.target.value)} placeholder="RELIANCE.NS" className="w-40" required /><Button type="submit" size="sm" disabled={busy}><Plus className="size-4" />{busy ? "Adding" : "Add"}</Button></form>} />{error && <div role="alert" className="rounded-lg border border-negative/30 bg-negative/10 p-3 text-sm text-negative">{error}</div>}<Panel><SectionHeader title="Monitored instruments" description={`${items.length} tracked · pinned names remain first`} /><label className="relative my-4 block max-w-sm"><span className="sr-only">Search watchlist</span><Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search watchlist" className="pl-8" /></label>{!loading && items.length === 0 ? <DataState kind="empty" title="Your watchlist is empty" description="Add an NSE symbol to begin monitoring it." /> : <DataTable columns={columns} rows={filtered} rowKey={(item) => item.id} loading={loading} emptyMessage="No watchlist items match this search." caption="Watchlist instruments and latest research signals" />}</Panel></div>;
}
