"use client";

/**
 * Market Intelligence page (Phase 7) — Analytics page template.
 *
 * Overview breadth, a sector heatmap, gainers/losers tables, and AI analysis
 * (evidence-backed watch/avoid recommendations with Show Evidence). Market
 * reads are public; recommendations are user-scoped. All data is live.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { AIAnalysisState } from "@/components/AIAnalysisState";
import { DataTable, type Column } from "@/components/DataTable";
import { Heatmap } from "@/components/Heatmap";
import { EconomicEventsCard, TechnicalSummaryCard } from "@/components/MarketContext";
import { MetricCard } from "@/components/MetricCard";
import { AnalyticsPageTemplate } from "@/components/templates/AnalyticsPageTemplate";
import {
  intelligenceApi,
  marketApi,
  type Breadth,
  type EconomicCalendar,
  type Quote,
  type Recommendation,
  type SectorOverview,
  type TechnicalSummary,
} from "@/lib/api";
import { money, pct, signClass } from "@/lib/utils";

const quoteColumns: Column<Quote>[] = [
  { key: "symbol", header: "Symbol", render: (q) => <span className="font-medium">{q.symbol}</span> },
  { key: "name", header: "Name", render: (q) => q.name ?? "—" },
  { key: "price", header: "Price", align: "right", render: (q) => money(q.close) },
  {
    key: "change",
    header: "Change",
    align: "right",
    render: (q) => <span className={signClass(q.change_percent)}>{pct(q.change_percent)}</span>,
  },
];

export default function MarketPage() {
  const [breadth, setBreadth] = useState<Breadth | null>(null);
  const [gainers, setGainers] = useState<Quote[]>([]);
  const [losers, setLosers] = useState<Quote[]>([]);
  const [sectors, setSectors] = useState<SectorOverview[]>([]);
  const [technical, setTechnical] = useState<TechnicalSummary | null>(null);
  const [calendar, setCalendar] = useState<EconomicCalendar | null>(null);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [risks, setRisks] = useState<Recommendation[]>([]);
  const [aiUnavailable, setAiUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [b, g, l, s, t, e] = await Promise.all([
          marketApi.breadth(),
          marketApi.gainers(5),
          marketApi.losers(5),
          marketApi.sectors(),
          marketApi.technicalSummary(),
          marketApi.economicEvents(14),
        ]);
        if (cancelled) return;
        setBreadth(b);
        setGainers(g);
        setLosers(l);
        setSectors(s);
        setTechnical(t);
        setCalendar(e);
        // Recommendations are user-scoped and best-effort — don't fail the page.
        try {
          const r = await intelligenceApi.recommendations();
          if (!cancelled) {
            setRecs(r.watchlist);
            setRisks(r.risk_alerts);
            setAiUnavailable(false);
          }
        } catch {
          if (!cancelled) setAiUnavailable(true);
        }
      } catch {
        if (!cancelled) setError("Could not load market data.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading market intelligence…</p>;
  }
  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  const summaryCards = breadth && (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      <MetricCard label="Advancers" value={breadth.advancers} tone="positive" />
      <MetricCard label="Decliners" value={breadth.decliners} tone="negative" />
      <MetricCard label="Unchanged" value={breadth.unchanged} tone="neutral" />
      <MetricCard
        label="A/D Ratio"
        value={breadth.advance_decline_ratio == null ? "—" : breadth.advance_decline_ratio.toFixed(2)}
        tone={breadth.advance_decline_ratio == null ? "default" : breadth.advance_decline_ratio >= 1 ? "positive" : "negative"}
      />
    </div>
  );

  const charts = (
    <div className="space-y-6">
      <Heatmap
        cells={sectors.map((s) => ({
          label: s.sector,
          value: s.average_change_percent,
          sub: `${s.stock_count} stock${s.stock_count === 1 ? "" : "s"}`,
        }))}
      />
      <div className="grid gap-6 xl:grid-cols-2">
        <TechnicalSummaryCard summary={technical} />
        <EconomicEventsCard calendar={calendar} />
      </div>
    </div>
  );

  const aiAnalysis = aiUnavailable ? (
    <AIAnalysisState
      status="unavailable"
      message="AI analysis is temporarily unavailable. The market data above is still current."
    />
  ) : recs.length === 0 && risks.length === 0 ? (
    <AIAnalysisState
      status="empty"
      message="No watch or avoid signals met the recommendation thresholds for this session."
    />
  ) : (
    <div className="grid gap-4 lg:grid-cols-2">
      {[...recs, ...risks].map((r) => (
        <AIInsightCard
          key={`${r.action}-${r.symbol}`}
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
  );

  const tables = (
    <div className="space-y-8">
      <div>
        <h4 className="mb-2 text-sm font-semibold">Top Gainers</h4>
        <DataTable columns={quoteColumns} rows={gainers} rowKey={(q) => q.symbol} emptyMessage="No gainers yet." />
      </div>
      <div>
        <h4 className="mb-2 text-sm font-semibold">Top Losers</h4>
        <DataTable columns={quoteColumns} rows={losers} rowKey={(q) => q.symbol} emptyMessage="No losers yet." />
      </div>
      <p className="text-sm text-muted-foreground">
        See how today compares to the past on the{" "}
        <Link href="/history" className="text-blue-600 hover:underline">Historical Similarity</Link> page.
      </p>
    </div>
  );

  return (
    <AnalyticsPageTemplate
      title="Market Intelligence"
      subtitle="End-of-day breadth, technicals, events, sectors, movers, and AI analysis"
      summaryCards={summaryCards}
      charts={charts}
      aiAnalysis={aiAnalysis}
      tables={tables}
    />
  );
}
