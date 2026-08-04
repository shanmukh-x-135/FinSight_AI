"use client";

import Plot from "react-plotly.js";

import type { DonutSlice } from "@/components/donut-chart";

const COLORS = [
  "#2563eb",
  "#16a34a",
  "#d97706",
  "#dc2626",
  "#7c3aed",
  "#0891b2",
  "#db2777",
  "#65a30d",
];

export function PlotlyDonut({
  slices,
  size,
}: {
  slices: DonutSlice[];
  size: number;
}) {
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div
        role="img"
        aria-label="Sector allocation donut chart"
        style={{ width: size, height: size }}
        className="shrink-0"
      >
        <Plot
          data={[
            {
              type: "pie",
              labels: slices.map((slice) => slice.label),
              values: slices.map((slice) => slice.value),
              hole: 0.68,
              sort: false,
              direction: "clockwise",
              marker: { colors: COLORS, line: { color: "transparent", width: 1 } },
              textinfo: "none",
              hovertemplate: "%{label}<br>%{percent:.1%}<extra></extra>",
            },
          ]}
          layout={{
            autosize: true,
            margin: { t: 2, r: 2, b: 2, l: 2 },
            paper_bgcolor: "transparent",
            plot_bgcolor: "transparent",
            showlegend: false,
            transition: { duration: 0 },
            annotations: [
              {
                text: `${slices.length}<br>${slices.length === 1 ? "sector" : "sectors"}`,
                showarrow: false,
                font: { size: 13, color: "currentColor" },
              },
            ],
          }}
          config={{
            displayModeBar: false,
            responsive: true,
            scrollZoom: false,
          }}
          useResizeHandler
          style={{ width: "100%", height: "100%" }}
        />
      </div>

      <ul className="flex min-w-40 flex-col gap-2 text-sm" aria-label="Sector allocation legend">
        {slices.map((slice, index) => (
          <li key={slice.label} className="flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-2.5 rounded-sm"
              style={{ backgroundColor: COLORS[index % COLORS.length] }}
              aria-hidden
            />
            <span className="min-w-0 flex-1 truncate font-medium">{slice.label}</span>
            <span className="tabular-nums text-muted-foreground">
              {slice.percent.toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
