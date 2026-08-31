import { ExternalLink } from "lucide-react";

import { DataState, StatusBadge } from "@/components/workspace";
import type { StockNewsEvidence } from "@/lib/api";

function tone(direction: string) {
  return direction === "positive" ? "positive" : direction === "negative" ? "negative" : "neutral";
}

export function NewsEvidenceList({ evidence }: { evidence: StockNewsEvidence[] }) {
  if (evidence.length === 0) {
    return <DataState kind="empty" title="No relevant news found" description="No recent article has a verified association with this stock. Missing coverage is unavailable, not neutral." />;
  }

  return (
    <div className="divide-y divide-border/60">
      {evidence.map((item) => (
        <article key={item.id} className="py-4 first:pt-0 last:pb-0">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge label={item.event_category} tone="info" />
                <StatusBadge label={`${item.sentiment_class} ${item.sentiment_score >= 0 ? "+" : ""}${item.sentiment_score.toFixed(2)}`} tone={tone(item.sentiment_class)} />
              </div>
              <h3 className="mt-2 text-sm font-semibold leading-5">{item.headline}</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {item.publisher} · {item.published_at ? new Date(item.published_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Timestamp unavailable"}
              </p>
            </div>
            <a href={item.source_url} target="_blank" rel="noreferrer" className="inline-flex shrink-0 items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary outline-none hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-ring">
              Open article <ExternalLink className="size-3" aria-hidden />
            </a>
          </div>
          <p className="mt-3 text-xs leading-5 text-foreground/85"><span className="font-semibold">Why:</span> {item.driver}</p>
          <details className="mt-2 rounded-lg border border-border/60 bg-muted/20 px-3 py-2 text-xs">
            <summary className="cursor-pointer font-medium text-primary">Review evidence</summary>
            <p className="mt-2 leading-5 text-muted-foreground">{item.evidence_excerpt}</p>
            <dl className="mt-3 grid gap-2 border-t border-border/60 pt-3 sm:grid-cols-3">
              <div><dt className="text-muted-foreground">Sentiment confidence</dt><dd className="font-medium text-foreground">{Math.round(item.sentiment_confidence * 100)}%</dd></div>
              <div><dt className="text-muted-foreground">Entity match</dt><dd className="font-medium text-foreground">{Math.round(item.entity_match_confidence * 100)}%</dd></div>
              <div><dt className="text-muted-foreground">Matched as</dt><dd className="font-medium text-foreground">{item.matched_alias ?? "Unavailable"}</dd></div>
            </dl>
          </details>
        </article>
      ))}
    </div>
  );
}
