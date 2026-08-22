"use client";

/**
 * Protected shell for authenticated screens. Redirects unauthenticated users to
 * /login once the auth state has resolved. Renders a minimal top bar with the
 * signed-in email and a logout button. Real navigation/sidebar arrives in
 * Phase 7 (Dashboard UI).
 */

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { AppShell } from "@/components/app-shell";
import { PageSkeleton } from "@/components/workspace";
import { useAuth } from "@/lib/auth-context";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, loading, isAuthenticated, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [loading, isAuthenticated, router]);

  if (loading || !isAuthenticated) {
    return (
      <div className="dark min-h-screen bg-background p-6 text-foreground">
        <PageSkeleton />
      </div>
    );
  }

  return <AppShell email={user?.email} onLogout={logout}>{children}</AppShell>;
}
