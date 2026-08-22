"use client";

import { ArrowRight, BrainCircuit, ShieldAlert, Telescope } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { DashboardWatchlist } from "@/components/DashboardWatchlist";
import { Heatmap } from "@/components/Heatmap";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { buttonVariants } from "@/components/ui/button";
import { DataState, PageHeader, PageSkeleton, Panel, SectionHeader, TrendValue } from "@/components/workspace";
import { dashboardApi, type DashboardSummary } from "@/lib/api";
import { marketNarrativeEvidence } from "@/lib/evidence";
import { cn, money, pct } from "@/lib/utils";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  function load() {
    setLoading(true);
    setError(false);
    dashboardApi.summary().then(setData).catch(() => setError(true)).finally(() => setLoading(false));
  }
  useEffect(() => {
    let active = true;
    dashboardApi.summary().then((next) => active && setData(next)).catch(() => active && setError(true)).finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  if (loading) return <PageSkeleton />;
  if (error || !data) return <DataState kind="error" title="Overview unavailable" description="The financial workspace could not be loaded." onRetry={load} />;

  const { market, portfolio, opportunities, risk_alerts: risks } = data;
  const breadth = market.breadth;
  const observed = breadth.advancers + breadth.decliners + breadth.unchanged;
  const advanceWidth = observed ? (breadth.advancers / observed) * 100 : 0;
  const declineWidth = observed ? (breadth.decliners / observed) * 100 : 0;
  const sentimentBySymbol = Object.fromEntries(data.sentiment.map((row) => [row.symbol, row.latest_sentiment]));
  const sentimentCounts = data.sentiment.reduce((counts, row) => {
    if (row.latest_sentiment == null || Math.abs(row.latest_sentiment) < 0.05) counts.neutral += 1;
    else if (row.latest_sentiment > 0) counts.positive += 1;
    else counts.negative += 1;
    return counts;
  }, { positive: 0, neutral: 0, negative: 0 });
  const sentimentTotal = sentimentCounts.positive + sentimentCounts.neutral + sentimentCounts.negative;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Daily intelligence" title="Overview" description="A compact read on market participation, portfolio exposure, and evidence-backed signals." actions={<Link href="/chat" className={cn(buttonVariants({ size: "sm" }))}><BrainCircuit className="size-4" />Ask FinSight</Link>} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Market breadth" value={`${breadth.advancers} / ${breadth.decliners}`} sub={`${breadth.total} tracked · ${breadth.unchanged} unchanged`} tone={toneOf((breadth.advance_decline_ratio ?? 1) - 1)} />
        <MetricCard label="A/D ratio" value={breadth.advance_decline_ratio?.toFixed(2) ?? "—"} sub={breadth.advance_decline_ratio == null ? "No decliners in sample" : breadth.advance_decline_ratio >= 1 ? "Advancers lead" : "Decliners lead"} tone={toneOf((breadth.advance_decline_ratio ?? 1) - 1)} />
        <MetricCard label="Portfolio value" value={portfolio ? money(portfolio.total_value) : "—"} sub={portfolio ? pct(portfolio.total_return_percent) : "Create a portfolio to track exposure"} tone={toneOf(portfolio?.total_return_percent)} />
        <MetricCard label="Active signals" value={opportunities.length + risks.length} sub={`${opportunities.length} watch · ${risks.length} risk`} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(280px,.85fr)]">
        <Panel className="surface-grid min-h-72 overflow-hidden">
          <SectionHeader title="Market participation" description="End-of-day movement across the tracked Indian equity universe." action={<Link href="/market" className="text-xs font-medium text-primary hover:underline">Open screener</Link>} />
          <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_220px] lg:items-end">
            <div>
              <p className="text-xs text-muted-foreground">Advance / decline balance</p>
              <div className="mt-2 flex items-baseline gap-3"><span className="text-4xl font-semibold tracking-tight">{breadth.advance_decline_ratio?.toFixed(2) ?? "—"}</span><TrendValue value={(breadth.advance_decline_ratio ?? 1) - 1}>{breadth.advance_decline_ratio != null && breadth.advance_decline_ratio >= 1 ? "Broad participation" : "Narrow participation"}</TrendValue></div>
              <div className="mt-8 flex h-3 overflow-hidden rounded-full bg-muted" role="img" aria-label={`${breadth.advancers} advancers, ${breadth.decliners} decliners, ${breadth.unchanged} unchanged`}><span className="bg-positive" style={{ width: `${advanceWidth}%` }} /><span className="bg-negative" style={{ width: `${declineWidth}%` }} /><span className="flex-1 bg-muted-foreground/35" /></div>
              <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2 text-xs"><span><i className="mr-1.5 inline-block size-2 rounded-sm bg-positive" />{breadth.advancers} advancing</span><span><i className="mr-1.5 inline-block size-2 rounded-sm bg-negative" />{breadth.decliners} declining</span><span className="text-muted-foreground"><i className="mr-1.5 inline-block size-2 rounded-sm bg-muted-foreground/35" />{breadth.unchanged} flat</span></div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {[...market.gainers.slice(0, 2), ...market.losers.slice(0, 2)].map((quote) => <Link key={quote.symbol} href={`/market/${encodeURIComponent(quote.symbol)}`} className="rounded-lg border border-border/70 bg-background/65 p-3 transition-colors hover:border-primary/45"><p className="truncate text-xs font-semibold">{quote.symbol}</p><p className="mt-1 text-sm">{money(quote.close)}</p><TrendValue compact value={quote.change_percent}>{pct(quote.change_percent)}</TrendValue></Link>)}
            </div>
          </div>
        </Panel>

        <Panel>
          <SectionHeader title="Intelligence brief" description="Narrative is generated from deterministic analytics." />
          <p className="mt-5 text-sm leading-6 text-foreground/90">{data.ai_market_summary}</p>
          <details className="mt-5 border-t border-border/70 pt-4 text-xs"><summary className="cursor-pointer font-medium text-primary">Review evidence</summary><ul className="mt-3 space-y-2 text-muted-foreground">{marketNarrativeEvidence(market).map((item) => <li key={item}>• {item}</li>)}</ul></details>
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
        <Panel><SectionHeader title="Sector performance" description="Ranked end-of-day movement across sectors with priced constituents." action={<Link href="/market" className="text-xs font-medium text-primary hover:underline">Explore market</Link>} /><div className="mt-4"><Heatmap cells={data.sectors.map((item) => ({ label: item.sector, value: item.average_change_percent, sub: `${item.stock_count} stocks` }))} emptyMessage="Sector performance appears after market prices are ingested." /></div></Panel>
        <Panel><SectionHeader title="News tone" description="Latest daily sentiment across the active universe." /><div className="mt-6"><div role="img" aria-label={`${sentimentCounts.positive} positive, ${sentimentCounts.neutral} neutral, ${sentimentCounts.negative} negative sentiment readings`} className="flex h-3 overflow-hidden rounded-full bg-muted">{sentimentTotal > 0 && <><span className="bg-positive" style={{ width: `${sentimentCounts.positive / sentimentTotal * 100}%` }} /><span className="bg-muted-foreground/45" style={{ width: `${sentimentCounts.neutral / sentimentTotal * 100}%` }} /><span className="bg-negative" style={{ width: `${sentimentCounts.negative / sentimentTotal * 100}%` }} /></>}</div><div className="mt-4 grid grid-cols-3 text-center text-xs"><div><p className="text-lg font-semibold text-positive">{sentimentCounts.positive}</p><p className="text-muted-foreground">positive</p></div><div><p className="text-lg font-semibold">{sentimentCounts.neutral}</p><p className="text-muted-foreground">neutral</p></div><div><p className="text-lg font-semibold text-negative">{sentimentCounts.negative}</p><p className="text-muted-foreground">negative</p></div></div><div className="mt-5 border-t border-border/60 pt-4 text-xs text-muted-foreground"><span className="font-medium text-foreground">Technical regime:</span> {data.technical.above_ema20_count} of {data.technical.stocks_with_indicators} above EMA 20 · {data.technical.positive_macd_count} positive MACD</div></div></Panel>
      </div>

      <DashboardWatchlist items={data.watchlist} sentimentBySymbol={sentimentBySymbol} />

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel><SectionHeader title="Research opportunities" description="Signals that passed the deterministic watch threshold." action={<Telescope className="size-4 text-primary" />} /><div className="mt-4 space-y-3">{opportunities.length ? opportunities.slice(0, 3).map((item) => <AIInsightCard key={item.symbol} title={`${item.symbol}${item.name ? ` · ${item.name}` : ""}`} narrative={item.explanation} action={item.action} confidence={item.confidence} evidence={{ evidence: item.evidence, risks: item.risks, confidence: item.confidence, historicalContext: item.historical_context }} />) : <DataState kind="empty" title="No watch signals" description="No tracked stock met the current evidence threshold." />}</div></Panel>
        <Panel><SectionHeader title="Risk monitor" description="Portfolio and watchlist signals requiring attention." action={<ShieldAlert className="size-4 text-negative" />} /><div className="mt-4 space-y-3">{risks.length ? risks.slice(0, 3).map((item) => <AIInsightCard key={item.symbol} title={`${item.symbol}${item.name ? ` · ${item.name}` : ""}`} narrative={item.explanation} action={item.action} confidence={item.confidence} evidence={{ evidence: item.evidence, risks: item.risks, confidence: item.confidence, historicalContext: item.historical_context }} />) : <DataState kind="empty" title="No active risk alerts" description="No tracked position crossed the current deterministic risk threshold." />}</div></Panel>
      </div>

      <div className="flex justify-end"><Link href="/history" className={cn(buttonVariants({ variant: "ghost" }))}>Compare today with historical analogues <ArrowRight className="size-4" /></Link></div>
    </div>
  );
}
