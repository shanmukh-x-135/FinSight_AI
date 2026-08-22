import type { Breadth, HistoryStatistics } from "@/lib/api";

function SegmentBar({ values, label }: { values: { value: number; className: string }[]; label: string }) {
  const total = values.reduce((sum, item) => sum + item.value, 0);
  return <div role="img" aria-label={label} className="flex h-3 overflow-hidden rounded-full bg-muted">{total > 0 && values.map((item, index) => <span key={index} className={item.className} style={{ width: `${item.value / total * 100}%` }} />)}</div>;
}

export function ReportBreadthVisual({ breadth }: { breadth: Breadth }) {
  return <div className="rounded-lg border border-border/60 bg-muted/15 p-4"><p className="mb-3 text-xs font-medium text-muted-foreground">Participation balance</p><SegmentBar label={`${breadth.advancers} advancers, ${breadth.decliners} decliners, ${breadth.unchanged} unchanged`} values={[{ value: breadth.advancers, className: "bg-positive" }, { value: breadth.unchanged, className: "bg-muted-foreground/45" }, { value: breadth.decliners, className: "bg-negative" }]} /><div className="mt-3 flex flex-wrap gap-4 text-xs"><span className="text-positive">↑ {breadth.advancers} advancing</span><span className="text-muted-foreground">• {breadth.unchanged} flat</span><span className="text-negative">↓ {breadth.decliners} declining</span></div></div>;
}

export function ReportHistoryVisual({ statistics }: { statistics: HistoryStatistics }) {
  return <div className="rounded-lg border border-border/60 bg-muted/15 p-4"><p className="mb-3 text-xs font-medium text-muted-foreground">Observed analogue outcomes</p><SegmentBar label={`${statistics.bullish_count} bullish, ${statistics.neutral_count} neutral, ${statistics.bearish_count} bearish historical outcomes`} values={[{ value: statistics.bullish_count, className: "bg-positive" }, { value: statistics.neutral_count, className: "bg-muted-foreground/45" }, { value: statistics.bearish_count, className: "bg-negative" }]} /><div className="mt-3 grid grid-cols-3 text-center text-xs"><span><strong className="block text-positive">{statistics.bullish_count}</strong>bullish</span><span><strong className="block">{statistics.neutral_count}</strong>neutral</span><span><strong className="block text-negative">{statistics.bearish_count}</strong>bearish</span></div></div>;
}

export function ReportPortfolioVisual({ health, diversification }: { health: number | null | undefined; diversification: number | null | undefined }) {
  const rows = [{ label: "Health score", value: health }, { label: "Diversification score", value: diversification }];
  return <div className="grid gap-3 rounded-lg border border-border/60 bg-muted/15 p-4 sm:grid-cols-2">{rows.map((row) => <div key={row.label}><div className="flex justify-between text-xs"><span className="text-muted-foreground">{row.label}</span><strong>{row.value == null ? "—" : `Score ${Math.round(row.value)}/100`}</strong></div><div className="mt-2 h-2 overflow-hidden rounded-full bg-muted"><span className="block h-full rounded-full bg-primary" style={{ width: `${Math.max(0, Math.min(100, row.value ?? 0))}%` }} /></div></div>)}</div>;
}

export function ReportSentimentVisual({ labels }: { labels: (string | undefined)[] }) {
  const counts = labels.reduce((result, label) => { if (label === "positive") result.positive += 1; else if (label === "negative") result.negative += 1; else result.neutral += 1; return result; }, { positive: 0, neutral: 0, negative: 0 });
  return <div className="mb-4 rounded-lg border border-border/60 bg-muted/15 p-4"><p className="mb-3 text-xs font-medium text-muted-foreground">Notable-news sentiment</p><SegmentBar label={`${counts.positive} positive, ${counts.neutral} neutral, ${counts.negative} negative notable news items`} values={[{ value: counts.positive, className: "bg-positive" }, { value: counts.neutral, className: "bg-muted-foreground/45" }, { value: counts.negative, className: "bg-negative" }]} /></div>;
}
