"use client";

import { ArrowDownUp, BookmarkCheck, BookmarkPlus, Search } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { AIAnalysisState } from "@/components/AIAnalysisState";
import { AIInsightCard } from "@/components/AIInsightCard";
import { DataTable, type Column } from "@/components/DataTable";
import { EconomicEventsCard, TechnicalSummaryCard } from "@/components/MarketContext";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { SectorRotation } from "@/components/sector-rotation";
import { StockHeatmap } from "@/components/stock-heatmap";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { DataState, PageHeader, PageSkeleton, Panel, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";
import { intelligenceApi, marketApi, watchlistApi, type Breadth, type EconomicCalendar, type HeatmapStock, type LatestSentiment, type MarketStockSnapshot, type Recommendation, type SectorOverview, type SectorRotation as SectorRotationRow, type TechnicalSummary, type UniverseCode, type UniverseOption, type WatchlistItem } from "@/lib/api";
import { money, pct } from "@/lib/utils";

type SortKey = "symbol" | "change" | "rsi";
const DEFAULT_UNIVERSE: UniverseCode = "NIFTY100";

export default function MarketPage() {
  const [stocks, setStocks] = useState<MarketStockSnapshot[]>([]);
  const [universe, setUniverse] = useState<UniverseCode>(DEFAULT_UNIVERSE);
  const [universeOptions, setUniverseOptions] = useState<UniverseOption[]>([]);
  const [breadth, setBreadth] = useState<Breadth | null>(null);
  const [sectors, setSectors] = useState<SectorOverview[]>([]);
  const [heatmap, setHeatmap] = useState<HeatmapStock[]>([]);
  const [rotation, setRotation] = useState<SectorRotationRow[]>([]);
  const [technical, setTechnical] = useState<TechnicalSummary | null>(null);
  const [calendar, setCalendar] = useState<EconomicCalendar | null>(null);
  const [sentiment, setSentiment] = useState<LatestSentiment[]>([]);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [risks, setRisks] = useState<Recommendation[]>([]);
  const [aiUnavailable, setAiUnavailable] = useState(false);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [watchBusy, setWatchBusy] = useState<string | null>(null);
  const [watchError, setWatchError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState("");
  const [sector, setSector] = useState("All sectors");
  const [sort, setSort] = useState<SortKey>("change");

  useEffect(() => {
    let active = true;
    marketApi.universes().then((options) => { if (active) { setUniverseOptions(options); const preferred = options.find((option) => option.preferred); if (preferred && preferred.code !== DEFAULT_UNIVERSE) { setLoading(true); setError(false); setUniverse(preferred.code); } } }).catch(() => undefined);
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    marketApi.workspace(universe)
      .then((workspace) => { if (active) { setStocks(workspace.stocks); setBreadth(workspace.breadth); setSectors(workspace.sectors); setTechnical(workspace.technical); setHeatmap(workspace.heatmap); setRotation(workspace.sector_rotation); setCalendar(workspace.economic_events); setSentiment(workspace.sentiment); } })
      .catch(() => active && setError(true))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [universe]);

  useEffect(() => {
    let active = true;
    intelligenceApi.recommendations().then((data) => { if (active) { setRecs(data.watchlist); setRisks(data.risk_alerts); } }).catch(() => active && setAiUnavailable(true));
    watchlistApi.list().then((items) => active && setWatchlist(items)).catch(() => active && setWatchError("Watchlist actions are temporarily unavailable."));
    return () => { active = false; };
  }, []);

  const sentimentMap = useMemo(() => new Map(sentiment.map((row) => [row.symbol, row.latest_sentiment])), [sentiment]);
  const watchedMap = useMemo(() => new Map(watchlist.map((row) => [row.symbol, row.id])), [watchlist]);
  const selectedUniverse = universeOptions.find((option) => option.code === universe);
  const filtered = useMemo(() => stocks.filter((stock) => (sector === "All sectors" || stock.sector === sector) && `${stock.symbol} ${stock.name ?? ""}`.toLowerCase().includes(query.toLowerCase())).sort((a, b) => sort === "symbol" ? a.symbol.localeCompare(b.symbol) : sort === "rsi" ? (b.rsi_14 ?? -Infinity) - (a.rsi_14 ?? -Infinity) : (b.change_percent ?? -Infinity) - (a.change_percent ?? -Infinity)), [query, sector, sort, stocks]);

  if (loading) return <PageSkeleton />;
  if (error || !breadth) return <DataState kind="error" title="Market data unavailable" description="The end-of-day market snapshot could not be loaded." />;

  async function toggleWatch(symbol: string) {
    setWatchBusy(symbol);
    setWatchError(null);
    try {
      const existing = watchedMap.get(symbol);
      if (existing != null) {
        await watchlistApi.remove(existing);
        setWatchlist((items) => items.filter((item) => item.id !== existing));
      } else {
        await watchlistApi.add(symbol);
        setWatchlist(await watchlistApi.list());
      }
    } catch {
      setWatchError(`Could not update ${symbol} in your watchlist.`);
    } finally {
      setWatchBusy(null);
    }
  }

  const columns: Column<MarketStockSnapshot>[] = [
    { key: "symbol", header: "Instrument", render: (row) => <Link href={`/market/${encodeURIComponent(row.symbol)}`} className="block min-w-40 font-semibold text-foreground hover:text-primary"><span>{row.symbol}</span><span className="mt-0.5 block truncate text-[11px] font-normal text-muted-foreground">{row.name ?? "Name unavailable"}</span></Link> },
    { key: "sector", header: "Sector", render: (row) => <span className="text-xs text-muted-foreground">{row.sector ?? "—"}</span> },
    { key: "price", header: "Price", align: "right", render: (row) => <span className="font-medium tabular-nums">{money(row.close)}</span> },
    { key: "change", header: "1D", align: "right", render: (row) => <TrendValue compact value={row.change_percent}>{pct(row.change_percent)}</TrendValue> },
    { key: "rsi", header: "RSI 14", align: "right", render: (row) => row.rsi_14?.toFixed(1) ?? "—" },
    { key: "trend", header: "Trend", render: (row) => row.trend ? <StatusBadge label={row.trend} tone={row.trend === "bullish" ? "positive" : row.trend === "bearish" ? "negative" : "neutral"} /> : <span className="text-xs text-muted-foreground">—</span> },
    { key: "sentiment", header: "News", align: "right", render: (row) => { const value = sentimentMap.get(row.symbol); return <TrendValue compact value={value}>{value == null ? "—" : value.toFixed(2)}</TrendValue>; } },
    { key: "volume", header: "Volume", align: "right", render: (row) => row.volume?.toLocaleString("en-IN") ?? "—" },
    { key: "watch", header: <span className="sr-only">Watchlist</span>, align: "right", render: (row) => { const watched = watchedMap.has(row.symbol); return <Button type="button" variant="ghost" size="icon-xs" disabled={watchBusy === row.symbol} aria-label={watched ? `Remove ${row.symbol} from watchlist` : `Add ${row.symbol} to watchlist`} onClick={() => toggleWatch(row.symbol)}>{watched ? <BookmarkCheck className="size-4 text-primary" /> : <BookmarkPlus className="size-4 text-muted-foreground" />}</Button>; } },
  ];

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Market intelligence" title="Market Intelligence" description="Scan participation, technical regimes, sentiment, and catalysts across a membership-aware NSE research universe." actions={<label className="grid gap-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"><span>Research universe</span><select aria-label="Research universe" value={universe} onChange={(event) => { setLoading(true); setError(false); setUniverse(event.target.value as UniverseCode); }} className="h-9 min-w-40 rounded-lg border border-input bg-background px-3 text-sm font-medium normal-case tracking-normal text-foreground">{universeOptions.length === 0 ? <option value="NIFTY100">NIFTY 100</option> : universeOptions.map((option) => <option key={option.code} value={option.code}>{option.label} · {option.active_constituents}/{option.expected_constituents}</option>)}</select></label>} />
      {selectedUniverse && !selectedUniverse.initialized && <div role="status" className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3 text-xs text-warning">{selectedUniverse.label} is not fully synchronized: {selectedUniverse.active_constituents} of {selectedUniverse.expected_constituents} constituents are active. Results remain scoped to validated members only.</div>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Advancers" value={breadth.advancers} tone="positive" sub={`${breadth.total} priced stocks`} /><MetricCard label="Decliners" value={breadth.decliners} tone="negative" sub={`${breadth.unchanged} unchanged`} /><MetricCard label="A/D ratio" value={breadth.advance_decline_ratio?.toFixed(2) ?? "—"} tone={toneOf((breadth.advance_decline_ratio ?? 1) - 1)} /><MetricCard label="Average RSI" value={technical?.average_rsi?.toFixed(1) ?? "—"} sub={`${technical?.stocks_with_indicators ?? 0} with indicators`} /></div>

      <Panel>
        <SectionHeader title="Equity screener" description={`${filtered.length} of ${stocks.length} instruments · prices and indicators are end-of-day`} action={<ArrowDownUp className="size-4 text-muted-foreground" />} />
        <div className="my-4 flex flex-col gap-2 sm:flex-row">
          <label className="relative flex-1"><span className="sr-only">Search stocks</span><Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search symbol or company" className="pl-8" /></label>
          <select aria-label="Filter by sector" value={sector} onChange={(event) => setSector(event.target.value)} className="h-9 rounded-lg border border-input bg-background px-3 text-sm"><option>All sectors</option>{sectors.map((item) => <option key={item.sector}>{item.sector}</option>)}</select>
          <select aria-label="Sort stocks" value={sort} onChange={(event) => setSort(event.target.value as SortKey)} className="h-9 rounded-lg border border-input bg-background px-3 text-sm"><option value="change">1D change</option><option value="rsi">RSI</option><option value="symbol">Symbol</option></select>
        </div>
        {watchError && <p role="status" className="mb-3 text-xs text-warning">{watchError}</p>}
        <DataTable columns={columns} rows={filtered} rowKey={(row) => row.symbol} emptyMessage="No instruments match these filters." caption="Tracked market instruments with price, technical, and sentiment metrics" />
      </Panel>

      <Panel><StockHeatmap stocks={heatmap} /></Panel>
      <div className="grid gap-4 xl:grid-cols-[1.35fr_1fr]"><Panel><SectorRotation rows={rotation} /></Panel><TechnicalSummaryCard summary={technical} /></div>
      <div className="grid gap-4 xl:grid-cols-[1fr_1.35fr]"><EconomicEventsCard calendar={calendar} /><Panel><SectionHeader title="Evidence-backed signals" description="Deterministic ranking; AI provides explanation only." /><div className="mt-4 grid gap-3 md:grid-cols-2">{aiUnavailable ? <div className="md:col-span-2"><AIAnalysisState status="unavailable" message="AI analysis is temporarily unavailable. The market data above is still current." /></div> : recs.length + risks.length === 0 ? <div className="md:col-span-2"><AIAnalysisState status="empty" message="No watch or avoid signals met the recommendation thresholds for this session." /></div> : [...recs, ...risks].slice(0, 4).map((item) => <AIInsightCard key={`${item.action}-${item.symbol}`} title={item.symbol} narrative={item.explanation} action={item.action} confidence={item.confidence} evidence={{ evidence: item.evidence, risks: item.risks, confidence: item.confidence, historicalContext: item.historical_context }} />)}</div></Panel></div>
    </div>
  );
}
