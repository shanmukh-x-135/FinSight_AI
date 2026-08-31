"use client";

import { useEffect, useState } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { DataTable, type Column } from "@/components/DataTable";
import { HistoryOutcomeChart } from "@/components/finance-charts";
import { HistoryFeatureComparison } from "@/components/history-feature-comparison";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { DataState, PageHeader, PageSkeleton, Panel, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";
import { historyApi, type SimilarSession, type SimilarityResult } from "@/lib/api";
import { ratioPct } from "@/lib/utils";

const columns: Column<SimilarSession>[] = [
  { key: "date", header: "Historical session", render: (row) => <span className="font-semibold">{row.date}</span> },
  { key: "similarity", header: "Similarity", align: "right", render: (row) => `${(row.similarity_score * 100).toFixed(1)}%` },
  { key: "session", header: "Session return", align: "right", render: (row) => <TrendValue compact value={row.avg_return}>{ratioPct(row.avg_return)}</TrendValue> },
  { key: "breadth", header: "Advancers", align: "right", render: (row) => ratioPct(row.pct_advancers, 1, false) },
  { key: "rsi", header: "Median RSI", align: "right", render: (row) => (row.median_rsi ?? row.avg_rsi).toFixed(1) },
  { key: "next", header: "Next session", align: "right", render: (row) => <TrendValue compact value={row.next_day_return}>{ratioPct(row.next_day_return)}</TrendValue> },
  { key: "forward", header: "Next 5 sessions", align: "right", render: (row) => <TrendValue compact value={row.forward_5_session_return ?? null}>{ratioPct(row.forward_5_session_return ?? null)}</TrendValue> },
  { key: "outcome", header: "Outcome", render: (row) => <StatusBadge label={row.outcome ?? "unknown"} tone={row.outcome === "bullish" ? "positive" : row.outcome === "bearish" ? "negative" : "neutral"} /> },
];

export default function HistoryPage() {
  const [result, setResult] = useState<SimilarityResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);
  useEffect(() => { let active = true; historyApi.similar(10).then((data) => active && setResult(data)).catch(() => active && setUnavailable(true)).finally(() => active && setLoading(false)); return () => { active = false; }; }, []);
  if (loading) return <PageSkeleton />;
  if (unavailable || !result) return <div className="space-y-5"><PageHeader eyebrow="Research" title="Historical Similarity" description="How the current market state compares with stored sessions." /><DataState kind="unavailable" title="Similarity index unavailable" description="The index is built from accumulated market sessions and rebuilt on schedule." /></div>;

  const stats = result.statistics;
  const summary = result.query_summary;
  const bullPct = stats.bullish_probability == null ? null : Math.round(stats.bullish_probability * 100);
  const narrative = stats.sample_size === 0 ? "No comparable historical sessions were found for today." : `The current market resembles ${stats.sample_size} stored sessions. ${bullPct ?? "An unavailable share"}% closed higher on the following session, with an average next-session return of ${ratioPct(stats.avg_next_day_return)}. This is historical context, not a forecast.`;
  const selected = result.similar_sessions.find((session) => session.date === selectedDate) ?? result.similar_sessions[0];

  return <div className="space-y-5">
    <PageHeader eyebrow="Research" title="Historical Similarity" description="Robust, constituent-order-independent market-regime analogues and their observed outcomes — context, not prediction." />
    <div className="flex flex-wrap gap-2" aria-label="Similarity model metadata">
      <StatusBadge label={result.feature_version ?? "legacy feature model"} tone="neutral" />
      {result.vector_dimension != null && <StatusBadge label={`${result.vector_dimension} regime features`} tone="neutral" />}
      {summary.membership_mode && <StatusBadge label={summary.membership_mode === "effective_membership" ? "Effective membership" : "Available-data proxy"} tone={summary.membership_mode === "effective_membership" ? "positive" : "warning"} />}
      {summary.coverage_ratio != null && <StatusBadge label={`${ratioPct(summary.coverage_ratio, 0, false)} constituent coverage`} tone={summary.coverage_ratio >= .9 ? "positive" : "warning"} />}
    </div>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><MetricCard label="Comparable sessions" value={stats.sample_size} sub={`Top-${stats.k} nearest states`} /><MetricCard label="Closed higher" value={bullPct == null ? "—" : `${bullPct}%`} sub="Following session" tone={bullPct == null ? "default" : bullPct >= 50 ? "positive" : "negative"} /><MetricCard label="Average next session" value={ratioPct(stats.avg_next_day_return)} tone={toneOf(stats.avg_next_day_return)} /><MetricCard label="Observed range" value={`${ratioPct(stats.worst_case_return)} to ${ratioPct(stats.best_case_return)}`} sub="Worst to best" /></div>
    <div className="grid gap-4 xl:grid-cols-[1.2fr_.8fr]"><Panel><SectionHeader title="Observed next-session outcomes" description={`${stats.sample_size} nearest sessions in the current result set.`} /><HistoryOutcomeChart result={result} /></Panel><Panel><SectionHeader title={`Current state · ${result.query_date}`} description="Transparent regime inputs and data quality." /><dl className="mt-6 grid grid-cols-2 gap-3">{[["Equal-weight return", ratioPct(summary.avg_return)], ["Advancers", ratioPct(summary.pct_advancers, 1, false)], ["A/D ratio", summary.advance_decline_ratio.toFixed(2)], ["Median RSI", (summary.median_rsi ?? summary.avg_rsi).toFixed(1)], ["Breadth regime", summary.breadth_regime ?? "—"], ["Momentum regime", summary.momentum_regime ?? "—"], ["Volatility regime", summary.volatility_regime ?? "—"], ["Relative volume", summary.median_relative_volume == null ? "—" : `${summary.median_relative_volume.toFixed(2)}×`]].map(([label, value]) => <div key={label} className="rounded-lg border border-border/60 bg-muted/20 p-3"><dt className="text-xs text-muted-foreground">{label}</dt><dd className="mt-1 font-semibold capitalize">{value}</dd></div>)}</dl>{stats.ci_low != null && stats.ci_high != null && <div className="mt-4 rounded-lg border border-primary/20 bg-primary/5 p-3"><p className="text-xs text-muted-foreground">95% confidence interval</p><p className="mt-1 text-sm font-semibold">{ratioPct(stats.ci_low)} to {ratioPct(stats.ci_high)}</p></div>}</Panel></div>
    {selected && <Panel><SectionHeader title={`Why ${selected.date} is similar`} description="Deterministic grouped factors, divergences, observed forward outcomes, and a side-by-side input comparison." action={<label className="text-xs text-muted-foreground">Compare session <select aria-label="Compare historical session" value={selected.date} onChange={(event) => setSelectedDate(event.currentTarget.value)} className="ml-2 rounded-md border border-input bg-background px-2 py-1 text-foreground">{result.similar_sessions.map((session) => <option key={session.date} value={session.date}>{session.date} · {(session.similarity_score * 100).toFixed(0)}%</option>)}</select></label>} /><div className="mt-4 grid gap-3 sm:grid-cols-3"><div className="rounded-lg border border-border/60 p-3"><p className="text-xs text-muted-foreground">Next session</p><p className="mt-1 font-semibold">{ratioPct(selected.next_day_return)}</p></div><div className="rounded-lg border border-border/60 p-3"><p className="text-xs text-muted-foreground">Next 5 sessions</p><p className="mt-1 font-semibold">{ratioPct(selected.forward_5_session_return ?? null)}</p></div><div className="rounded-lg border border-border/60 p-3"><p className="text-xs text-muted-foreground">Maximum drawdown</p><p className="mt-1 font-semibold">{ratioPct(selected.forward_5_session_drawdown ?? null)}</p></div></div><div className="mt-5 grid gap-6 xl:grid-cols-[.8fr_1.2fr]"><div className="space-y-4"><div><p className="text-xs font-semibold uppercase tracking-[.16em] text-muted-foreground">Closest regime factors</p><div className="mt-2 space-y-2">{(selected.matching_factors ?? []).map((factor) => <div key={factor.factor} className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3"><p className="text-sm font-semibold capitalize">{factor.factor} · {(factor.similarity_score * 100).toFixed(0)}%</p><p className="mt-1 text-xs text-muted-foreground">{factor.explanation}</p></div>)}</div></div><div><p className="text-xs font-semibold uppercase tracking-[.16em] text-muted-foreground">Largest differences</p><div className="mt-2 space-y-2">{(selected.divergence_factors ?? []).map((factor) => <div key={factor.factor} className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3"><p className="text-sm font-semibold capitalize">{factor.factor} · {(factor.similarity_score * 100).toFixed(0)}%</p><p className="mt-1 text-xs text-muted-foreground">{factor.explanation}</p></div>)}</div></div></div><HistoryFeatureComparison current={summary} analogue={selected} /></div></Panel>}
    <AIInsightCard title="Historical context" narrative={narrative} evidence={{ evidence: result.similar_sessions.slice(0, 5).map((row) => `${row.date}: ${(row.similarity_score * 100).toFixed(0)}% similar → ${ratioPct(row.next_day_return)} (${row.outcome ?? "n/a"})`), extra: [{ label: "Median next-session", value: ratioPct(stats.median_next_day_return) }, { label: "Standard deviation", value: ratioPct(stats.std_next_day_return) }] }} />
    <Panel><SectionHeader title="Nearest sessions" description="Ranked by normalized feature-vector distance." /><div className="mt-4"><DataTable columns={columns} rows={result.similar_sessions} rowKey={(row) => row.date} emptyMessage="No similar sessions found." caption="Historical market sessions ranked by similarity" /></div></Panel>
  </div>;
}
