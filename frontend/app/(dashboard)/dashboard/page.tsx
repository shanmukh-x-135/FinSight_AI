"use client";

/**
 * Phase 1 dashboard shell. Confirms an authenticated session and echoes the
 * user's profile + preferences. The real dashboard (market cards, portfolio
 * summary, AI insights) is built in Phase 7.
 */

import Link from "next/link";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { useAuth } from "@/lib/auth-context";

export default function DashboardPage() {
  const { user } = useAuth();
  const prefs = user?.preferences;

  return (
    <div className="mx-auto max-w-3xl">
      <h2 className="text-2xl font-bold">Dashboard</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        You are signed in. Market intelligence arrives in a later phase.
      </p>

      <div className="mt-6 grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Account</CardTitle>
            <CardDescription>Your identity</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              <span className="text-muted-foreground">Email:</span> {user?.email}
            </p>
            <p>
              <span className="text-muted-foreground">Status:</span>{" "}
              <span className="text-green-600">active</span>
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Preferences</CardTitle>
            <CardDescription>
              Drives personalization —{" "}
              <Link href="/settings" className="text-blue-600 hover:underline">
                edit
              </Link>
            </CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              <span className="text-muted-foreground">Risk:</span>{" "}
              {prefs?.risk_tolerance}
            </p>
            <p>
              <span className="text-muted-foreground">Horizon:</span>{" "}
              {prefs?.investment_horizon}
            </p>
            <p>
              <span className="text-muted-foreground">Market:</span>{" "}
              {prefs?.preferred_market}
            </p>
            <p>
              <span className="text-muted-foreground">Sectors:</span>{" "}
              {prefs?.preferred_sectors.length
                ? prefs.preferred_sectors.join(", ")
                : "none set"}
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
