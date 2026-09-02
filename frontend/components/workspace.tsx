import { AlertTriangle, ArrowDownRight, ArrowUpRight, Inbox, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-col gap-3 pb-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        {eyebrow && <p className="text-label text-primary">{eyebrow}</p>}
        <h1 className="text-page-heading mt-1">{title}</h1>
        {description && <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function SectionHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 className="text-section-heading">{title}</h2>
        {description && <p className="mt-0.5 text-xs leading-5 text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function Panel({ className, children }: { className?: string; children: ReactNode }) {
  return <section className={cn("surface-primary min-w-0 p-4 sm:p-5", className)}>{children}</section>;
}

export function TrendValue({ value, children, compact = false }: { value: number | null | undefined; children?: ReactNode; compact?: boolean }) {
  const positive = value != null && value > 0;
  const negative = value != null && value < 0;
  const Icon = positive ? ArrowUpRight : negative ? ArrowDownRight : null;
  return (
    <span className={cn("inline-flex items-center gap-1 font-medium", compact ? "text-xs" : "text-sm", positive && "text-positive", negative && "text-negative", value == null && "text-muted-foreground")}>
      {Icon && <Icon className="size-3.5" aria-hidden />}
      {children}
      <span className="sr-only">{positive ? "increase" : negative ? "decrease" : "unchanged"}</span>
    </span>
  );
}

export function StatusBadge({ label, tone = "neutral" }: { label: string; tone?: "positive" | "negative" | "warning" | "neutral" | "info" | "delayed" | "stale" | "confidence" }) {
  return (
    <span className={cn(
      "inline-flex items-center rounded-md border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
      tone === "positive" && "border-positive/25 bg-positive/10 text-positive",
      tone === "negative" && "border-negative/25 bg-negative/10 text-negative",
      tone === "warning" && "border-warning/25 bg-warning/10 text-warning",
      tone === "delayed" && "border-delayed/25 bg-delayed/10 text-delayed",
      tone === "stale" && "border-stale/25 bg-stale/10 text-stale",
      tone === "confidence" && "border-confidence/25 bg-confidence/10 text-confidence",
      tone === "info" && "border-primary/25 bg-primary/10 text-primary",
      tone === "neutral" && "border-border bg-muted/45 text-muted-foreground",
    )}>{label}</span>
  );
}

export function DataState({
  kind,
  title,
  description,
  onRetry,
}: {
  kind: "empty" | "error" | "unavailable";
  title: string;
  description: string;
  onRetry?: () => void;
}) {
  const Icon = kind === "empty" ? Inbox : AlertTriangle;
  return (
    <div role={kind === "error" ? "alert" : "status"} className="flex min-h-32 flex-col items-center justify-center rounded-lg border border-dashed border-border/80 bg-muted/15 px-5 py-8 text-center">
      <span className={cn("grid size-9 place-items-center rounded-full bg-muted text-muted-foreground", kind !== "empty" && "bg-warning/10 text-warning")}><Icon className="size-4" aria-hidden /></span>
      <p className="mt-3 text-sm font-medium">{title}</p>
      <p className="mt-1 max-w-md text-xs leading-5 text-muted-foreground">{description}</p>
      {onRetry && <Button variant="outline" size="sm" className="mt-3" onClick={onRetry}><RefreshCw className="size-3.5" />Retry</Button>}
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("animate-pulse rounded-md bg-muted/75 motion-reduce:animate-none", className)} />;
}

export function PageSkeleton() {
  return (
    <div className="space-y-5" aria-label="Loading workspace" role="status">
      <div className="space-y-2"><Skeleton className="h-3 w-24" /><Skeleton className="h-7 w-64" /><Skeleton className="h-4 w-96 max-w-full" /></div>
      <div className="grid gap-4 lg:grid-cols-3"><Skeleton className="h-72 lg:col-span-2" /><Skeleton className="h-72" /></div>
      <Skeleton className="h-56" />
      <span className="sr-only">Loading financial data</span>
    </div>
  );
}
