"use client";

import { useEffect, useState } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { DataTable, type Column } from "@/components/DataTable";
import { HistoryOutcomeChart } from "@/components/finance-charts";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { DataState, PageHeader, PageSkeleton, Panel, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";
import { historyApi, type SimilarSession, type SimilarityResult } from "@/lib/api";
import { ratioPct } from "@/lib/utils";

const columns: Column<SimilarSession>[] = [
  { key: "date", header: "Historical session", render: (row) => <span className="font-semibold">{row.date}</span> },
  { key: "similarity", header: "Similarity", align: "right", render: (row) => `${(row.similarity_score * 100).toFixed(1)}%` },
  { key: "session", header: "Session return", align: "right", render: (row) => <TrendValue compact value={row.avg_return}>{ratioPct(row.avg_return)}</TrendValue> },
  { key: "breadth", header: "Advancers", align: "right", render: (row) => ratioPct(row.pct_advancers, 1, false) },
  { key: "rsi", header: "Avg RSI", align: "right", render: (row) => row.avg_rsi.toFixed(1) },
  { key: "next", header: "Next session", align: "right", render: (row) => <TrendValue compact value={row.next_day_return}>{ratioPct(row.next_day_return)}</TrendValue> },
  { key: "outcome", header: "Outcome", render: (row) => <StatusBadge label={row.outcome ?? "unknown"} tone={row.outcome === "bullish" ? "positive" : row.outcome === "bearish" ? "negative" : "neutral"} /> },
];

export default function HistoryPage() {
  const [result, setResult] = useState<SimilarityResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => { let active = true; historyApi.similar(10).then((data) => active && setResult(data)).catch(() => active && setUnavailable(true)).finally(() => active && setLoading(false)); return () => { active = false; }; }, []);
  if (loading) return <PageSkeleton />;
  if (unavailable || !result) return <div className="space-y-5"><PageHeader eyebrow="Research" title="Historical Similarity" description="How the current market state compares with stored sessions." /><DataState kind="unavailable" title="Similarity index unavailable" description="The index is built from accumulated market sessions and rebuilt on schedule." /></div>;

  const stats = result.statistics;
  const bullPct = stats.bullish_probability == null ? null : Math.round(stats.bullish_probability * 100);
  const narrative = stats.sample_size === 0 ? "No comparable historical sessions were found for today." : `The current market resembles ${stats.sample_size} stored sessions. ${bullPct ?? "An unavailable share"}% closed higher on the following session, with an average next-session return of ${ratioPct(stats.avg_next_day_return)}. This is historical context, not a forecast.`;

  return <div className="space-y-5">
    <PageHeader eyebrow="Research" title="Historical Similarity" description="Nearest market-state analogues and their observed next-session outcomes — context, not prediction." />
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Comparable sessions" value={stats.sample_size} sub={`Top-${stats.k} nearest states`} /><MetricCard label="Closed higher" value={bullPct == null ? "—" : `${bullPct}%`} sub="Following session" tone={bullPct == null ? "default" : bullPct >= 50 ? "positive" : "negative"} /><MetricCard label="Average next session" value={ratioPct(stats.avg_next_day_return)} tone={toneOf(stats.avg_next_day_return)} /><MetricCard label="Observed range" value={`${ratioPct(stats.worst_case_return)} to ${ratioPct(stats.best_case_return)}`} sub="Worst to best" /></div>
    <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]"><Panel><SectionHeader title="Observed next-session outcomes" description={`${stats.sample_size} nearest sessions in the current result set.`} /><HistoryOutcomeChart result={result} /></Panel><Panel><SectionHeader title={`Current state · ${result.query_date}`} description="Normalized inputs used by the similarity engine." /><dl className="mt-6 grid grid-cols-2 gap-3">{[["Average return", ratioPct(result.query_summary.avg_return)], ["Advancers", ratioPct(result.query_summary.pct_advancers, 1, false)], ["A/D ratio", result.query_summary.advance_decline_ratio.toFixed(2)], ["Average RSI", result.query_summary.avg_rsi.toFixed(1)]].map(([label, value]) => <div key={label} className="rounded-lg border border-border/60 bg-muted/20 p-3"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold">{value}</dd></div>)}</dl>{stats.ci_low != null && stats.ci_high != null && <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 p-3"><p className="text-xs text-muted-foreground">95% confidence interval</p><p className="mt-1 text-sm font-semibold">{ratioPct(stats.ci_low)} to {ratioPct(stats.ci_high)}</p></div>}</Panel></div>
    <AIInsightCard title="Historical context" narrative={narrative} evidence={{ evidence: result.similar_sessions.slice(0, 5).map((row) => `${row.date}: ${(row.similarity_score * 100).toFixed(0)}% similar → ${ratioPct(row.next_day_return)} (${row.outcome ?? "n/a"})`), extra: [{ label: "Median next-session", value: ratioPct(stats.median_next_day_return) }, { label: "Standard deviation", value: ratioPct(stats.std_next_day_return) }] }} />
    <Panel><SectionHeader title="Nearest sessions" description="Ranked by normalized feature-vector distance." /><div className="mt-4"><DataTable columns={columns} rows={result.similar_sessions} rowKey={(row) => row.date} emptyMessage="No similar sessions found." caption="Historical market sessions ranked by similarity" /></div></Panel>
  </div>;
}
