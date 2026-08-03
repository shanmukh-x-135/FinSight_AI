"use client";

/**
 * Portfolio page — first real use of the Analytics page template.
 * Shows summary metrics, sector allocation (donut), a health card, and the
 * holdings table with add/edit/remove. All numbers come from the backend
 * analytics endpoint (Phase 3), which values holdings against Phase 2 prices.
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";

import { DonutChart } from "@/components/donut-chart";
import { AnalyticsPageTemplate } from "@/components/templates/AnalyticsPageTemplate";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  ApiError,
  portfolioApi,
  type PortfolioAnalytics,
  type PortfolioDetail,
} from "@/lib/api";

const money = (n: number | null | undefined) =>
  n == null ? "—" : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const pct = (n: number | null | undefined) =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
const signClass = (n: number | null | undefined) =>
  n == null ? "" : n > 0 ? "text-green-600" : n < 0 ? "text-red-600" : "";

function Metric({ label, value, sub, valueClass }: {
  label: string; value: string; sub?: string; valueClass?: string;
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-xs text-muted-foreground">{label}</p>
        <p className={`mt-1 text-xl font-bold ${valueClass ?? ""}`}>{value}</p>
        {sub && <p className={`text-xs ${valueClass ?? "text-muted-foreground"}`}>{sub}</p>}
      </CardContent>
    </Card>
  );
}

export default function PortfolioPage() {
  const [portfolioId, setPortfolioId] = useState<number | null>(null);
  const [analytics, setAnalytics] = useState<PortfolioAnalytics | null>(null);
  const [detail, setDetail] = useState<PortfolioDetail | null>(null);
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
      <Metric label="Total Value" value={money(a.total_value)} />
      <Metric
        label="Total Return"
        value={money(a.total_unrealized_pnl)}
        sub={pct(a.total_return_percent)}
        valueClass={signClass(a.total_unrealized_pnl)}
      />
      <Metric
        label="Today's P&L"
        value={money(a.daily_pnl)}
        sub={pct(a.daily_pnl_percent)}
        valueClass={signClass(a.daily_pnl)}
      />
      <Metric label="Health Score" value={`${a.health_score}`} sub={`risk: ${a.risk_level}`} />
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

  const tables = a && (
    <div className="flex flex-col gap-6">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-muted-foreground">
              <th className="py-2 pr-3">Symbol</th>
              <th className="py-2 pr-3 text-right">Qty</th>
              <th className="py-2 pr-3 text-right">Avg</th>
              <th className="py-2 pr-3 text-right">Price</th>
              <th className="py-2 pr-3 text-right">Value</th>
              <th className="py-2 pr-3 text-right">P&L</th>
              <th className="py-2 pr-3 text-right">Return</th>
              <th className="py-2 pr-3 text-right">Weight</th>
              <th className="py-2 pr-3" />
            </tr>
          </thead>
          <tbody>
            {a.holdings.length === 0 && (
              <tr><td colSpan={9} className="py-4 text-muted-foreground">No holdings yet — add one below.</td></tr>
            )}
            {a.holdings.map((h) => (
              <tr key={h.id} className="border-b">
                <td className="py-2 pr-3 font-medium">{h.symbol}</td>
                <td className="py-2 pr-3 text-right">{h.quantity}</td>
                <td className="py-2 pr-3 text-right">{money(h.avg_buy_price)}</td>
                <td className="py-2 pr-3 text-right">{money(h.current_price)}</td>
                <td className="py-2 pr-3 text-right">{money(h.market_value)}</td>
                <td className={`py-2 pr-3 text-right ${signClass(h.unrealized_pnl)}`}>{money(h.unrealized_pnl)}</td>
                <td className={`py-2 pr-3 text-right ${signClass(h.return_percent)}`}>{pct(h.return_percent)}</td>
                <td className="py-2 pr-3 text-right">{h.weight_percent.toFixed(1)}%</td>
                <td className="py-2 pr-3 text-right whitespace-nowrap">
                  <button className="text-blue-600 hover:underline" onClick={() => onEdit(h.id)}>Edit</button>
                  <button className="ml-3 text-red-600 hover:underline" onClick={() => onRemove(h.id)}>Remove</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

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
      tables={tables}
    />
  );
}
