"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { useAuth } from "@/lib/auth-context";

function intendedRoute(): string {
  const requested = new URLSearchParams(window.location.search).get("returnTo");
  return requested?.startsWith("/") && !requested.startsWith("//")
    ? requested
    : "/dashboard";
}

export default function AuthLayout({ children }: { children: ReactNode }) {
  const { status, refreshUser, error } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") router.replace(intendedRoute());
  }, [router, status]);

  if (status === "checking" || status === "refreshing" || status === "authenticated") {
    return (
      <main className="grid min-h-screen place-items-center p-6" aria-live="polite">
        <p className="text-sm text-muted-foreground">Checking your FinSight session…</p>
      </main>
    );
  }

  if (status === "unavailable") {
    return (
      <main className="grid min-h-screen place-items-center p-6">
        <div className="max-w-md text-center">
          <h1 className="text-xl font-semibold">FinSight is taking longer than expected</h1>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
          <button type="button" className="mt-5 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" onClick={() => void refreshUser()}>
            Check again
          </button>
        </div>
      </main>
    );
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight">FinSight AI</h1>
        <p className="mt-1 text-sm text-muted-foreground">AI-Powered Financial Intelligence</p>
      </div>
      {children}
    </div>
  );
}
