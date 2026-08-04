"use client";

/**
 * Dashboard — the primary home screen (Phase 7).
 *
 * One batched call to /dashboard/summary backs the whole page: market breadth
 * cards, the deterministic AI market summary, the user's portfolio snapshot,
 * watchlist quotes, today's evidence-backed opportunities (each with a Show
 * Evidence expander), risk alerts, and market movers. All data is real.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { DashboardWatchlist } from "@/components/DashboardWatchlist";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { StockCard } from "@/components/StockCard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { dashboardApi, type DashboardSummary } from "@/lib/api";
import { money, pct } from "@/lib/utils";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    dashboardApi
      .summary()
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setError("Could not load your dashboard."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading dashboard…</p>;
  }
  if (error || !data) {
    return <p className="text-sm text-red-600">{error ?? "No data."}</p>;
  }

  const { market, portfolio, opportunities, risk_alerts } = data;
  const breadth = market.breadth;

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h2 className="text-2xl font-bold">Dashboard</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Your daily, evidence-backed market intelligence.
        </p>
      </div>

      {/* Summary metrics */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          label="Market Breadth"
          value={`${breadth.advancers} / ${breadth.decliners}`}
          sub={`${breadth.total} tracked · ${breadth.unchanged} flat`}
        />
        <MetricCard
          label="Advance / Decline"
          value={breadth.advance_decline_ratio == null ? "—" : breadth.advance_decline_ratio.toFixed(2)}
          sub={breadth.advance_decline_ratio != null && breadth.advance_decline_ratio >= 1 ? "advancers lead" : "decliners lead"}
          tone={breadth.advance_decline_ratio == null ? "default" : breadth.advance_decline_ratio >= 1 ? "positive" : "negative"}
        />
        <MetricCard
          label="Portfolio Value"
          value={portfolio ? money(portfolio.total_value) : "—"}
          sub={portfolio ? pct(portfolio.total_return_percent) : "No portfolio yet"}
          tone={portfolio ? toneOf(portfolio.total_return_percent) : "default"}
        />
        <MetricCard
          label="Opportunities"
          value={opportunities.length}
          sub="watch-rated today"
        />
      </div>

      {/* AI market summary */}
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          AI Market Summary
        </h3>
        <AIInsightCard title="Today's market" narrative={data.ai_market_summary} />
      </section>

      <section>
        <DashboardWatchlist items={data.watchlist} />
      </section>

      {/* Today's opportunities */}
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Today&apos;s Opportunities
        </h3>
        {opportunities.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No watch-rated opportunities today. Check back after the next market ingestion.
          </p>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {opportunities.map((r) => (
              <AIInsightCard
                key={r.symbol}
                title={`${r.symbol}${r.name ? ` · ${r.name}` : ""}`}
                narrative={r.explanation}
                action={r.action}
                confidence={r.confidence}
                evidence={{
                  evidence: r.evidence,
                  risks: r.risks,
                  confidence: r.confidence,
                  historicalContext: r.historical_context,
                }}
              />
            ))}
          </div>
        )}
      </section>

      {/* Risk alerts */}
      {risk_alerts.length > 0 && (
        <section>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Risk Alerts
          </h3>
          <div className="grid gap-4 lg:grid-cols-2">
            {risk_alerts.map((r) => (
              <AIInsightCard
                key={r.symbol}
                title={`${r.symbol}${r.name ? ` · ${r.name}` : ""}`}
                narrative={r.explanation}
                action={r.action}
                confidence={r.confidence}
                evidence={{
                  evidence: r.evidence,
                  risks: r.risks,
                  confidence: r.confidence,
                  historicalContext: r.historical_context,
                }}
              />
            ))}
          </div>
        </section>
      )}

      {/* Movers */}
      <section className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Top Gainers
          </h3>
          <div className="space-y-2">
            {market.gainers.length === 0 && (
              <p className="text-sm text-muted-foreground">No movers yet.</p>
            )}
            {market.gainers.map((q) => (
              <StockCard key={q.symbol} symbol={q.symbol} name={q.name} price={q.close} changePercent={q.change_percent} />
            ))}
          </div>
        </div>
        <div>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
            Top Losers
          </h3>
          <div className="space-y-2">
            {market.losers.length === 0 && (
              <p className="text-sm text-muted-foreground">No movers yet.</p>
            )}
            {market.losers.map((q) => (
              <StockCard key={q.symbol} symbol={q.symbol} name={q.name} price={q.close} changePercent={q.change_percent} />
            ))}
          </div>
        </div>
      </section>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Go deeper</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-4 text-sm">
          <Link href="/market" className="text-blue-600 hover:underline">Market Intelligence →</Link>
          <Link href="/history" className="text-blue-600 hover:underline">Historical Similarity →</Link>
          <Link href="/portfolio" className="text-blue-600 hover:underline">Portfolio →</Link>
        </CardContent>
      </Card>
    </div>
  );
}
