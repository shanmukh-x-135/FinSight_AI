"use client";

import {
  Binoculars,
  Bot,
  BriefcaseBusiness,
  FileText,
  History,
  LineChart,
  Search,
  Telescope,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { marketApi, type MarketStockSnapshot } from "@/lib/api";
import { cn } from "@/lib/utils";

const destinations = [
  { label: "Search the market", hint: "Screener and movers", href: "/market", icon: Binoculars },
  { label: "Open portfolio", hint: "Holdings, P&L, and risk", href: "/portfolio", icon: BriefcaseBusiness },
  { label: "Open watchlist", hint: "Monitored instruments", href: "/watchlist", icon: Telescope },
  { label: "Open historical research", hint: "Comparable market regimes", href: "/history", icon: History },
  { label: "Open strategies", hint: "Rules and backtests", href: "/strategies", icon: LineChart },
  { label: "Open today’s movers", hint: "Market breadth and leaders", href: "/market", icon: Search },
  { label: "Open reports", hint: "Generated research archive", href: "/reports", icon: FileText },
  { label: "Ask FinSight", hint: "Start an evidence-backed conversation", href: "/chat", icon: Bot },
] as const;

export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [stocks, setStocks] = useState<MarketStockSnapshot[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);

  useEffect(() => {
    if (!open) return;
    const frame = requestAnimationFrame(() => inputRef.current?.focus());
    let active = true;
    if (stocks.length === 0) {
      marketApi.stocks("NIFTY100").then((rows) => active && setStocks(rows)).catch(() => undefined);
    }
    return () => { active = false; cancelAnimationFrame(frame); };
  }, [open, stocks.length]);

  const results = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const routes = destinations
      .filter((item) => !normalized || `${item.label} ${item.hint}`.toLowerCase().includes(normalized))
      .map((item) => ({ ...item, key: item.label }));
    const instruments = normalized.length < 1 ? [] : stocks
      .filter((stock) => `${stock.symbol} ${stock.name ?? ""}`.toLowerCase().includes(normalized))
      .slice(0, 6)
      .map((stock) => ({
        label: stock.symbol,
        hint: stock.name ?? "Open stock research",
        href: `/market/${encodeURIComponent(stock.symbol)}`,
        icon: Binoculars,
        key: stock.symbol,
      }));
    return [...instruments, ...routes].slice(0, 9);
  }, [query, stocks]);

  function choose(href: string) {
    setQuery("");
    setActiveIndex(0);
    onOpenChange(false);
    router.push(href);
  }

  function close() {
    setQuery("");
    setActiveIndex(0);
    onOpenChange(false);
  }

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[80] grid items-start justify-items-center bg-slate-950/70 px-3 pt-[12vh] backdrop-blur-sm motion-safe:animate-in motion-safe:fade-in" onMouseDown={close}>
      <section
        role="dialog"
        aria-modal="true"
        aria-label="FinSight command palette"
        className="w-full max-w-xl overflow-hidden rounded-2xl border border-white/10 bg-popover shadow-2xl shadow-black/40"
        onMouseDown={(event) => event.stopPropagation()}
        onKeyDown={(event) => {
          if (event.key === "Escape") close();
          if (event.key === "ArrowDown") { event.preventDefault(); setActiveIndex((value) => Math.min(value + 1, results.length - 1)); }
          if (event.key === "ArrowUp") { event.preventDefault(); setActiveIndex((value) => Math.max(value - 1, 0)); }
          if (event.key === "Enter" && results[activeIndex]) { event.preventDefault(); choose(results[activeIndex].href); }
        }}
      >
        <label className="flex h-14 items-center gap-3 border-b border-border/60 px-4">
          <Search className="size-4 text-muted-foreground" aria-hidden />
          <span className="sr-only">Search commands and instruments</span>
          <input ref={inputRef} aria-label="Search commands and instruments" value={query} onChange={(event) => { setQuery(event.target.value); setActiveIndex(0); }} placeholder="Search instruments, pages, or actions…" className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground" />
          <kbd className="hidden rounded-md border border-border/70 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground sm:block">ESC</kbd>
        </label>
        <div role="listbox" aria-label="Commands" className="max-h-[min(26rem,60vh)] overflow-y-auto p-2">
          {results.length === 0 ? (
            <p className="px-3 py-10 text-center text-sm text-muted-foreground">No matching instruments or actions.</p>
          ) : results.map((item, index) => {
            const Icon = item.icon;
            return (
              <button key={item.key} type="button" role="option" aria-selected={index === activeIndex} onMouseEnter={() => setActiveIndex(index)} onClick={() => choose(item.href)} className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left outline-none", index === activeIndex ? "bg-primary/12 text-foreground" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground")}>
                <span className={cn("grid size-8 shrink-0 place-items-center rounded-lg bg-muted", index === activeIndex && "bg-primary/15 text-primary")}><Icon className="size-4" aria-hidden /></span>
                <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{item.label}</span><span className="block truncate text-xs text-muted-foreground">{item.hint}</span></span>
                <span className="font-mono text-[10px] text-muted-foreground">↵</span>
              </button>
            );
          })}
        </div>
        <footer className="flex items-center gap-4 border-t border-border/60 px-4 py-2 text-[10px] text-muted-foreground"><span>↑↓ Navigate</span><span>↵ Open</span><span>Esc Close</span></footer>
      </section>
    </div>
  );
}
