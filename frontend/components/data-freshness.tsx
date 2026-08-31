import { Clock3 } from "lucide-react";

import { StatusBadge } from "@/components/workspace";
import type { DataFreshness } from "@/lib/api";

const labels: Record<DataFreshness["dataset"], string> = {
  market: "Market",
  news: "News",
  universe: "Universe",
  historical_corpus: "History",
};

export function DataFreshnessStrip({ items }: { items: DataFreshness[] }) {
  return (
    <section aria-label="Data freshness" className="flex flex-wrap items-center gap-2 rounded-xl border border-border/70 bg-card/70 px-3 py-2">
      <span className="mr-1 inline-flex items-center gap-1.5 text-xs font-medium text-muted-foreground"><Clock3 className="size-3.5" aria-hidden />Data freshness</span>
      {items.map((item) => (
        <span key={item.dataset} title={item.explanation} className="inline-flex items-center gap-1.5 rounded-md border border-border/60 bg-background/60 px-2 py-1 text-[11px]">
          <span>{labels[item.dataset]}</span>
          <StatusBadge label={item.state} tone={item.state === "Fresh" ? "positive" : item.state === "Delayed" ? "warning" : "neutral"} />
          <span className="sr-only">{item.explanation}</span>
        </span>
      ))}
    </section>
  );
}
