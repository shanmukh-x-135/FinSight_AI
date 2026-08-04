import { CircleAlert, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";

export interface AIAnalysisStateProps {
  status: "empty" | "unavailable";
  message: string;
}

/** Honest, consistent empty/error state for an Analytics template's AI slot. */
export function AIAnalysisState({ status, message }: AIAnalysisStateProps) {
  const unavailable = status === "unavailable";
  const Icon = unavailable ? CircleAlert : Sparkles;

  return (
    <div
      role="status"
      className={cn(
        "flex items-start gap-3 rounded-lg border border-dashed p-4 text-sm",
        unavailable
          ? "border-amber-500/40 bg-amber-500/5 text-foreground"
          : "text-muted-foreground",
      )}
    >
      <Icon
        className={cn("mt-0.5 h-4 w-4 shrink-0", unavailable && "text-amber-600")}
        aria-hidden
      />
      <p>{message}</p>
    </div>
  );
}
