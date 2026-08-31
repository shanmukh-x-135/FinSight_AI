import { Bot } from "lucide-react";
import Link from "next/link";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export interface ContextualAction {
  label: string;
  prompt: string;
}

export function ContextualAIActions({ actions, label = "Contextual AI actions" }: { actions: ContextualAction[]; label?: string }) {
  return <nav aria-label={label} className="flex flex-wrap gap-2">{actions.map((action) => <Link key={action.label} href={`/chat?prompt=${encodeURIComponent(action.prompt)}`} className={cn(buttonVariants({ size: "sm", variant: "outline" }), "h-8 text-xs")}><Bot className="size-3.5" aria-hidden />{action.label}</Link>)}</nav>;
}
