"use client";

import dynamic from "next/dynamic";

export interface DonutSlice {
  label: string;
  value: number;
  percent: number;
}

const PlotlyDonut = dynamic(
  () => import("@/components/plotly-donut").then((module) => module.PlotlyDonut),
  {
    ssr: false,
    loading: () => (
      <div
        role="status"
        className="h-[180px] w-full animate-pulse rounded-md bg-muted/40"
      >
        <span className="sr-only">Loading sector allocation chart…</span>
      </div>
    ),
  },
);

/** Browser-only Plotly allocation chart with an SSR-safe loading shell. */
export function DonutChart({
  slices,
  size = 180,
}: {
  slices: DonutSlice[];
  size?: number;
}) {
  return <PlotlyDonut slices={slices} size={size} />;
}
