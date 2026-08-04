"use client";

/**
 * Historical Similarity page (Phase 7) — Analytics page template.
 *
 * Surfaces Phase 4's deterministic engine: the sessions most similar to today
 * and what actually happened next, with the statistics framed explicitly as
 * historical context — not a forecast. The narrative here is a factual
 * description of the returned numbers, not an LLM prediction.
 */

import { useEffect, useState } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { DataTable, type Column } from "@/components/DataTable";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { AnalyticsPageTemplate } from "@/components/templates/AnalyticsPageTemplate";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { historyApi, type SimilarSession, type SimilarityResult } from "@/lib/api";
import { pct, signClass } from "@/lib/utils";

const outcomeClass = (o: string | null) =>
  o === "bullish" ? "text-green-600" : o === "bearish" ? "text-red-600" : "text-muted-foreground";

const sessionColumns: Column<SimilarSession>[] = [
  { key: "date", header: "Date", render: (s) => <span className="font-medium">{s.date}</span> },
  { key: "similarity", header: "Similarity", align: "right", render: (s) => `${(s.similarity_score * 100).toFixed(1)}%` },
  { key: "avg_return", header: "Session return", align: "right", render: (s) => <span className={signClass(s.avg_return)}>{pct(s.avg_return)}</span> },
  { key: "next_day", header: "Next day", align: "right", render: (s) => <span className={signClass(s.next_day_return)}>{pct(s.next_day_return)}</span> },
  { key: "outcome", header: "Outcome", align: "right", render: (s) => <span className={`capitalize ${outcomeClass(s.outcome)}`}>{s.outcome ?? "—"}</span> },
];

export default function HistoryPage() {
  const [result, setResult] = useState<SimilarityResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    historyApi
      .similar(10)
      .then((d) => !cancelled && setResult(d))
      .catch(() => !cancelled && setUnavailable(true))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading historical similarity…</p>;
  }

  if (unavailable || !result) {
    return (
      <AnalyticsPageTemplate
        title="Historical Similarity"
        subtitle="How today compares to past market sessions"
        summaryCards={
          <div className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
            The historical similarity index has not been built yet. It is created from
            accumulated market data and rebuilt on schedule.
          </div>
        }
      />
    );
  }

  const stats = result.statistics;
  const total = stats.bullish_count + stats.bearish_count + stats.neutral_count || 1;
  const bullPct = stats.bullish_probability == null ? null : Math.round(stats.bullish_probability * 100);

  const narrative =
    stats.sample_size === 0
      ? "No comparable historical sessions were found for today."
      : `Today's market resembles ${stats.sample_size} past session${stats.sample_size === 1 ? "" : "s"}. ` +
        (bullPct != null ? `${bullPct}% of them closed higher the next day` : "") +
        (stats.avg_next_day_return != null ? ` (average ${pct(stats.avg_next_day_return)}).` : ".") +
        " This is historical context, not a forecast.";

  const summaryCards = (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard label="Similar Sessions" value={stats.sample_size} sub={`top-${stats.k} nearest`} />
      <MetricCard
        label="Closed Higher"
        value={bullPct == null ? "—" : `${bullPct}%`}
        sub="next-day, historically"
        tone={bullPct == null ? "default" : bullPct >= 50 ? "positive" : "negative"}
      />
      <MetricCard
        label="Avg Next-Day"
        value={pct(stats.avg_next_day_return)}
        tone={toneOf(stats.avg_next_day_return)}
      />
      <MetricCard
        label="Best / Worst"
        value={`${pct(stats.best_case_return)} / ${pct(stats.worst_case_return)}`}
        sub="observed next-day range"
      />
    </div>
  );

  const charts = (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Next-day outcomes</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex h-3 overflow-hidden rounded-full">
            <div className="bg-green-500" style={{ width: `${(stats.bullish_count / total) * 100}%` }} />
            <div className="bg-muted-foreground/40" style={{ width: `${(stats.neutral_count / total) * 100}%` }} />
            <div className="bg-red-500" style={{ width: `${(stats.bearish_count / total) * 100}%` }} />
          </div>
          <div className="grid grid-cols-3 text-center text-sm">
            <div><p className="font-semibold text-green-600">{stats.bullish_count}</p><p className="text-xs text-muted-foreground">bullish</p></div>
            <div><p className="font-semibold text-muted-foreground">{stats.neutral_count}</p><p className="text-xs text-muted-foreground">neutral</p></div>
            <div><p className="font-semibold text-red-600">{stats.bearish_count}</p><p className="text-xs text-muted-foreground">bearish</p></div>
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Today&apos;s session ({result.query_date})</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 text-sm">
          <div><p className="text-muted-foreground">Avg return</p><p className={`font-semibold ${signClass(result.query_summary.avg_return)}`}>{pct(result.query_summary.avg_return)}</p></div>
          <div><p className="text-muted-foreground">% advancers</p><p className="font-semibold">{result.query_summary.pct_advancers.toFixed(1)}%</p></div>
          <div><p className="text-muted-foreground">A/D ratio</p><p className="font-semibold">{result.query_summary.advance_decline_ratio.toFixed(2)}</p></div>
          <div><p className="text-muted-foreground">Avg RSI</p><p className="font-semibold">{result.query_summary.avg_rsi.toFixed(1)}</p></div>
        </CardContent>
      </Card>
    </div>
  );

  const aiAnalysis = (
    <AIInsightCard
      title="Historical context"
      narrative={narrative}
      evidence={{
        evidence: result.similar_sessions
          .slice(0, 5)
          .map((s) => `${s.date}: ${(s.similarity_score * 100).toFixed(0)}% similar → next day ${pct(s.next_day_return)} (${s.outcome ?? "n/a"})`),
        extra: [
          { label: "Median next-day", value: pct(stats.median_next_day_return) },
          { label: "Std deviation", value: pct(stats.std_next_day_return) },
          ...(stats.ci_low != null && stats.ci_high != null
            ? [{ label: "95% CI", value: `${pct(stats.ci_low)} to ${pct(stats.ci_high)}` }]
            : []),
        ],
      }}
    />
  );

  const tables = (
    <DataTable
      columns={sessionColumns}
      rows={result.similar_sessions}
      rowKey={(s) => s.date}
      emptyMessage="No similar sessions found."
    />
  );

  return (
    <AnalyticsPageTemplate
      title="Historical Similarity"
      subtitle="How today compares to past market sessions — context, not prediction"
      summaryCards={summaryCards}
      charts={charts}
      aiAnalysis={aiAnalysis}
      tables={tables}
    />
  );
}
