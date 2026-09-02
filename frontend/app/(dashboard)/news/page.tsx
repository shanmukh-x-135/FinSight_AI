"use client";

import { ExternalLink, Newspaper } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { DataState, MetricStrip, PageHeader, PageSkeleton, Panel, SectionHeader, StatusBadge } from "@/components/workspace";
import { ContextualAIActions } from "@/components/contextual-ai-actions";
import { newsApi, type NewsArticle } from "@/lib/api";

function sentimentTone(score: number) {
  return score > 0.1 ? "positive" as const : score < -0.1 ? "negative" as const : "neutral" as const;
}

export default function NewsPage() {
  const [articles, setArticles] = useState<NewsArticle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    newsApi.recent(100)
      .then((items) => active && setArticles(items))
      .catch(() => active && setError(true))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, []);

  const counts = useMemo(() => articles.reduce((result, article) => {
    result[article.sentiment_label as "positive" | "neutral" | "negative"] += 1;
    return result;
  }, { positive: 0, neutral: 0, negative: 0 }), [articles]);

  if (loading) return <PageSkeleton />;
  if (error) return <DataState kind="error" title="News intelligence unavailable" description="Recent evidence-backed coverage could not be loaded." />;

  return (
    <div className="space-y-5">
      <PageHeader eyebrow="Evidence-backed intelligence" title="News" description="Article-level sentiment, event drivers, source evidence, and explainable stock matching. No coverage is never treated as neutral." actions={<ContextualAIActions actions={[{ label: "Assess market impact", prompt: "Assess the likely market impact of the current recent news using source-linked evidence; distinguish association from proven causation." }, { label: "Summarize narratives", prompt: "Summarize the dominant narratives in recent news, including conflicting evidence and unavailable coverage." }]} />} />
      <MetricStrip className="xl:grid-cols-3" items={[{ label: "Positive evidence", value: counts.positive, detail: "Constructive source signals", tone: "positive" }, { label: "Neutral evidence", value: counts.neutral, detail: "Observed, not missing", tone: "neutral" }, { label: "Negative evidence", value: counts.negative, detail: "Adverse source signals", tone: "negative" }]} />
      <Panel>
        <SectionHeader title="Recent verified coverage" description={`${articles.length} recent article${articles.length === 1 ? "" : "s"}; source links open outside FinSight.`} action={<Newspaper className="size-4 text-primary" aria-hidden />} />
        {articles.length === 0 ? <div className="mt-4"><DataState kind="empty" title="No recent news found" description="The recent ingestion window contains no articles. Sentiment is unavailable, not neutral." /></div> : <div className="mt-5 divide-y divide-border/45">{articles.map((article, index) => <article key={article.id} className={index === 0 ? "surface-subtle mb-2 p-4 sm:p-5" : "py-4"}><div className="flex flex-wrap items-start justify-between gap-3"><div className="min-w-0 flex-1"><p className="text-label text-muted-foreground">{index === 0 ? "Latest verified coverage · " : ""}{article.source} · {article.published_at ? new Date(article.published_at).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" }) : "Timestamp unavailable"}</p><h2 className={index === 0 ? "mt-2 max-w-4xl text-lg font-semibold leading-7" : "mt-2 text-sm font-semibold leading-5"}>{article.title}</h2><div className="mt-3 flex flex-wrap gap-2"><StatusBadge label={article.event_category} tone="info" /><StatusBadge label={`${article.sentiment_label} ${article.sentiment_score >= 0 ? "+" : ""}${article.sentiment_score.toFixed(2)}`} tone={sentimentTone(article.sentiment_score)} /></div></div><a href={article.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-primary hover:bg-primary/10 focus-visible:ring-2 focus-visible:ring-ring">Open source <ExternalLink className="size-3" /></a></div><p className="mt-3 text-xs leading-5"><span className="font-semibold">Observed driver:</span> {article.driver}</p>{article.associations.length > 0 && <div className="mt-3 flex flex-wrap gap-2" aria-label="Associated instruments">{article.associations.map((association) => <Link key={association.symbol} href={`/market/${encodeURIComponent(association.symbol)}`} className="rounded-md bg-primary/8 px-2 py-1 text-[11px] text-primary outline-none hover:bg-primary/14 focus-visible:ring-2 focus-visible:ring-ring"><span className="font-medium">{association.symbol}</span> · match {Math.round(association.entity_match_confidence * 100)}%</Link>)}</div>}<details className="mt-3 rounded-lg bg-muted/35 px-3 py-2 text-xs"><summary className="cursor-pointer font-medium text-primary">Review source evidence</summary><p className="mt-2 leading-5 text-muted-foreground">{article.evidence_excerpt}</p><p className="mt-2 text-muted-foreground">Sentiment confidence {Math.round(article.sentiment_confidence * 100)}% · event confidence {Math.round(article.event_confidence * 100)}%</p></details></article>)}</div>}
      </Panel>
    </div>
  );
}
