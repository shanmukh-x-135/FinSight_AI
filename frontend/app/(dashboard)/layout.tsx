"use client";

/**
 * Protected shell for authenticated screens. Redirects unauthenticated users to
 * /login once the auth state has resolved. Renders a minimal top bar with the
 * signed-in email and a logout button. Real navigation/sidebar arrives in
 * Phase 7 (Dashboard UI).
 */

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, type ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { PageSkeleton } from "@/components/workspace";
import { useAuth } from "@/lib/auth-context";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, status, loading, isAuthenticated, logout, refreshUser, error } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const hadAuthenticatedSession = useRef(false);

  useEffect(() => {
    if (isAuthenticated) hadAuthenticatedSession.current = true;
  }, [isAuthenticated]);

  useEffect(() => {
    if (status === "unauthenticated" || status === "expired") {
      const query = window.location.search.slice(1);
      const returnTo = `${pathname}${query ? `?${query}` : ""}`;
      const reason = status === "expired"
        ? "expired"
        : hadAuthenticatedSession.current
          ? "signedOut"
          : null;
      const params = new URLSearchParams({ returnTo });
      if (reason) params.set("reason", reason);
      router.replace(`/login?${params}`);
    }
  }, [pathname, router, status]);

  if (status === "unavailable") {
    return (
      <main className="dark grid min-h-screen place-items-center bg-background p-6 text-foreground">
        <div className="max-w-md text-center">
          <h1 className="text-xl font-semibold">Session check unavailable</h1>
          <p className="mt-2 text-sm text-muted-foreground">{error}</p>
          <button className="mt-5 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground" type="button" onClick={() => void refreshUser()}>
            Try again
          </button>
        </div>
      </main>
    );
  }

  if (loading || !isAuthenticated) {
    return (
      <div className="dark min-h-screen bg-background p-6 text-foreground">
        <PageSkeleton />
      </div>
    );
  }

  return <AppShell email={user?.email} isAdmin={user?.is_admin} onLogout={logout}>{children}</AppShell>;
}
