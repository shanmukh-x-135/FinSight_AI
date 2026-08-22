"use client";

import type { Data, Layout } from "plotly.js";
import { useMemo } from "react";

import { PlotlyFigure } from "@/components/plotly-figure";
import type { IndicatorPoint, PricePoint, SentimentDaily, SimilarityResult } from "@/lib/api";

export function PriceChart({ prices, indicators = [], candlestick = true }: { prices: PricePoint[]; indicators?: IndicatorPoint[]; candlestick?: boolean }) {
  const data = useMemo<Data[]>(() => {
    const dates = prices.map((point) => point.date);
    const price: Data = candlestick
      ? { type: "candlestick", x: dates, open: prices.map((p) => p.open), high: prices.map((p) => p.high), low: prices.map((p) => p.low), close: prices.map((p) => p.close), name: "Price", increasing: { line: { color: "#22c55e" } }, decreasing: { line: { color: "#f43f5e" } } }
      : { type: "scatter", mode: "lines", x: dates, y: prices.map((p) => p.close), name: "Close", line: { color: "#60a5fa", width: 2 } };
    const traces: Data[] = [price];
    if (indicators.length) {
      traces.push(
        { type: "scatter", mode: "lines", x: indicators.map((p) => p.date), y: indicators.map((p) => p.ema_20), name: "EMA 20", line: { color: "#f59e0b", width: 1.2 } },
        { type: "scatter", mode: "lines", x: indicators.map((p) => p.date), y: indicators.map((p) => p.ema_50), name: "EMA 50", line: { color: "#a78bfa", width: 1.2 } },
      );
    }
    return traces;
  }, [candlestick, indicators, prices]);
  const layout = useMemo<Partial<Layout>>(() => ({ xaxis: { rangeslider: { visible: false }, type: "date" }, yaxis: { tickprefix: "₹", fixedrange: true }, hovermode: "x unified" }), []);
  return <PlotlyFigure ariaLabel="Daily stock price chart with moving averages" data={data} layout={layout} height={380} empty={prices.length < 2} />;
}

export function VolumeChart({ prices }: { prices: PricePoint[] }) {
  const data = useMemo<Data[]>(() => [{ type: "bar", x: prices.map((p) => p.date), y: prices.map((p) => p.volume), marker: { color: prices.map((p, index) => index === 0 || p.close >= prices[index - 1].close ? "rgba(34,197,94,.65)" : "rgba(244,63,94,.65)" ) }, hovertemplate: "%{x}<br>%{y:,}<extra></extra>" }], [prices]);
  return <PlotlyFigure ariaLabel="Daily traded volume chart" data={data} layout={{ margin: { t: 8, r: 16, b: 38, l: 54 }, yaxis: { fixedrange: true }, showlegend: false }} height={180} empty={prices.length < 2} />;
}

export function SentimentChart({ series }: { series: SentimentDaily[] }) {
  const data = useMemo<Data[]>(() => [{ type: "bar", x: series.map((p) => p.date), y: series.map((p) => p.avg_sentiment), marker: { color: series.map((p) => p.avg_sentiment > 0 ? "#22c55e" : p.avg_sentiment < 0 ? "#f43f5e" : "#64748b") }, customdata: series.map((p) => p.article_count), hovertemplate: "%{x}<br>Score %{y:.2f}<br>%{customdata} articles<extra></extra>" }], [series]);
  return <PlotlyFigure ariaLabel="Daily news sentiment chart" data={data} layout={{ yaxis: { range: [-1, 1], fixedrange: true }, showlegend: false }} height={240} empty={series.length === 0} emptyMessage="No tagged sentiment history is available for this stock." />;
}

export function HistoryOutcomeChart({ result }: { result: SimilarityResult }) {
  const { statistics: stats } = result;
  const data = useMemo<Data[]>(() => [{ type: "bar", orientation: "h", y: ["Bullish", "Neutral", "Bearish"], x: [stats.bullish_count, stats.neutral_count, stats.bearish_count], marker: { color: ["#22c55e", "#64748b", "#f43f5e"] }, text: [stats.bullish_count, stats.neutral_count, stats.bearish_count].map(String), textposition: "auto", hovertemplate: "%{y}: %{x} sessions<extra></extra>" }], [stats]);
  return <PlotlyFigure ariaLabel="Outcomes after historically similar market sessions" data={data} layout={{ margin: { t: 8, r: 16, b: 38, l: 68 }, xaxis: { fixedrange: true }, showlegend: false }} height={220} empty={stats.sample_size === 0} />;
}

export function ContributionChart({ holdings }: { holdings: { symbol: string; unrealized_pnl: number | null }[] }) {
  const rows = useMemo(() => holdings.filter((h) => h.unrealized_pnl != null).sort((a, b) => Math.abs(b.unrealized_pnl!) - Math.abs(a.unrealized_pnl!)).slice(0, 10).reverse(), [holdings]);
  const data = useMemo<Data[]>(() => [{ type: "bar", orientation: "h", y: rows.map((h) => h.symbol), x: rows.map((h) => h.unrealized_pnl), marker: { color: rows.map((h) => h.unrealized_pnl! >= 0 ? "#22c55e" : "#f43f5e") }, hovertemplate: "%{y}<br>₹%{x:,.0f}<extra></extra>" }], [rows]);
  return <PlotlyFigure ariaLabel="Holding contribution to unrealized profit and loss" data={data} layout={{ margin: { t: 8, r: 16, b: 38, l: 76 }, xaxis: { tickprefix: "₹", fixedrange: true }, showlegend: false }} height={280} empty={rows.length === 0} emptyMessage="Contribution appears once holdings have current prices." />;
}
