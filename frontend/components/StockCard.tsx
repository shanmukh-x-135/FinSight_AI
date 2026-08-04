import { Card, CardContent } from "@/components/ui/card";
import { cn, money, pct, signClass } from "@/lib/utils";

/**
 * StockCard — compact quote tile: symbol + name, last price, day change.
 * Used for movers and opportunities. Presentational; colours the change by sign.
 */
export interface StockCardProps {
  symbol: string;
  name?: string | null;
  sector?: string | null;
  price?: number | null;
  changePercent?: number | null;
}

export function StockCard({ symbol, name, sector, price, changePercent }: StockCardProps) {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 pt-4">
        <div className="min-w-0">
          <p className="truncate font-semibold">{symbol}</p>
          <p className="truncate text-xs text-muted-foreground">{name ?? sector ?? "—"}</p>
        </div>
        <div className="text-right">
          <p className="font-medium">{money(price)}</p>
          <p className={cn("text-xs", signClass(changePercent))}>{pct(changePercent)}</p>
        </div>
      </CardContent>
    </Card>
  );
}
