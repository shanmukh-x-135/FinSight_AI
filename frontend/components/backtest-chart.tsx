"use client";

import { useEffect, useRef } from "react";
import Plotly from "plotly.js-finance-dist-min";
import type { Config, Data, Layout } from "plotly.js";

import type { Backtest } from "@/lib/api";

export function BacktestChart({ result }: { result: Backtest }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    const dates = result.equity_curve.map((point) => point.date);
    const equityByDate = new Map(result.equity_curve.map((point) => [point.date, point.equity]));
    const entries: { x: string; y: number }[] = [];
    const exits: { x: string; y: number }[] = [];
    for (const trade of result.trades) {
      const entryEquity = equityByDate.get(trade.entry_date);
      const exitEquity = equityByDate.get(trade.exit_date);
      if (entryEquity != null) entries.push({ x: trade.entry_date, y: entryEquity });
      if (exitEquity != null) exits.push({ x: trade.exit_date, y: exitEquity });
    }
    const data: Data[] = [
      { type: "scatter", mode: "lines", name: "Strategy", x: dates, y: result.equity_curve.map((point) => point.equity), line: { color: "#3b82f6", width: 2 } },
      { type: "scatter", mode: "lines", name: result.benchmark_symbol, x: dates, y: result.equity_curve.map((point) => point.benchmark_equity), line: { color: "#94a3b8", dash: "dot", width: 1.5 } },
      { type: "scatter", mode: "markers", name: "Entries", x: entries.map((point) => point.x), y: entries.map((point) => point.y), marker: { color: "#22c55e", symbol: "triangle-up", size: 8 } },
      { type: "scatter", mode: "markers", name: "Exits", x: exits.map((point) => point.x), y: exits.map((point) => point.y), marker: { color: "#ef4444", symbol: "triangle-down", size: 8 } },
      { type: "scatter", mode: "lines", name: "Drawdown", x: dates, y: result.equity_curve.map((point) => point.drawdown_percent), yaxis: "y2", fill: "tozeroy", line: { color: "#f59e0b", width: 1 } },
    ];
    const layout: Partial<Layout> = { autosize: true, margin: { t: 12, r: 50, b: 40, l: 58 }, paper_bgcolor: "transparent", plot_bgcolor: "transparent", font: { color: "#94a3b8", size: 11 }, hovermode: "x unified", legend: { orientation: "h", y: 1.12 }, xaxis: { gridcolor: "rgba(148,163,184,.12)" }, yaxis: { title: { text: "Equity" }, gridcolor: "rgba(148,163,184,.12)" }, yaxis2: { title: { text: "Drawdown %" }, overlaying: "y", side: "right", showgrid: false } };
    const config: Partial<Config> = { responsive: true, displaylogo: false, modeBarButtonsToRemove: ["lasso2d", "select2d"] };
    void Plotly.newPlot(node, data, layout, config);
    return () => { Plotly.purge(node); };
  }, [result]);
  return <div ref={ref} role="img" aria-label="Strategy equity, benchmark, drawdown, and trade markers" className="h-[360px] w-full" data-testid="backtest-chart" />;
}
