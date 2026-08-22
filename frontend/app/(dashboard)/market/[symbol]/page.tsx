"use client";

import { Bot, Plus, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { PriceChart, SentimentChart, VolumeChart } from "@/components/finance-charts";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { buttonVariants, Button } from "@/components/ui/button";
import { DataState, PageHeader, PageSkeleton, Panel, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";
import { intelligenceApi, marketApi, newsApi, watchlistApi, type IndicatorPoint, type NewsArticle, type PricePoint, type Recommendation, type StockDetail, type StockSentiment } from "@/lib/api";
import { cn, money, pct } from "@/lib/utils";

export default function StockDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol);
  const [detail, setDetail] = useState<StockDetail | null>(null);
  const [prices, setPrices] = useState<PricePoint[]>([]);
  const [indicators, setIndicators] = useState<IndicatorPoint[]>([]);
  const [sentiment, setSentiment] = useState<StockSentiment | null>(null);
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [watchState, setWatchState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  useEffect(() => {
    let active = true;
    Promise.all([marketApi.detail(symbol), marketApi.prices(symbol, 180), marketApi.indicators(symbol, 180), newsApi.stockSentiment(symbol), newsApi.recent(100)])
      .then(([nextDetail, nextPrices, nextIndicators, nextSentiment, recent]) => { if (active) { setDetail(nextDetail); setPrices(nextPrices); setIndicators(nextIndicators); setSentiment(nextSentiment); setNews(recent.filter((article) => article.tags.includes(symbol))); } })
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
      <PageHeader eyebrow={`${detail.exchange ?? "NSE"} · ${detail.sector ?? "Sector unavailable"}`} title={`${detail.symbol} · ${detail.name ?? "Company name unavailable"}`} description={`${detail.industry ?? "Industry unavailable"} · Last market session ${detail.date ?? "not available"}`} actions={<><Button variant="outline" size="sm" onClick={addToWatchlist} disabled={watchState === "saving" || watchState === "saved"}>{watchState === "saving" ? <RefreshCw className="size-4 animate-spin" /> : <Plus className="size-4" />}{watchState === "saved" ? "Added" : watchState === "error" ? "Try again" : "Watchlist"}</Button><Link href={`/chat?prompt=${encodeURIComponent(`Explain the current evidence for ${symbol}`)}`} className={cn(buttonVariants({ size: "sm" }))}><Bot className="size-4" />Ask AI</Link></>} />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6"><MetricCard label="Last price" value={money(detail.close)} sub={detail.date ?? "—"} /><MetricCard label="1D change" value={pct(detail.change_percent)} tone={toneOf(detail.change_percent)} sub={detail.change == null ? "—" : money(detail.change)} /><MetricCard label="RSI 14" value={latestIndicator?.rsi_14?.toFixed(1) ?? "—"} sub={latestIndicator?.rsi_14 == null ? "Indicator unavailable" : latestIndicator.rsi_14 >= 70 ? "Overbought zone" : latestIndicator.rsi_14 <= 30 ? "Oversold zone" : "Neutral range"} /><MetricCard label="P/E" value={detail.fundamentals?.pe_ratio?.toFixed(1) ?? "—"} sub="Trailing valuation" /><MetricCard label="EPS" value={detail.fundamentals?.eps == null ? "—" : money(detail.fundamentals.eps)} /><MetricCard label="News sentiment" value={sentiment?.latest_sentiment?.toFixed(2) ?? "—"} tone={toneOf(sentiment?.latest_sentiment)} sub={`${sentiment?.series.reduce((sum, row) => sum + row.article_count, 0) ?? 0} tagged articles`} /></div>

      <Panel><SectionHeader title="Price structure" description="Daily OHLC with EMA 20 and EMA 50 overlays." /><PriceChart prices={prices} indicators={indicators} /><div className="border-t border-border/60 pt-3"><VolumeChart prices={prices} /></div></Panel>

      <div className="grid gap-4 xl:grid-cols-[1.35fr_.65fr]">
        <Panel><SectionHeader title="Technical snapshot" description={`Calculated through ${latestIndicator?.date ?? "the latest available session"}.`} /><div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{[["EMA 20", latestIndicator?.ema_20], ["EMA 50", latestIndicator?.ema_50], ["MACD", latestIndicator?.macd], ["MACD signal", latestIndicator?.macd_signal], ["ATR 14", latestIndicator?.atr_14], ["Bollinger upper", latestIndicator?.bb_upper]].map(([label, value]) => <div key={String(label)} className="rounded-lg border border-border/60 bg-muted/20 p-3"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 font-semibold tabular-nums">{typeof value === "number" ? value.toFixed(2) : "—"}</p></div>)}</div></Panel>
        <Panel><SectionHeader title="52-week range" description="Position within stored fundamentals." />{rangePosition == null ? <div className="mt-4"><DataState kind="unavailable" title="Range unavailable" description="52-week fundamentals are not stored for this instrument." /></div> : <div className="mt-8"><div className="relative h-2 rounded-full bg-gradient-to-r from-negative via-warning to-positive"><span className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-foreground" style={{ left: `${rangePosition}%` }} /></div><div className="mt-3 flex justify-between text-xs text-muted-foreground"><span>{money(detail.fundamentals?.week52_low)}</span><span>{money(detail.fundamentals?.week52_high)}</span></div><p className="mt-6 text-center text-sm"><strong>{rangePosition.toFixed(0)}%</strong> through the annual range</p></div>}</Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2"><Panel><SectionHeader title="News sentiment" description="Daily aggregate from tagged financial coverage." /><div className="mt-3"><SentimentChart series={sentiment?.series ?? []} /></div></Panel><Panel><SectionHeader title="Latest tagged news" description="Source links open outside FinSight." /><div className="mt-3 divide-y divide-border/60">{news.length ? news.slice(0, 6).map((article) => <a key={article.id} href={article.url} target="_blank" rel="noreferrer" className="block py-3 hover:text-primary"><div className="flex items-start justify-between gap-3"><p className="text-sm font-medium leading-5">{article.title}</p><StatusBadge label={article.sentiment_label} tone={article.sentiment_score > 0 ? "positive" : article.sentiment_score < 0 ? "negative" : "neutral"} /></div><p className="mt-1 text-xs text-muted-foreground">{article.source} · {article.published_at ? new Date(article.published_at).toLocaleDateString("en-IN") : "Date unavailable"}</p></a>) : <DataState kind="empty" title="No tagged coverage" description="No recent article is tagged to this stock." />}</div></Panel></div>

      <Panel><SectionHeader title="AI research interpretation" description="Ranking remains deterministic; prose explains available evidence." />{recommendation ? <div className="mt-4"><AIInsightCard title={recommendation.symbol} narrative={recommendation.explanation} action={recommendation.action} confidence={recommendation.confidence} evidence={{ evidence: recommendation.evidence, risks: recommendation.risks, confidence: recommendation.confidence, historicalContext: recommendation.historical_context }} /></div> : <div className="mt-4"><DataState kind="empty" title="No active recommendation" description="This instrument did not cross a current watch or avoid threshold." /></div>}</Panel>
    </div>
  );
}
