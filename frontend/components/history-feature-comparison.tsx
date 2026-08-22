import type { SessionSummary, SimilarSession } from "@/lib/api";
import { cn, ratioPct } from "@/lib/utils";

interface Feature {
  label: string;
  current: number;
  analogue: number;
  position: (value: number) => number;
  format: (value: number) => string;
}

const clamp = (value: number) => Math.max(0, Math.min(100, value));

export function HistoryFeatureComparison({ current, analogue }: { current: SessionSummary; analogue: SimilarSession }) {
  const features: Feature[] = [
    { label: "Session return", current: current.avg_return, analogue: analogue.avg_return, position: (value) => clamp((value * 100 + 3) / 6 * 100), format: (value) => ratioPct(value) },
    { label: "Advancing stocks", current: current.pct_advancers, analogue: analogue.pct_advancers, position: (value) => clamp(value * 100), format: (value) => ratioPct(value, 1, false) },
    { label: "Advance / decline", current: current.advance_decline_ratio, analogue: analogue.advance_decline_ratio, position: (value) => clamp(value / 3 * 100), format: (value) => value.toFixed(2) },
    { label: "Average RSI", current: current.avg_rsi, analogue: analogue.avg_rsi, position: clamp, format: (value) => value.toFixed(1) },
  ];

  return (
    <div role="img" aria-label={`Feature comparison between the current session and ${analogue.date}`} className="space-y-5">
      <div className="flex flex-wrap gap-4 text-xs text-muted-foreground"><span><i className="mr-1.5 inline-block size-2 rounded-full bg-primary" />Current session</span><span><i className="mr-1.5 inline-block size-2 rounded-full bg-chart-4" />{analogue.date} · {(analogue.similarity_score * 100).toFixed(1)}% similar</span></div>
      {features.map((feature) => <div key={feature.label}><div className="mb-2 flex items-center justify-between gap-4 text-xs"><span className="font-medium">{feature.label}</span><span className="text-muted-foreground"><strong className="text-primary">Now {feature.format(feature.current)}</strong> / <strong className="text-chart-4">Then {feature.format(feature.analogue)}</strong></span></div><div className="relative h-2 rounded-full bg-muted"><span className={cn("absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-chart-4")} style={{ left: `${feature.position(feature.analogue)}%` }} /><span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-primary" style={{ left: `${feature.position(feature.current)}%` }} /></div></div>)}
    </div>
  );
}
