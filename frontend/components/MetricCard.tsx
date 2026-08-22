import type { ReactNode } from "react";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * MetricCard — a single labelled KPI tile (design doc component library).
 *
 * Presentational and dependency-free so it composes into any Analytics-template
 * summary row and is trivially unit-testable. `tone` drives the semantic colour
 * (green up / red down / neutral); pass an optional Lucide `icon` node.
 */
export type Tone = "positive" | "negative" | "neutral" | "default";

const toneClass: Record<Tone, string> = {
  positive: "text-positive",
  negative: "text-negative",
  neutral: "text-muted-foreground",
  default: "",
};

/** Map a signed number to a tone (0 → neutral). */
export function toneOf(n: number | null | undefined): Tone {
  if (n == null) return "default";
  if (n > 0) return "positive";
  if (n < 0) return "negative";
  return "neutral";
}

export interface MetricCardProps {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}

export function MetricCard({ label, value, sub, tone = "default", icon }: MetricCardProps) {
  return (
    <Card size="sm" className="gap-0 border-border/70 bg-card/80 py-0 shadow-none ring-0">
      <CardContent className="px-3 py-3">
        <div className="flex items-center justify-between">
          <p className="text-xs text-muted-foreground">{label}</p>
          {icon && <span className="text-muted-foreground">{icon}</span>}
        </div>
        <p className={cn("mt-1 text-lg font-semibold tracking-tight", toneClass[tone])}>{value}</p>
        {sub != null && (
          <p className={cn("text-xs", tone === "default" ? "text-muted-foreground" : toneClass[tone])}>
            {sub}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
