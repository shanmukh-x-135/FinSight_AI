"use client";

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
    <main className="grid min-h-screen place-items-center bg-background p-6 text-foreground">
      <div className="max-w-md text-center" aria-live="polite">
        {status === "unavailable" ? (
          <>
            <h1 className="text-xl font-semibold">Google sign-in is taking longer than expected</h1>
            <p className="mt-2 text-sm text-muted-foreground">{error}</p>
            <button type="button" className="mt-5 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" onClick={() => void refreshUser()}>
              Check again
            </button>
          </>
        ) : status === "unauthenticated" || status === "expired" ? (
          <>
            <h1 className="text-xl font-semibold">Google sign-in could not be completed</h1>
            <button type="button" className="mt-5 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" onClick={() => router.replace("/login?oauthError=provider_error")}>
              Return to sign in
            </button>
          </>
        ) : (
          <>
            <h1 className="text-xl font-semibold">Securing your FinSight session</h1>
            <p className="mt-2 text-sm text-muted-foreground">Verifying your Google identity…</p>
          </>
        )}
      </div>
    </main>
  );
}
