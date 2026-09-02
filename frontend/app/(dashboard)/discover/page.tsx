"use client";

import { BookmarkPlus, Play, Trash2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DataState, PageHeader, Panel, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";
import { ApiError, discoveryApi, type SavedScreen, type ScreenerResult, type ScreenerRow } from "@/lib/api";
import { money, pct } from "@/lib/utils";

const examples = [
  "Find NIFTY 100 profitable stocks above EMA50, RSI 45-65, with non-negative recent news sentiment",
  "NIFTY 50 bullish signals with MACD positive and volume above 1.5x",
  "NIFTY 100 Technology sector stocks above EMA20 with P/E below 30",
];

const columns: Column<ScreenerRow>[] = [
  { key: "symbol", header: "Instrument", render: (row) => <Link className="font-semibold hover:text-primary" href={`/market/${encodeURIComponent(row.symbol)}`}>{row.symbol}<span className="block text-[10px] font-normal text-muted-foreground">{row.name ?? "Name unavailable"}</span></Link> },
  { key: "sector", header: "Sector", render: (row) => row.sector ?? "Unavailable" },
  { key: "close", header: "Close", align: "right", render: (row) => money(row.close) },
  { key: "change", header: "1D", align: "right", render: (row) => <TrendValue compact value={row.price_change_percent}>{pct(row.price_change_percent)}</TrendValue> },
  { key: "rsi", header: "RSI", align: "right", render: (row) => row.rsi_14?.toFixed(1) ?? "—" },
  { key: "volume", header: "Rel. volume", align: "right", render: (row) => row.volume_ratio == null ? "—" : `${row.volume_ratio.toFixed(2)}×` },
  { key: "pe", header: "P/E", align: "right", render: (row) => row.pe_ratio?.toFixed(1) ?? "—" },
  { key: "sentiment", header: "News", align: "right", render: (row) => row.news_sentiment?.toFixed(2) ?? "—" },
  { key: "signal", header: "Signal", render: (row) => <StatusBadge label={row.signal_state} tone={row.signal_state === "bullish" ? "positive" : row.signal_state === "bearish" ? "negative" : "neutral"} /> },
];

export default function DiscoverPage() {
  const [query, setQuery] = useState(examples[0]);
  const [result, setResult] = useState<ScreenerResult | null>(null);
  const [saved, setSaved] = useState<SavedScreen[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { discoveryApi.list().then(setSaved).catch(() => setError("Saved screens could not be loaded.")); }, []);

  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try { setResult(await discoveryApi.screen(query)); }
    catch (reason) { setResult(null); setError(reason instanceof ApiError ? reason.message : "The screen could not be evaluated."); }
    finally { setBusy(false); }
  }

  async function save() {
    if (!result || !name.trim()) return;
    setBusy(true); setError("");
    try { const item = await discoveryApi.save({ name: name.trim(), query_text: result.query, filter_ast: result.ast }); setSaved((current) => [item, ...current]); setName(""); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The screen could not be saved."); }
    finally { setBusy(false); }
  }

  async function run(item: SavedScreen) {
    setBusy(true); setError(""); setQuery(item.query_text);
    try { setResult(await discoveryApi.run(item.id)); } catch (reason) { setError(reason instanceof Error ? reason.message : "The saved screen could not be run."); }
    finally { setBusy(false); }
  }

  async function remove(item: SavedScreen) {
    await discoveryApi.remove(item.id); setSaved((current) => current.filter((screen) => screen.id !== item.id));
  }

  return <div className="space-y-5">
    <PageHeader eyebrow="Research workflow" title="Discover" description="Describe a supported market screen in plain language. FinSight translates it to a visible, validated filter tree and deterministically evaluates current stored data." />
    <Panel><form onSubmit={submit}><Label htmlFor="screen-query">Describe your screen</Label><textarea id="screen-query" value={query} onChange={(event) => setQuery(event.currentTarget.value)} rows={3} className="mt-2 w-full rounded-xl border border-input bg-background px-3 py-2 text-sm leading-6 outline-none focus-visible:ring-2 focus-visible:ring-ring" /><div className="mt-3 flex flex-wrap gap-2">{examples.map((example, index) => <button type="button" key={example} onClick={() => setQuery(example)} className="rounded-md bg-muted/45 px-2.5 py-1.5 text-left text-[11px] text-muted-foreground outline-none hover:bg-primary/10 hover:text-primary focus-visible:ring-2 focus-visible:ring-ring">Example {index + 1}</button>)}</div><div className="mt-4 flex flex-col items-start gap-3 sm:flex-row sm:items-center"><Button type="submit" disabled={busy}>{busy ? "Evaluating…" : "Run deterministic screen"}</Button><p className="text-xs text-muted-foreground">Unsupported fields are rejected; no SQL or AI stock selection is generated.</p></div></form>{error && <p role="alert" className="mt-3 text-sm text-negative">{error}</p>}</Panel>
    {result && <><Panel><SectionHeader title={`${result.rows.length} matching instrument${result.rows.length === 1 ? "" : "s"}`} description={`${result.ast.universe} · reproducibility hash ${result.result_hash.slice(0, 12)}`} /><div className="mt-3 flex flex-wrap gap-2" aria-label="Validated filters">{result.explanation.map((item) => <StatusBadge key={item} label={item} tone="info" />)}</div><div className="mt-4"><DataTable columns={columns} rows={result.rows} rowKey={(row) => row.symbol} caption="Deterministic stock screener results" emptyMessage="No stocks satisfy every validated condition." /></div></Panel><Panel><SectionHeader title="Save this screen" description="The validated AST is stored with the original query so it can be replayed reproducibly." /><div className="mt-3 flex max-w-xl gap-2"><Input aria-label="Saved screen name" value={name} onChange={(event) => setName(event.currentTarget.value)} placeholder="Quality momentum" /><Button onClick={() => void save()} disabled={busy || !name.trim()}><BookmarkPlus className="size-4" />Save</Button></div></Panel></>}
    <Panel><SectionHeader title="Saved screens" description="Reusable research filters that can later become alert definitions." />{saved.length === 0 ? <div className="mt-4"><DataState kind="empty" title="No saved screens" description="Run and name a screen to preserve its validated filter tree." /></div> : <ul className="mt-4 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">{saved.map((item) => <li key={item.id} className="surface-subtle p-3"><p className="text-sm font-semibold">{item.name}</p><p className="mt-1 line-clamp-2 text-xs leading-5 text-muted-foreground">{item.query_text}</p><div className="mt-3 flex gap-2"><Button size="sm" variant="outline" onClick={() => void run(item)} disabled={busy}><Play className="size-3.5" />Run</Button><Button size="sm" variant="ghost" aria-label={`Delete ${item.name}`} onClick={() => void remove(item)}><Trash2 className="size-3.5" /></Button></div></li>)}</ul>}</Panel>
  </div>;
}
