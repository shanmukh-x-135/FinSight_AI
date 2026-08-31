import Link from "next/link";

import type { HeatmapStock } from "@/lib/api";
import { pct } from "@/lib/utils";
import { DataState, SectionHeader } from "@/components/workspace";

function tileStyle(value: number | null): React.CSSProperties {
  if (value == null) return { backgroundColor: "var(--muted)" };
  const intensity = Math.min(Math.abs(value) / 4, 1);
  const alpha = 0.13 + intensity * 0.56;
  const rgb = value > 0 ? "22, 163, 74" : value < 0 ? "220, 38, 38" : "120, 120, 120";
  return { backgroundColor: `rgba(${rgb}, ${alpha})` };
}

function compactSymbol(symbol: string) {
  return symbol.replace(/\.NS$/, "");
}

export function StockHeatmap({ stocks }: { stocks: HeatmapStock[] }) {
  if (stocks.length === 0) {
    return <DataState kind="empty" title="Heatmap unavailable" description="Synchronize and ingest the selected universe to populate stock tiles." />;
  }
  const groups = new Map<string, HeatmapStock[]>();
  for (const stock of stocks) groups.set(stock.sector, [...(groups.get(stock.sector) ?? []), stock]);

  return (
    <div aria-label="Stock performance heatmap" className="space-y-4">
      <SectionHeader title="Stock heatmap" description={`${stocks.length} end-of-day instruments grouped by sector · colour shows 1D return`} />
      <div className="grid gap-3 lg:grid-cols-2">
        {[...groups].map(([sector, items]) => (
          <section key={sector} className="min-w-0 rounded-lg border border-border/60 bg-muted/10 p-2.5" aria-labelledby={`heatmap-${sector.replace(/\W+/g, "-")}`}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <h3 id={`heatmap-${sector.replace(/\W+/g, "-")}`} className="truncate text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{sector}</h3>
              <span className="text-[10px] tabular-nums text-muted-foreground">{items.length}</span>
            </div>
            <div className="grid grid-cols-3 gap-1 sm:grid-cols-4 xl:grid-cols-5">
              {items.map((stock) => {
                const news = stock.sentiment_availability === "available" ? `news ${stock.sentiment?.toFixed(2) ?? "unscored"}` : "news unavailable";
                const details = `${stock.name ?? stock.symbol}; ${pct(stock.change_percent)}; RSI ${stock.rsi_14?.toFixed(1) ?? "unavailable"}; ${news}`;
                return (
                  <Link
                    key={stock.symbol}
                    href={`/market/${encodeURIComponent(stock.symbol)}`}
                    style={tileStyle(stock.change_percent)}
                    title={details}
                    aria-label={`${stock.symbol}: ${details}`}
                    className="min-w-0 rounded-md px-1.5 py-2 text-center ring-1 ring-foreground/5 transition-transform hover:z-10 hover:scale-[1.04] focus-visible:z-10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary motion-reduce:transform-none"
                  >
                    <span className="block truncate text-[10px] font-semibold">{compactSymbol(stock.symbol)}</span>
                    <span className="mt-0.5 block text-[10px] font-bold tabular-nums">{pct(stock.change_percent)}</span>
                    <span className="mt-1 flex items-center justify-center gap-1 text-[8px] text-foreground/70">
                      <span>RSI {stock.rsi_14?.toFixed(0) ?? "—"}</span>
                      <span aria-hidden className={stock.sentiment_availability !== "available" ? "text-muted-foreground" : (stock.sentiment ?? 0) >= 0 ? "text-positive" : "text-negative"}>●</span>
                    </span>
                  </Link>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
