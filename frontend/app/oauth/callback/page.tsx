"use client";

import { LoaderCircle, ShieldCheck } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { publishAuthEvent } from "@/lib/auth-events";
import { useAuth } from "@/lib/auth-context";

function returnPath(): string {
  const requested = new URLSearchParams(window.location.search).get("returnTo");
  return requested?.startsWith("/") && !requested.startsWith("//")
    ? requested
    : "/dashboard";
}

export default function OAuthCallbackPage() {
  const { status, error, refreshUser } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "authenticated") {
      publishAuthEvent("login");
      router.replace(returnPath());
    }
  }, [router, status]);

  return (
    <main className="dark relative grid min-h-screen place-items-center overflow-hidden bg-background p-6 text-foreground">
      <div className="surface-grid absolute inset-0 opacity-20" aria-hidden="true" />
      <div className="relative z-10 w-full max-w-md border-y border-border/60 py-10 text-center" aria-live="polite">
        <span className="mx-auto grid size-10 place-items-center rounded-lg bg-primary text-sm font-black text-primary-foreground">F</span>
        {status === "unavailable" ? (
          <>
            <p className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-warning">Connection delayed</p>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight">Google sign-in is taking longer than expected</h1>
            <p className="mt-2 text-sm text-muted-foreground">{error}</p>
            <button type="button" className="mt-5 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" onClick={() => void refreshUser()}>
              Check again
            </button>
          </>
        ) : status === "unauthenticated" || status === "expired" ? (
          <>
            <p className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-negative">Verification incomplete</p>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight">Google sign-in could not be completed</h1>
            <button type="button" className="mt-5 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" onClick={() => router.replace("/login?oauthError=provider_error")}>
              Return to sign in
            </button>
          </>
        ) : (
          <>
            <ShieldCheck className="mx-auto mt-6 size-5 text-primary" aria-hidden="true" />
            <h1 className="mt-4 text-2xl font-semibold tracking-tight">Securing your FinSight session</h1>
            <p className="mt-2 flex items-center justify-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-3.5 animate-spin motion-reduce:animate-none" />Verifying your Google identity…</p>
          </>
        )}
      </div>
    </main>
  );
}
