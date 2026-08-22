"use client";

/**
 * Report detail (Phase 8) — the Report page template: Executive Summary →
 * Analysis → Recommendations, each recommendation carrying its real evidence
 * via Show Evidence. Export buttons stream the Markdown/PDF the backend renders
 * from the same stored sections, so the file matches what's on screen.
 */

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { StockCard } from "@/components/StockCard";
import { ReportPageTemplate } from "@/components/templates/ReportPageTemplate";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  downloadReport,
  reportsApi,
  type Recommendation,
  type Report,
} from "@/lib/api";
import {
  executiveNarrativeEvidence,
  historicalNarrativeEvidence,
  marketNarrativeEvidence,
  portfolioNarrativeEvidence,
} from "@/lib/evidence";
import { money, pct, ratioPct } from "@/lib/utils";

function RecCard({ r }: { r: Recommendation }) {
  return (
    <AIInsightCard
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
  );
}

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);

  const [report, setReport] = useState<Report | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [exporting, setExporting] = useState<"markdown" | "pdf" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    reportsApi
      .get(id)
      .then((d) => !cancelled && setReport(d))
      .catch(() => !cancelled && setNotFound(true))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [id]);

  async function onExport(fmt: "markdown" | "pdf") {
    setExporting(fmt);
    setExportError(null);
    try {
      await downloadReport(id, fmt);
    } catch {
      setExportError("Export failed. Please try again.");
    } finally {
      setExporting(null);
    }
  }

  if (loading) {
    return <p className="text-sm text-muted-foreground">Loading report…</p>;
  }
  if (notFound || !report) {
    return (
      <div className="mx-auto max-w-4xl">
        <p className="text-sm text-negative">Report not found.</p>
        <Link href="/reports" className="mt-2 inline-block text-sm text-primary hover:underline">
          ← Back to reports
        </Link>
      </div>
    );
  }

  const s = report.sections;
  const market = s.market_summary;
  const portfolio = s.portfolio_summary;
  const hist = s.historical_summary;
  const recs = s.recommendations ?? [];
  const alerts = s.risk_alerts ?? [];
  const news = s.news?.notable ?? [];

  const generated = s.meta?.generated_at ?? report.created_at;
  const generation = s.meta?.generation;
  const model = generation?.model_versions[0] ?? generation?.requested_models[0];
  const subtitle =
    `Report #${report.id} · Generated ${new Date(generated).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })}` +
    (s.meta?.llm_backend ? ` · ${s.meta.llm_backend}` : "") +
    (model ? ` · ${model}` : "") +
    (generation?.fallback_count ? ` · ${generation.fallback_count} fallback` : "") +
    (s.meta?.prompt_version ? ` · prompt v${s.meta.prompt_version}` : "");

  const actions = (
    <>
      <Link href="/reports">
        <Button variant="ghost" size="sm">← Back</Button>
      </Link>
      <Button variant="outline" size="sm" disabled={exporting !== null} onClick={() => onExport("markdown")}>
        {exporting === "markdown" ? "Exporting…" : "Export Markdown"}
      </Button>
      <Button variant="outline" size="sm" disabled={exporting !== null} onClick={() => onExport("pdf")}>
        {exporting === "pdf" ? "Exporting…" : "Export PDF"}
      </Button>
    </>
  );

  const executiveSummary = s.executive_summary && (
    <AIInsightCard
      title="Executive Summary"
      narrative={s.executive_summary}
      evidence={{ evidence: executiveNarrativeEvidence(s) }}
    />
  );

  const analysis = (
    <div className="space-y-4">
      {market && (
        <>
          {market.narrative && (
            <AIInsightCard
              title="Market Summary"
              narrative={market.narrative}
              evidence={{ evidence: marketNarrativeEvidence(market) }}
            />
          )}
          {market.breadth && (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <MetricCard label="Advancers" value={market.breadth.advancers} tone="positive" />
              <MetricCard label="Decliners" value={market.breadth.decliners} tone="negative" />
              <MetricCard label="Unchanged" value={market.breadth.unchanged} tone="neutral" />
              <MetricCard label="Tracked" value={market.breadth.total} />
              <MetricCard
                label="A/D Ratio"
                value={market.breadth.advance_decline_ratio == null ? "—" : market.breadth.advance_decline_ratio.toFixed(2)}
              />
            </div>
          )}
          {(market.gainers?.length || market.losers?.length) && (
            <div className="grid gap-4 lg:grid-cols-2">
              <div className="space-y-2">
                <p className="text-sm font-semibold">Top gainers</p>
                {(market.gainers ?? []).map((q) => (
                  <StockCard key={q.symbol} symbol={q.symbol} name={q.name} price={q.close} changePercent={q.change_percent} />
                ))}
              </div>
              <div className="space-y-2">
                <p className="text-sm font-semibold">Top losers</p>
                {(market.losers ?? []).map((q) => (
                  <StockCard key={q.symbol} symbol={q.symbol} name={q.name} price={q.close} changePercent={q.change_percent} />
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {portfolio && (
        <>
          {portfolio.narrative && (
            <AIInsightCard
              title="Portfolio Summary"
              narrative={portfolio.narrative}
              evidence={{ evidence: portfolioNarrativeEvidence(portfolio) }}
            />
          )}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <MetricCard label="Total Value" value={money(portfolio.total_value)} />
            <MetricCard label="Total Return" value={pct(portfolio.total_return_percent)} tone={toneOf(portfolio.total_return_percent)} />
            <MetricCard label="Health Score" value={portfolio.health_score == null ? "—" : Math.round(portfolio.health_score)} sub={`risk: ${portfolio.risk_level ?? "—"}`} />
            <MetricCard label="Diversification" value={portfolio.diversification_score == null ? "—" : `${Math.round(portfolio.diversification_score)}/100`} />
            <MetricCard label="Holdings" value={portfolio.number_of_holdings ?? "—"} />
          </div>
        </>
      )}

      {hist && (
        <>
          {hist.narrative && hist.statistics && (
            <AIInsightCard
              title="Historical Context"
              narrative={hist.narrative}
              evidence={{ evidence: historicalNarrativeEvidence(hist.statistics) }}
            />
          )}
          {hist.statistics && (
            <div className="grid gap-4 sm:grid-cols-3">
              <MetricCard label="Similar Sessions" value={hist.statistics.sample_size} sub={`top-${hist.statistics.k} nearest`} />
              <MetricCard
                label="Closed Higher"
                value={hist.statistics.bullish_probability == null ? "—" : `${Math.round(hist.statistics.bullish_probability * 100)}%`}
              />
              <MetricCard label="Avg Next-Day" value={ratioPct(hist.statistics.avg_next_day_return)} tone={toneOf(hist.statistics.avg_next_day_return)} />
            </div>
          )}
          <p className="text-xs italic text-muted-foreground">
            Historical context, not a forecast.
          </p>
        </>
      )}

      {!market && !portfolio && !hist && (
        <p className="text-sm text-muted-foreground">No analysis sections in this report.</p>
      )}
    </div>
  );

  const recommendations = (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        {recs.length === 0 ? (
          <p className="text-sm text-muted-foreground">No watch-rated opportunities in this report.</p>
        ) : (
          recs.map((r) => <RecCard key={`w-${r.symbol}`} r={r} />)
        )}
      </div>
      {alerts.length > 0 && (
        <div>
          <p className="mb-3 text-sm font-semibold">Risk alerts</p>
          <div className="grid gap-4 lg:grid-cols-2">
            {alerts.map((r) => <RecCard key={`a-${r.symbol}`} r={r} />)}
          </div>
        </div>
      )}
    </div>
  );

  const appendix = news.length > 0 && (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Notable news</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2 text-sm">
          {news.slice(0, 5).map((a, i) => (
            <li key={i} className="flex flex-wrap items-center gap-2">
              <span>{a.title}</span>
              {a.sentiment_label && (
                <span className="rounded-full bg-muted px-2 py-0.5 text-xs capitalize text-muted-foreground">
                  {a.sentiment_label}
                </span>
              )}
              {a.tags?.length ? <span className="text-xs text-muted-foreground">{a.tags.join(", ")}</span> : null}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );

  return (
    <>
      {exportError && (
        <p role="alert" className="mx-auto mb-3 max-w-4xl text-sm text-negative">{exportError}</p>
      )}
      <ReportPageTemplate
        title={`FinSight AI — ${report.report_type.charAt(0).toUpperCase()}${report.report_type.slice(1)} Report`}
        subtitle={subtitle}
        actions={actions}
        executiveSummary={executiveSummary}
        analysis={analysis}
        recommendations={recommendations}
        appendix={appendix || undefined}
      />
    </>
  );
}
