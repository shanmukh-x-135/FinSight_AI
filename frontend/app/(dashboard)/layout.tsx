"use client";

/**
 * Protected shell for authenticated screens. Redirects unauthenticated users to
 * /login once the auth state has resolved. Renders a minimal top bar with the
 * signed-in email and a logout button. Real navigation/sidebar arrives in
 * Phase 7 (Dashboard UI).
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
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
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading…</p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b px-6 py-3">
        <div className="flex items-center gap-6">
          <Link href="/dashboard" className="font-semibold">
            FinSight AI
          </Link>
          <nav className="hidden gap-4 text-sm text-muted-foreground sm:flex">
            <Link href="/dashboard" className="hover:text-foreground">
              Dashboard
            </Link>
            <Link href="/market" className="hover:text-foreground">
              Market
            </Link>
            <Link href="/history" className="hover:text-foreground">
              History
            </Link>
            <Link href="/portfolio" className="hover:text-foreground">
              Portfolio
            </Link>
            <Link href="/watchlist" className="hover:text-foreground">
              Watchlist
            </Link>
            <Link href="/reports" className="hover:text-foreground">
              Reports
            </Link>
            <Link href="/chat" className="hover:text-foreground">
              Assistant
            </Link>
            <Link href="/settings" className="hover:text-foreground">
              Settings
            </Link>
          </nav>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm text-muted-foreground">{user?.email}</span>
          <Button variant="outline" size="sm" onClick={logout}>
            Log out
          </Button>
        </div>
      </header>
      {/* Mobile nav strip — prioritized screens, horizontally scrollable. */}
      <nav className="flex gap-4 overflow-x-auto border-b px-6 py-2 text-sm text-muted-foreground sm:hidden">
        <Link href="/dashboard" className="whitespace-nowrap hover:text-foreground">Dashboard</Link>
        <Link href="/market" className="whitespace-nowrap hover:text-foreground">Market</Link>
        <Link href="/history" className="whitespace-nowrap hover:text-foreground">History</Link>
        <Link href="/portfolio" className="whitespace-nowrap hover:text-foreground">Portfolio</Link>
        <Link href="/reports" className="whitespace-nowrap hover:text-foreground">Reports</Link>
        <Link href="/chat" className="whitespace-nowrap hover:text-foreground">Assistant</Link>
        <Link href="/watchlist" className="whitespace-nowrap hover:text-foreground">Watchlist</Link>
        <Link href="/settings" className="whitespace-nowrap hover:text-foreground">Settings</Link>
      </nav>
      <main className="flex-1 p-4 sm:p-6">{children}</main>
    </div>
  );
}
