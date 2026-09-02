"use client";

import { Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { ContextualAIActions } from "@/components/contextual-ai-actions";
import { PriceChart, SentimentChart, VolumeChart } from "@/components/finance-charts";
import { NewsEvidenceList } from "@/components/news-evidence-list";
import { Button } from "@/components/ui/button";
import { DataState, MetricStrip, PageHeader, PageSkeleton, Panel, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";
import { intelligenceApi, marketApi, newsApi, watchlistApi, type IndicatorPoint, type MovementAttribution, type PricePoint, type Recommendation, type StockDetail, type StockSentiment } from "@/lib/api";
import { money, pct } from "@/lib/utils";

const compactMoney = (value: number | null | undefined) => value == null ? "—" : new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", notation: "compact", maximumFractionDigits: 2 }).format(value);

export default function StockDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [detail, setDetail] = useState<StockDetail | null>(null);
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [indicators, setIndicators] = useState<IndicatorPoint[]>([]);
  const [sentiment, setSentiment] = useState<StockSentiment | null>(null);
  const [attribution, setAttribution] = useState<MovementAttribution | null>(null);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [watchState, setWatchState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  useEffect(() => {
    let active = true;
    Promise.all([marketApi.detail(symbol), marketApi.prices(symbol, 180), marketApi.indicators(symbol, 180), newsApi.stockSentiment(symbol), marketApi.attribution(symbol)])
      .then(([nextDetail, nextPrices, nextIndicators, nextSentiment, nextAttribution]) => { if (active) { setDetail(nextDetail); setPrices(nextPrices); setIndicators(nextIndicators); setSentiment(nextSentiment); setAttribution(nextAttribution); } })
      .catch(() => active && setError(true))
      .finally(() => active && setLoading(false));
    intelligenceApi.recommendations().then((data) => { if (active) setRecommendation([...data.watchlist, ...data.risk_alerts].find((item) => item.symbol === symbol) ?? null); }).catch(() => undefined);
    return () => { active = false; };
  }, [symbol]);

  const latestIndicator = indicators.at(-1);
  const rangePosition = useMemo(() => { const f = detail?.fundamentals; if (!detail?.close || !f?.week52_low || !f.week52_high || f.week52_high === f.week52_low) return null; return Math.min(100, Math.max(0, ((detail.close - f.week52_low) / (f.week52_high - f.week52_low)) * 100)); }, [detail]);

  async function addToWatchlist() {
    setWatchState("saving");
    try { await watchlistApi.add(symbol); setWatchState("saved"); } catch { setWatchState("error"); }
  }

  if (loading) return <PageSkeleton />;
  if (error || !detail) return <DataState kind="error" title="Stock research unavailable" description={`Could not load the research record for ${symbol}.`} />;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow={`${detail.exchange ?? "NSE"} · ${detail.sector ?? "Sector unavailable"}`} title={`${detail.symbol} · ${detail.name ?? "Company name unavailable"}`} description={`${detail.industry ?? "Industry unavailable"} · Last market session ${detail.date ?? "not available"}`} actions={<><Button variant="outline" size="sm" onClick={addToWatchlist} disabled={watchState === "saving" || watchState === "saved"}>{watchState === "saving" ? <RefreshCw className="size-4 animate-spin motion-reduce:animate-none" /> : <Plus className="size-4" />}{watchState === "saved" ? "Added" : watchState === "error" ? "Try again" : "Watchlist"}</Button><ContextualAIActions actions={[{ label: "Ask AI", prompt: `Explain why ${symbol} moved using only current source-linked and technical evidence.` }, { label: "Compare sector", prompt: `Compare ${symbol} with its sector using current deterministic market evidence.` }, { label: "Find analogues", prompt: `Explain the market-regime historical analogues relevant to the current context for ${symbol}; do not imply a stock-specific pattern.` }, { label: "Strategy context", prompt: `Assess how ${symbol}'s current evidence relates to the saved deterministic strategy rules; do not invent a signal.` }]} /></>} />

      <Panel className="overflow-hidden p-0">
        <div className="flex flex-col gap-4 px-4 pt-4 sm:flex-row sm:items-end sm:justify-between sm:px-5 sm:pt-5"><div><p className="text-label text-muted-foreground">Last traded price</p><div className="mt-1 flex flex-wrap items-baseline gap-3"><p className="financial-number text-3xl font-semibold tracking-tight">{money(detail.close)}</p><TrendValue value={detail.change_percent}>{pct(detail.change_percent)} · {detail.change == null ? "change unavailable" : money(detail.change)}</TrendValue></div></div><p className="text-xs text-muted-foreground">Daily OHLC · EMA 20 · EMA 50</p></div>
        <div className="px-1 sm:px-3"><PriceChart prices={prices} indicators={indicators} /></div>
        <div className="border-t border-border/45 px-1 pt-2 sm:px-3"><VolumeChart prices={prices} /></div>
      </Panel>

      <MetricStrip items={[{ label: "RSI 14", value: latestIndicator?.rsi_14?.toFixed(1) ?? "—", detail: latestIndicator?.rsi_14 == null ? "Indicator unavailable" : latestIndicator.rsi_14 >= 70 ? "Overbought zone" : latestIndicator.rsi_14 <= 30 ? "Oversold zone" : "Neutral range" }, { label: "P/E ratio", value: detail.fundamentals?.pe_ratio?.toFixed(1) ?? "—", detail: "Trailing valuation" }, { label: "EPS", value: detail.fundamentals?.eps == null ? "—" : money(detail.fundamentals.eps), detail: "Latest stored fundamentals" }, { label: "News sentiment", value: sentiment?.latest_sentiment?.toFixed(2) ?? "—", detail: sentiment?.availability === "available" ? `${sentiment.article_count} evidence-backed article${sentiment.article_count === 1 ? "" : "s"}` : "No relevant news found", tone: sentiment?.latest_sentiment == null ? "neutral" : sentiment.latest_sentiment >= 0 ? "positive" : "negative" }]} />

      {attribution && <Panel><SectionHeader title="Why did it move?" description="Likely contributors from deterministic evidence; associations are not proven causes." action={<StatusBadge label={attribution.evidence_conflict.consensus} tone={attribution.evidence_conflict.consensus === "bullish" ? "positive" : attribution.evidence_conflict.consensus === "bearish" ? "negative" : attribution.evidence_conflict.consensus === "mixed" ? "warning" : "neutral"} />} /><ol className="mt-4 grid gap-2 lg:grid-cols-2">{attribution.drivers.map((driver) => <li key={driver.category} className="rounded-lg border border-border/60 bg-muted/20 p-3"><div className="flex items-start gap-3"><span className="grid size-6 shrink-0 place-items-center rounded-full bg-primary/10 text-[11px] font-semibold text-primary">{driver.rank}</span><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center justify-between gap-2"><p className="text-sm font-semibold">{driver.label}</p><StatusBadge label={driver.relevance} tone={driver.relevance === "high" ? "info" : "neutral"} /></div><p className="mt-1 text-xs leading-5 text-muted-foreground">{driver.observation}</p></div></div></li>)}</ol><details className="mt-4 border-t border-border/60 pt-3 text-xs"><summary className="cursor-pointer font-medium text-primary">Review evidence conflicts</summary><div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">{attribution.evidence_conflict.signals.map((signal) => <div key={signal.source} className="rounded-md bg-muted/30 p-2"><div className="flex items-center justify-between gap-2"><span className="font-medium">{signal.source}</span><StatusBadge label={signal.direction} tone={signal.direction === "bullish" ? "positive" : signal.direction === "bearish" ? "negative" : "neutral"} /></div><p className="mt-1 leading-4 text-muted-foreground">{signal.observation}</p></div>)}</div></details></Panel>}

      <div className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
        <Panel><SectionHeader title="Technical snapshot" description={`Calculated through ${latestIndicator?.date ?? "the latest available session"}.`} /><div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[["EMA 20", latestIndicator?.ema_20], ["EMA 50", latestIndicator?.ema_50], ["MACD", latestIndicator?.macd], ["MACD signal", latestIndicator?.macd_signal], ["ATR 14", latestIndicator?.atr_14], ["Bollinger upper", latestIndicator?.bb_upper]].map(([label, value]) => <div key={String(label)} className="rounded-lg border border-border/60 bg-muted/20 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-semibold tabular-nums">{typeof value === "number" ? value.toFixed(2) : "—"}</p></div>)}</div></Panel>
        <Panel><SectionHeader title="52-week range" description="Position within stored fundamentals." />{rangePosition == null ? <div className="mt-4"><DataState kind="unavailable" title="Range unavailable" description="52-week fundamentals are not stored for this instrument." /></div> : <div className="mt-8"><div className="relative h-2 rounded-full bg-gradient-to-r from-negative via-warning to-positive"><span className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground" style={{ left: `${rangePosition}%` }} /></div><div className="mt-3 flex justify-between text-xs text-muted-foreground"><span>{money(detail.fundamentals?.week52_low)}</span><span>{money(detail.fundamentals?.week52_high)}</span></div><p className="mt-6 text-center text-sm"><strong>{rangePosition.toFixed(0)}%</strong> through the annual range</p></div>}</Panel>
      </div>

      <Panel><SectionHeader title="Fundamentals" description="Latest stored company fundamentals; unavailable fields remain explicit." /><dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-6">{[["Market cap", compactMoney(detail.fundamentals?.market_cap)], ["P/E ratio", detail.fundamentals?.pe_ratio?.toFixed(1) ?? "—"], ["EPS", detail.fundamentals?.eps == null ? "—" : money(detail.fundamentals.eps)], ["Dividend yield", detail.fundamentals?.dividend_yield == null ? "—" : `${detail.fundamentals.dividend_yield.toFixed(2)}%`], ["52-week high", money(detail.fundamentals?.week52_high)], ["52-week low", money(detail.fundamentals?.week52_low)]].map(([label, value]) => <div key={label} className="rounded-lg border border-border/60 bg-muted/20 p-3"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold tabular-nums">{value}</dd></div>)}</dl></Panel>

      <div className="grid gap-4 xl:grid-cols-[.75fr_1.25fr]"><Panel><SectionHeader title="News sentiment" description={sentiment?.availability === "available" ? `Aggregated from ${sentiment.article_count} article-level evidence record(s).` : "No relevant news found; unavailable is not neutral."} /><div className="mt-3"><SentimentChart series={sentiment?.series ?? []} /></div>{sentiment?.availability === "available" && <div className="mt-3 grid grid-cols-4 gap-2 border-t border-border/60 pt-3 text-center text-xs"><div><strong>{sentiment.positive_count}</strong><p className="text-muted-foreground">positive</p></div><div><strong>{sentiment.neutral_count}</strong><p className="text-muted-foreground">neutral</p></div><div><strong>{sentiment.negative_count}</strong><p className="text-muted-foreground">negative</p></div><div><strong>{Math.round((sentiment.confidence ?? 0) * 100)}%</strong><p className="text-muted-foreground">confidence</p></div></div>}</Panel><Panel><SectionHeader title="News evidence" description="Every sentiment reading links to its source, driver, excerpt, and matching confidence." /><div className="mt-4"><NewsEvidenceList evidence={sentiment?.evidence ?? []} /></div></Panel></div>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]"><Panel><SectionHeader title="AI research interpretation" description="Ranking remains deterministic; prose explains available evidence." />{recommendation ? <div className="mt-4"><AIInsightCard title={recommendation.symbol} narrative={recommendation.explanation} action={recommendation.action} confidence={recommendation.confidence} evidence={{ evidence: recommendation.evidence, risks: recommendation.risks, confidence: recommendation.confidence, historicalContext: recommendation.historical_context }} /></div> : <div className="mt-4"><DataState kind="empty" title="No active recommendation" description="This instrument did not cross a current watch or avoid threshold." /></div>}</Panel><Panel><SectionHeader title="Stock-specific analogues" description="Historical comparison capability." /><div className="mt-4"><DataState kind="unavailable" title="Not available for individual stocks" description="The current similarity index models market-wide sessions, not company-specific price patterns. No analogue is shown to avoid a misleading comparison." /></div><Link href="/history" className="mt-3 inline-block text-xs font-medium text-primary hover:underline">Open market historical research →</Link></Panel></div>
    </div>
  );
}
