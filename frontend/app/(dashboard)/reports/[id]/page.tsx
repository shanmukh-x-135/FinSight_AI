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
import { StockCard } from "@/components/StockCard";
import { ReportBreadthVisual, ReportHistoryVisual, ReportPortfolioVisual, ReportSentimentVisual } from "@/components/report-visuals";
import { ReportPageTemplate } from "@/components/templates/ReportPageTemplate";
import { Button, buttonVariants } from "@/components/ui/button";
import { DataState, MetricStrip, PageSkeleton } from "@/components/workspace";
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
import { cn, money, pct, ratioPct } from "@/lib/utils";

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
    return <PageSkeleton />;
  }
  if (notFound || !report) {
    return (
      <div className="mx-auto max-w-4xl space-y-3">
        <DataState kind="error" title="Report unavailable" description="The report was not found or does not belong to this account." />
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
      <Link href="/reports" className={cn(buttonVariants({ variant: "ghost", size: "sm" }))}>← Back</Link>
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
            <><ReportBreadthVisual breadth={market.breadth} /><MetricStrip className="mt-3 sm:grid-cols-3 xl:grid-cols-5" items={[{ label: "Advancers", value: market.breadth.advancers, tone: "positive" }, { label: "Decliners", value: market.breadth.decliners, tone: "negative" }, { label: "Unchanged", value: market.breadth.unchanged, tone: "neutral" }, { label: "Tracked", value: market.breadth.total }, { label: "A/D ratio", value: market.breadth.advance_decline_ratio == null ? "—" : market.breadth.advance_decline_ratio.toFixed(2) }]} /></>
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
          <MetricStrip className="sm:grid-cols-2 xl:grid-cols-5" items={[{ label: "Total value", value: money(portfolio.total_value) }, { label: "Total return", value: pct(portfolio.total_return_percent), tone: portfolio.total_return_percent == null ? "neutral" : portfolio.total_return_percent >= 0 ? "positive" : "negative" }, { label: "Health score", value: portfolio.health_score == null ? "—" : Math.round(portfolio.health_score), detail: `Risk: ${portfolio.risk_level ?? "—"}` }, { label: "Diversification", value: portfolio.diversification_score == null ? "—" : `${Math.round(portfolio.diversification_score)}/100` }, { label: "Holdings", value: portfolio.number_of_holdings ?? "—" }]} />
          <ReportPortfolioVisual health={portfolio.health_score} diversification={portfolio.diversification_score} />
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
            <><ReportHistoryVisual statistics={hist.statistics} /><MetricStrip className="mt-3 xl:grid-cols-3" items={[{ label: "Similar sessions", value: hist.statistics.sample_size, detail: `top-${hist.statistics.k} nearest` }, { label: "Closed higher", value: hist.statistics.bullish_probability == null ? "—" : `${Math.round(hist.statistics.bullish_probability * 100)}%` }, { label: "Average next day", value: ratioPct(hist.statistics.avg_next_day_return), tone: hist.statistics.avg_next_day_return == null ? "neutral" : hist.statistics.avg_next_day_return >= 0 ? "positive" : "negative" }]} /></>
          )}
          <p className="text-xs italic text-muted-foreground">
            Historical context, not a forecast.
          </p>
        </>
      )}

      {!market && !portfolio && !hist && (
        <DataState kind="empty" title="No analysis sections" description="This stored report does not contain market, portfolio, or historical analysis." />
      )}
    </div>
  );

  const recommendations = (
    <div className="space-y-6">
      <div className="grid gap-4 lg:grid-cols-2">
        {recs.length === 0 ? (
          <DataState kind="empty" title="No watch-rated opportunities" description="No recommendation crossed the report's deterministic watch threshold." />
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
    <div className="surface-subtle p-4">
        <h3 className="text-section-heading">Notable news</h3>
        <div className="mt-3">
        <ReportSentimentVisual labels={news.map((item) => item.sentiment_label)} />
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
        </div>
    </div>
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
