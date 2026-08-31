"use client";

/**
 * Portfolio page — first real use of the Analytics page template.
 * Shows summary metrics, sector allocation (donut), a health card, and the
 * holdings table with add/edit/remove. All numbers come from the backend
 * analytics endpoint (Phase 3), which values holdings against Phase 2 prices.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { AIAnalysisState } from "@/components/AIAnalysisState";
import { DataTable, type Column } from "@/components/DataTable";
import { DonutChart } from "@/components/donut-chart";
import { ContributionChart } from "@/components/finance-charts";
import { ContextualAIActions } from "@/components/contextual-ai-actions";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { PortfolioRiskView } from "@/components/portfolio-risk";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DataState, PageHeader, PageSkeleton, Panel, SectionHeader, StatusBadge } from "@/components/workspace";
import {
  ApiError,
  intelligenceApi,
  portfolioApi,
  type HoldingAnalytics,
  type PortfolioAnalytics,
  type PortfolioDetail,
  type PortfolioRisk,
  type Recommendation,
} from "@/lib/api";
import { money, pct, signClass } from "@/lib/utils";

export default function PortfolioPage() {
  const [portfolioId, setPortfolioId] = useState<number | null>(null);
  const [analytics, setAnalytics] = useState<PortfolioAnalytics | null>(null);
  const [detail, setDetail] = useState<PortfolioDetail | null>(null);
  const [risk, setRisk] = useState<PortfolioRisk | null>(null);
  const [insights, setInsights] = useState<Recommendation[]>([]);
  const [aiUnavailable, setAiUnavailable] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Add/edit form state.
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [avgPrice, setAvgPrice] = useState("");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async (id: number) => {
    const [a, d] = await Promise.all([
      portfolioApi.analytics(id),
      portfolioApi.detail(id),
    ]);
    setAnalytics(a);
    setDetail(d);
    try {
      setRisk(await portfolioApi.risk(id));
    } catch {
      setRisk(null);
    }

    // AI insights relevant to what the user actually holds (best-effort).
    try {
      const held = new Set(a.holdings.map((h) => h.symbol));
      const recs = await intelligenceApi.recommendations();
      setInsights(
        [...recs.watchlist, ...recs.risk_alerts].filter((r) => held.has(r.symbol)),
      );
      setAiUnavailable(false);
    } catch {
      setInsights([]);
      setAiUnavailable(true);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await portfolioApi.list();
        const p = list[0] ?? (await portfolioApi.create("My Portfolio"));
        if (cancelled) return;
        setPortfolioId(p.id);
        await reload(p.id);
      } catch {
        if (!cancelled) setError("Could not load your portfolio.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reload]);

  function resetForm() {
    setSymbol("");
    setQuantity("");
    setAvgPrice("");
    setEditingId(null);
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (portfolioId == null) return;
    setError(null);
    setBusy(true);
    try {
      const q = Number(quantity);
      const a = Number(avgPrice);
      if (editingId != null) {
        await portfolioApi.updateHolding(portfolioId, editingId, {
          quantity: q,
          avg_buy_price: a,
        });
      } else {
        await portfolioApi.addHolding(portfolioId, {
          symbol: symbol.trim().toUpperCase(),
          quantity: q,
          avg_buy_price: a,
        });
      }
      resetForm();
      await reload(portfolioId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save holding.");
    } finally {
      setBusy(false);
    }
  }

  async function onRemove(itemId: number) {
    if (portfolioId == null) return;
    await portfolioApi.removeHolding(portfolioId, itemId);
    await reload(portfolioId);
  }

  function onEdit(itemId: number) {
    const h = detail?.holdings.find((x) => x.id === itemId);
    if (!h) return;
    setEditingId(itemId);
    setSymbol(h.symbol);
    setQuantity(String(h.quantity));
    setAvgPrice(String(h.avg_buy_price));
  }

  if (loading) {
    return <PageSkeleton />;
  }

  const a = analytics;

  const summaryCards = a && (
    <div className="space-y-4">
      {!a.valuation_complete && (
        <div role="status" className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-4 text-sm">
          Valuation metrics are unavailable until prices arrive for {a.unpriced_symbols.join(", ")}.
          Known cost basis: {money(a.total_cost)}.
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <MetricCard label="Total Value" value={money(a.total_value)} />
        <MetricCard
          label="Total Return"
          value={money(a.total_unrealized_pnl)}
          sub={pct(a.total_return_percent)}
          tone={toneOf(a.total_unrealized_pnl)}
        />
        <MetricCard
          label="Today's P&L"
          value={money(a.daily_pnl)}
          sub={pct(a.daily_pnl_percent)}
          tone={toneOf(a.daily_pnl)}
        />
        <MetricCard label="Health Score" value={a.health_score ?? "—"} sub={`risk: ${a.risk_level}`} />
      </div>
    </div>
  );

  const charts = a && (
    <div className="grid gap-4 xl:grid-cols-3">
      <Panel className="xl:col-span-3"><SectionHeader title="Portfolio equity curve" description="Performance through time requires dated cash flows and position history." /><div className="mt-4"><DataState kind="unavailable" title="Historical portfolio valuation is not available" description="FinSight currently stores present holdings and cost basis, not transaction timing. An equity curve is intentionally withheld rather than reconstructed from incomplete data." /></div></Panel>
      <Panel>
          <SectionHeader title="Sector allocation" description="Current market value by sector." />
          <div className="mt-4">
          {a.sector_allocation.length ? (
            <DonutChart
              slices={a.sector_allocation.map((s) => ({
                label: s.sector,
                value: s.value,
                percent: s.weight_percent,
              }))}
            />
          ) : (
            <p className="text-sm text-muted-foreground">No holdings yet.</p>
          )}
          </div>
      </Panel>
      <Panel>
        <SectionHeader title="Portfolio health" description="Deterministic concentration and volatility measures." />
        <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><p className="text-muted-foreground">Diversification</p><p className="font-semibold">{a.diversification_score == null ? "—" : `${a.diversification_score}/100`}</p></div>
          <div><p className="text-muted-foreground">Top holding</p><p className="font-semibold">{a.top_holding_weight_percent == null ? "—" : `${a.top_holding_weight_percent.toFixed(1)}%`}</p></div>
          <div><p className="text-muted-foreground">Volatility</p><p className="font-semibold">{a.volatility_percent == null ? "—" : `${a.volatility_percent.toFixed(2)}%`}</p></div>
          <div><p className="text-muted-foreground">Risk level</p><p className="mt-1"><StatusBadge label={a.risk_level} tone={a.risk_level === "high" ? "negative" : a.risk_level === "medium" ? "warning" : "positive"} /></p></div>
          <div><p className="text-muted-foreground">Holdings</p><p className="font-semibold">{a.number_of_holdings}</p></div>
          <div><p className="text-muted-foreground">Sectors</p><p className="font-semibold">{a.number_of_sectors}</p></div>
        </div>
      </Panel>
      <Panel><SectionHeader title="P&L contribution" description="Largest unrealized contributors by holding." /><ContributionChart holdings={a.holdings} /></Panel>
    </div>
  );

  const aiAnalysis = aiUnavailable ? (
    <AIAnalysisState
      status="unavailable"
      message="AI analysis is temporarily unavailable. Portfolio analytics remain available."
    />
  ) : insights.length === 0 ? (
    <AIAnalysisState
      status="empty"
      message="No current watch or avoid signals match this portfolio's holdings."
    />
  ) : (
    <div className="grid gap-4 lg:grid-cols-2">
      {insights.map((r) => (
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

  const tables = a && (
    <div className="flex flex-col gap-6">
      <DataTable<HoldingAnalytics>
        columns={[
          { key: "symbol", header: "Symbol", className: "font-medium", render: (h) => h.symbol },
          { key: "quantity", header: "Qty", align: "right", render: (h) => h.quantity },
          { key: "average", header: "Avg", align: "right", render: (h) => money(h.avg_buy_price) },
          { key: "price", header: "Price", align: "right", render: (h) => money(h.current_price) },
          { key: "value", header: "Value", align: "right", render: (h) => money(h.market_value) },
          {
            key: "pnl",
            header: "P&L",
            align: "right",
            render: (h) => (
              <span className={signClass(h.unrealized_pnl)}>{money(h.unrealized_pnl)}</span>
            ),
          },
          {
            key: "return",
            header: "Return",
            align: "right",
            render: (h) => (
              <span className={signClass(h.return_percent)}>{pct(h.return_percent)}</span>
            ),
          },
          {
            key: "weight",
            header: "Weight",
            align: "right",
            render: (h) => h.weight_percent == null ? "—" : `${h.weight_percent.toFixed(1)}%`,
          },
          {
            key: "actions",
            header: <span className="sr-only">Actions</span>,
            align: "right",
            className: "whitespace-nowrap",
            render: (h) => (
              <>
                <button
                  type="button"
                  className="text-blue-600 hover:underline"
                  onClick={() => onEdit(h.id)}
                >
                  Edit
                </button>
                <button
                  type="button"
                  className="ml-3 text-red-600 hover:underline"
                  onClick={() => onRemove(h.id)}
                >
                  Remove
                </button>
              </>
            ),
          },
        ] satisfies Column<HoldingAnalytics>[]}
        rows={a.holdings}
        rowKey={(holding) => holding.id}
        emptyMessage="No holdings yet — add one below."
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">{editingId != null ? "Edit holding" : "Add holding"}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="symbol">Symbol</Label>
              <Input id="symbol" value={symbol} disabled={editingId != null}
                onChange={(e) => setSymbol(e.target.value)} placeholder="RELIANCE.NS" className="w-40" required />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="qty">Quantity</Label>
              <Input id="qty" type="number" min="0" step="any" value={quantity}
                onChange={(e) => setQuantity(e.target.value)} className="w-28" required />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="avg">Avg buy price</Label>
              <Input id="avg" type="number" min="0" step="any" value={avgPrice}
                onChange={(e) => setAvgPrice(e.target.value)} className="w-32" required />
            </div>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : editingId != null ? "Update" : "Add"}
            </Button>
            {editingId != null && (
              <Button type="button" variant="outline" onClick={resetForm}>Cancel</Button>
            )}
          </form>
          {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
        </CardContent>
      </Card>
    </div>
  );

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Portfolio analytics" title={detail?.name ?? "Portfolio"} description="Exposure, contribution, risk, and evidence-backed position intelligence." actions={<ContextualAIActions actions={[{ label: "Explain concentration", prompt: "Explain my portfolio concentration using the current evidence and identify the largest contributors." }, { label: "Review P&L", prompt: "Explain my portfolio profit and loss by position using current deterministic analytics." }, { label: "Interpret stress", prompt: "Summarize my portfolio stress-test results, key vulnerabilities, and evidence-backed limitations." }]} />} />
      {error && !analytics ? <DataState kind="error" title="Portfolio unavailable" description={error} /> : <>{summaryCards}{charts}{risk && portfolioId != null && <PortfolioRiskView risk={risk} onCounterfactual={(changes) => portfolioApi.counterfactual(portfolioId, changes)} />}<Panel><SectionHeader title="Position intelligence" description="Signals are ranked deterministically from current analytics." /><div className="mt-4">{aiAnalysis}</div></Panel><Panel><SectionHeader title="Holdings" description="Current valuation and unrealized performance by position." /><div className="mt-4">{tables}</div></Panel></>}
    </div>
  );
}
