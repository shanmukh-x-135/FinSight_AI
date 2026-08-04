import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * StockCard — compact quote tile: symbol + name, last price, day change.
 * Used for movers and opportunities. Presentational; colours the change by sign.
 */
const money = (n: number | null | undefined) =>
  n == null ? "—" : `₹${n.toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
const pct = (n: number | null | undefined) =>
  n == null ? "—" : `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;

export interface StockCardProps {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  price?: number | null;
  changePercent?: number | null;
}

export function StockCard({ symbol, name, sector, price, changePercent }: StockCardProps) {
  const tone =
    changePercent == null ? "" : changePercent > 0 ? "text-green-600" : changePercent < 0 ? "text-red-600" : "";
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 pt-4">
        <div className="min-w-0">
          <p className="truncate font-semibold">{symbol}</p>
          <p className="truncate text-xs text-muted-foreground">{name ?? sector ?? "—"}</p>
        </div>
        <div className="text-right">
          <p className="font-medium">{money(price)}</p>
          <p className={cn("text-xs", tone)}>{pct(changePercent)}</p>
        </div>
      </CardContent>
    </Card>
  );
}
