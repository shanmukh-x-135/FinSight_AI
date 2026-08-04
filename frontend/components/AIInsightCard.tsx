"use client";

import { Sparkles } from "lucide-react";

import { EvidencePanel, type EvidencePanelProps } from "@/components/EvidencePanel";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

/**
 * AIInsightCard — the standard container for any AI-written insight.
 *
 * Renders the LLM prose (or deterministic narrative) with a title, an optional
 * action badge, and — when evidence is supplied — the reusable EvidencePanel so
 * "Show Evidence" behaves identically on every insight across every screen. The
 * card itself never computes anything; it displays already-built content.
 */
const actionStyle: Record<string, string> = {
  watch: "bg-green-100 text-green-700",
  avoid: "bg-red-100 text-red-700",
  hold: "bg-muted text-muted-foreground",
};

export interface AIInsightCardProps {
  title: string;
  narrative: string;
  action?: string;
  confidence?: number;
  evidence?: EvidencePanelProps;
}

export function AIInsightCard({ title, narrative, action, confidence, evidence }: AIInsightCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Sparkles className="h-4 w-4 text-blue-600" aria-hidden />
          <span className="flex-1">{title}</span>
          {action && (
            <span className={cn("rounded-full px-2 py-0.5 text-xs font-medium capitalize", actionStyle[action] ?? "bg-muted")}>
              {action}
            </span>
          )}
          {confidence != null && (
            <span className="text-xs font-normal text-muted-foreground">{confidence}% conf.</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm leading-relaxed text-foreground/90">{narrative}</p>
        {evidence && <EvidencePanel {...evidence} confidence={evidence.confidence ?? confidence} />}
      </CardContent>
    </Card>
  );
}
