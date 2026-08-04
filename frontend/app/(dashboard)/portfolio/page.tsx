"use client";

/**
 * Portfolio page — first real use of the Analytics page template.
 * Shows summary metrics, sector allocation (donut), a health card, and the
 * holdings table with add/edit/remove. All numbers come from the backend
 * analytics endpoint (Phase 3), which values holdings against Phase 2 prices.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { AIInsightCard } from "@/components/AIInsightCard";
import { DataTable, type Column } from "@/components/DataTable";
import { DonutChart } from "@/components/donut-chart";
import { MetricCard, toneOf } from "@/components/MetricCard";
import { AnalyticsPageTemplate } from "@/components/templates/AnalyticsPageTemplate";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ApiError,
  intelligenceApi,
  portfolioApi,
  type HoldingAnalytics,
  type PortfolioAnalytics,
  type PortfolioDetail,
  type Recommendation,
} from "@/lib/api";
import { money, pct, signClass } from "@/lib/utils";

export default function PortfolioPage() {
  const [portfolioId, setPortfolioId] = useState<number | null>(null);
  const [analytics, setAnalytics] = useState<PortfolioAnalytics | null>(null);
  const [detail, setDetail] = useState<PortfolioDetail | null>(null);
  const [insights, setInsights] = useState<Recommendation[]>([]);
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

    // AI insights relevant to what the user actually holds (best-effort).
    try {
      const held = new Set(a.holdings.map((h) => h.symbol));
      const recs = await intelligenceApi.recommendations();
      setInsights(
        [...recs.watchlist, ...recs.risk_alerts].filter((r) => held.has(r.symbol)),
      );
    } catch {
      setInsights([]);
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
    return <p className="text-sm text-muted-foreground">Loading portfolio…</p>;
  }

  const a = analytics;

  const summaryCards = a && (
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
      <MetricCard label="Health Score" value={a.health_score} sub={`risk: ${a.risk_level}`} />
    </div>
  );

  const charts = a && (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Sector Allocation</CardTitle>
        </CardHeader>
        <CardContent>
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
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Portfolio Health</CardTitle>
        </CardHeader>
        <CardContent className="grid grid-cols-2 gap-3 text-sm">
          <div><p className="text-muted-foreground">Diversification</p><p className="font-semibold">{a.diversification_score}/100</p></div>
          <div><p className="text-muted-foreground">Top holding</p><p className="font-semibold">{a.top_holding_weight_percent.toFixed(1)}%</p></div>
          <div><p className="text-muted-foreground">Volatility</p><p className="font-semibold">{a.volatility_percent == null ? "—" : `${a.volatility_percent.toFixed(2)}%`}</p></div>
          <div><p className="text-muted-foreground">Risk level</p><p className="font-semibold capitalize">{a.risk_level}</p></div>
          <div><p className="text-muted-foreground">Holdings</p><p className="font-semibold">{a.number_of_holdings}</p></div>
          <div><p className="text-muted-foreground">Sectors</p><p className="font-semibold">{a.number_of_sectors}</p></div>
        </CardContent>
      </Card>
    </div>
  );

  const aiAnalysis = insights.length > 0 && (
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
            render: (h) => `${h.weight_percent.toFixed(1)}%`,
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
    <AnalyticsPageTemplate
      title="Portfolio"
      subtitle={detail?.name}
      summaryCards={summaryCards}
      charts={charts}
      aiAnalysis={aiAnalysis || undefined}
      tables={tables}
    />
  );
}
