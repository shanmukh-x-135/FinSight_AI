"use client";

import { AlertTriangle, CheckCircle2, Clock3, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

import { DataFreshnessStrip } from "@/components/data-freshness";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DataState, PageHeader, PageSkeleton, Panel, SectionHeader, StatusBadge } from "@/components/workspace";
import { operationsApi, type EODStatus, type PipelineStepStatus } from "@/lib/api";

const tone = (status: string) => status === "completed" || status === "healthy" ? "positive" as const : status === "failed" || status === "partial" || status === "attention" ? "negative" as const : status === "running" ? "info" as const : "neutral" as const;
const label = (value: string) => value.replaceAll("_", " ");

function StepCard({ step }: { step: PipelineStepStatus }) {
  const Icon = step.status === "completed" ? CheckCircle2 : step.status === "failed" ? AlertTriangle : Clock3;
  return <li className="rounded-xl border border-border/70 bg-card/70 p-4"><div className="flex items-start justify-between gap-3"><div className="flex items-center gap-2"><Icon className="size-4 text-primary" aria-hidden /><h2 className="text-sm font-semibold capitalize">{label(step.step_name)}</h2></div><StatusBadge label={step.status} tone={tone(step.status)} /></div><dl className="mt-4 grid grid-cols-2 gap-2 text-xs"><div><dt className="text-muted-foreground">Attempts</dt><dd className="mt-1 font-semibold">{step.attempt_count}</dd></div><div><dt className="text-muted-foreground">Completed</dt><dd className="mt-1 font-medium">{step.completed_at ? new Date(step.completed_at).toLocaleString("en-IN") : "Not completed"}</dd></div></dl>{Object.keys(step.counters).length > 0 && <div className="mt-3 flex flex-wrap gap-2">{Object.entries(step.counters).map(([key, value]) => <span key={key} className="rounded-md bg-muted/50 px-2 py-1 text-[11px]"><span className="text-muted-foreground">{label(key)}</span> <strong>{value}</strong></span>)}</div>}{step.last_error_summary && <p role="alert" className="mt-3 rounded-md border border-negative/25 bg-negative/10 px-3 py-2 text-xs text-negative">{step.last_error_summary}</p>}</li>;
}

export default function OperationsPage() {
  const [status, setStatus] = useState<EODStatus | null>(null);
  const [target, setTarget] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const load = useCallback(async (date?: string) => { setLoading(true); setError(""); try { setStatus(await operationsApi.eodStatus(date || undefined)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Operational status could not be loaded."); } finally { setLoading(false); } }, []);
  useEffect(() => {
    let active = true;
    operationsApi.eodStatus().then((value) => { if (active) setStatus(value); }).catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Operational status could not be loaded."); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  if (loading && !status) return <PageSkeleton />;

  return <div className="space-y-5"><PageHeader eyebrow="Administrator" title="EOD Operations" description="Durable pipeline checkpoints, data freshness, counters, and safe rerun guidance for the end-of-day research workflow." actions={<Button size="sm" variant="outline" onClick={() => void load(target)} disabled={loading}><RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} />Refresh</Button>} />
    <Panel><form className="flex flex-wrap items-end gap-3" onSubmit={(event) => { event.preventDefault(); void load(target); }}><div><Label htmlFor="target-date">Trading date</Label><Input id="target-date" type="date" value={target} onChange={(event) => setTarget(event.currentTarget.value)} className="mt-1" /></div><Button type="submit" variant="outline" disabled={loading}>Inspect date</Button><Button type="button" variant="ghost" onClick={() => { setTarget(""); void load(); }}>Latest run</Button></form></Panel>
    {error && <DataState kind="error" title="Operations status unavailable" description={error} onRetry={() => void load(target)} />}
    {status && <><DataFreshnessStrip items={status.freshness} /><Panel><SectionHeader title={status.run ? `${status.run.target_trading_date} · ${label(status.run.status)}` : "No matching EOD run"} description={status.operator_explanation} action={<StatusBadge label={status.health} tone={tone(status.health)} />} />{status.run && <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{[["Attempts", status.run.attempt_count], ["Started", status.run.started_at ? new Date(status.run.started_at).toLocaleString("en-IN") : "Not started"], ["Completed", status.run.completed_at ? new Date(status.run.completed_at).toLocaleString("en-IN") : "Not completed"], ["Correlation ID", status.run.correlation_id]].map(([term, value]) => <div key={term} className="rounded-lg border border-border/60 bg-muted/20 p-3"><dt className="text-xs text-muted-foreground">{term}</dt><dd className="mt-1 break-all text-sm font-semibold">{value}</dd></div>)}</dl>}{status.run?.last_error_summary && <p role="alert" className="mt-4 rounded-lg border border-negative/25 bg-negative/10 p-3 text-sm text-negative">{status.run.last_error_summary}</p>}{status.rerun_recommended && <p className="mt-4 text-xs text-warning">A rerun is recommended. The external one-shot runner resumes completed checkpoints safely.</p>}</Panel><Panel><SectionHeader title="Pipeline steps" description="Each step commits independently; errors are safe summaries without provider secrets." />{status.run?.steps.length ? <ol className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">{status.run.steps.map((step) => <StepCard key={step.step_name} step={step} />)}</ol> : <div className="mt-4"><DataState kind="empty" title="No step checkpoints" description="No pipeline run has created step state for this session." /></div>}</Panel></>}
  </div>;
}
