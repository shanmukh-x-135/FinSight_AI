"use client";

import { useEffect, useRef } from "react";
import Plotly from "plotly.js-finance-dist-min";
import type { Config, Data, Layout } from "plotly.js";

import { DataState } from "@/components/workspace";

interface PlotlyFigureProps {
  ariaLabel: string;
  data: Data[];
  layout?: Partial<Layout>;
  height?: number;
  empty?: boolean;
  emptyMessage?: string;
}

const BASE_LAYOUT: Partial<Layout> = {
  autosize: true,
  margin: { t: 16, r: 16, b: 42, l: 54 },
  paper_bgcolor: "transparent",
  plot_bgcolor: "transparent",
  font: { color: "#94a3b8", family: "var(--font-geist-sans), sans-serif", size: 11 },
  hoverlabel: { bgcolor: "#0f172a", bordercolor: "#334155", font: { color: "#f8fafc" } },
  xaxis: { gridcolor: "rgba(148,163,184,.12)", zerolinecolor: "rgba(148,163,184,.2)" },
  yaxis: { gridcolor: "rgba(148,163,184,.12)", zerolinecolor: "rgba(148,163,184,.2)" },
  legend: { orientation: "h", y: 1.08, x: 0, font: { size: 11 } },
};

export function PlotlyFigure({
  ariaLabel,
  data,
  layout,
  height = 320,
  empty = false,
  emptyMessage = "Chart data is not available yet.",
}: PlotlyFigureProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node || empty) return;
    const merged: Partial<Layout> = {
      ...BASE_LAYOUT,
      ...layout,
      xaxis: { ...BASE_LAYOUT.xaxis, ...layout?.xaxis },
      yaxis: { ...BASE_LAYOUT.yaxis, ...layout?.yaxis },
    };
    const config: Partial<Config> = {
      displayModeBar: false,
      responsive: true,
      scrollZoom: false,
    };
    void Plotly.newPlot(node, data, merged, config);
    return () => Plotly.purge(node);
  }, [data, empty, layout]);

  if (empty) return <DataState kind="empty" title="No chart data" description={emptyMessage} />;

  return (
    <div
      ref={ref}
      role="img"
      aria-label={ariaLabel}
      style={{ height }}
      className="w-full min-w-0"
      data-testid="plotly-chart"
    />
  );
}
