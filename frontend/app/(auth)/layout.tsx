"use client";

import { ArrowRight, Database, History, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/lib/auth-context";

function intendedRoute(): string {
  const requested = new URLSearchParams(window.location.search).get("returnTo");
  return requested?.startsWith("/") && !requested.startsWith("//")
    ? requested
    : "/dashboard";
}

function ResearchPanel() {
  return (
    <section className="relative hidden min-h-screen overflow-hidden border-r border-white/8 bg-[#0b1220] p-10 text-white lg:flex lg:flex-col xl:p-14">
      <div className="surface-grid absolute inset-0 opacity-20" aria-hidden="true" />
      <div className="relative z-10 flex items-center gap-3">
        <span className="grid size-9 place-items-center rounded-lg bg-blue-400 text-sm font-black text-[#0b1220]">F</span>
        <span className="text-sm font-semibold tracking-tight">FinSight <span className="text-blue-300">AI</span></span>
      </div>

      <div className="relative z-10 my-auto max-w-xl py-16">
        <p className="mb-5 text-xs font-semibold uppercase tracking-[0.22em] text-blue-300/80">Financial intelligence workspace</p>
        <h1 className="max-w-lg text-4xl font-semibold leading-[1.08] tracking-[-0.04em] xl:text-5xl">
          Research markets with evidence, not noise.
        </h1>
        <p className="mt-5 max-w-md text-sm leading-6 text-slate-300">
          Deterministic analytics establish the facts. FinSight explains the evidence, uncertainty, and risk around them.
        </p>

        <div className="mt-12 border-y border-white/10 py-7">
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-5 text-sm">
            <span className="grid size-8 place-items-center rounded-md bg-blue-400/10 text-blue-300"><Database className="size-4" /></span>
            <div><p className="font-medium text-slate-100">Market evidence</p><p className="mt-1 text-xs leading-5 text-slate-400">Breadth, indicators, sentiment, and fundamentals remain inspectable.</p></div>
            <span className="grid size-8 place-items-center rounded-md bg-blue-400/10 text-blue-300"><History className="size-4" /></span>
            <div><p className="font-medium text-slate-100">Historical context</p><p className="mt-1 text-xs leading-5 text-slate-400">Comparable regimes frame probabilities without pretending to predict prices.</p></div>
            <span className="grid size-8 place-items-center rounded-md bg-blue-400/10 text-blue-300"><ShieldCheck className="size-4" /></span>
            <div><p className="font-medium text-slate-100">Research discipline</p><p className="mt-1 text-xs leading-5 text-slate-400">Confidence, risks, and source provenance stay attached to every conclusion.</p></div>
          </div>
        </div>
      </div>

      <p className="relative z-10 flex items-center gap-2 text-xs text-slate-500">
        Indian markets first <ArrowRight className="size-3" /> End-of-day research
      </p>
    </section>
  );
}

function AuthFrame({ children }: { children: ReactNode }) {
  return (
    <main className="dark min-h-screen bg-background text-foreground lg:grid lg:grid-cols-[minmax(0,1.08fr)_minmax(28rem,0.92fr)]">
      <ResearchPanel />
      <section className="flex min-h-screen flex-col px-5 py-6 sm:px-10 lg:px-14 xl:px-20">
        <div className="flex items-center gap-2.5 lg:hidden">
          <span className="grid size-8 place-items-center rounded-lg bg-primary text-xs font-black text-primary-foreground">F</span>
          <span className="text-sm font-semibold">FinSight AI</span>
        </div>
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="w-full max-w-[27rem]">{children}</div>
        </div>
        <p className="text-center text-[11px] leading-5 text-muted-foreground">Research assistance only. Not investment advice or a price prediction.</p>
      </section>
    </main>
  );
}

export default function AuthLayout({ children }: { children: ReactNode }) {
  const { status, refreshUser, error } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") router.replace(intendedRoute());
  }, [router, status]);

  if (status === "checking" || status === "refreshing" || status === "authenticated") {
    return <AuthFrame><div className="space-y-4" aria-live="polite"><div className="h-2 w-20 animate-pulse rounded-full bg-primary/40 motion-reduce:animate-none" /><h1 className="text-2xl font-semibold tracking-tight">Checking your session</h1><p className="text-sm text-muted-foreground">Restoring your secure FinSight workspace…</p></div></AuthFrame>;
  }

  if (status === "unavailable") {
    return <AuthFrame><div><p className="text-xs font-semibold uppercase tracking-[0.18em] text-warning">Connection delayed</p><h1 className="mt-3 text-2xl font-semibold tracking-tight">FinSight is taking longer than expected</h1><p className="mt-3 text-sm leading-6 text-muted-foreground">{error}</p><button type="button" className="mt-6 h-10 rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground focus-visible:outline-none focus-visible:ring-3 focus-visible:ring-ring/50" onClick={() => void refreshUser()}>Check again</button></div></AuthFrame>;
  }

  return <AuthFrame>{children}</AuthFrame>;
}
