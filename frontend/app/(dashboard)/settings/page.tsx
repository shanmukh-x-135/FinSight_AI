"use client";

/**
 * Preferences settings. Loads the current preferences and lets the user update
 * risk tolerance, investment horizon, preferred market, and sectors — the
 * personalization inputs that drive later report/recommendation logic.
 */

import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, api } from "@/lib/api";
import { PageHeader } from "@/components/workspace";
import { useAuth } from "@/lib/auth-context";

const RISK = ["conservative", "moderate", "aggressive"];
const HORIZON = ["short", "medium", "long"];
const MARKET = ["IN", "US"];

export default function SettingsPage() {
  const { refreshUser } = useAuth();

  const [risk, setRisk] = useState("moderate");
  const [horizon, setHorizon] = useState("medium");
  const [market, setMarket] = useState("IN");
  const [sectors, setSectors] = useState("");

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getPreferences()
      .then((p) => {
        if (cancelled) return;
        setRisk(p.risk_tolerance);
        setHorizon(p.investment_horizon);
        setMarket(p.preferred_market);
        setSectors(p.preferred_sectors.join(", "));
      })
      .catch(() => setError("Could not load preferences."))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setSaving(true);
    setMessage(null);
    setError(null);
    try {
      await api.updatePreferences({
        risk_tolerance: risk,
        investment_horizon: horizon,
        preferred_market: market,
        preferred_sectors: sectors
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      await refreshUser();
      setMessage("Preferences saved.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save preferences.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader eyebrow="Workspace" title="Settings" description="Personalize the deterministic risk and relevance context used in reports and recommendations." />

      <Card className="border-border/70 bg-card/80 shadow-none">
        <CardHeader>
          <CardTitle className="text-base">Investment preferences</CardTitle>
          <CardDescription>Used to tailor reports and recommendations.</CardDescription>
        </CardHeader>
        <form onSubmit={onSubmit}>
          <CardContent className="flex flex-col gap-4">
            {loading ? (
              <p className="text-sm text-muted-foreground">Loading…</p>
            ) : (
              <>
                <div className="flex flex-col gap-2">
                  <Label>Risk tolerance</Label>
                  <Select value={risk} onValueChange={(v) => v && setRisk(v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {RISK.map((v) => (
                        <SelectItem key={v} value={v} className="capitalize">
                          {v}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex flex-col gap-2">
                  <Label>Investment horizon</Label>
                  <Select value={horizon} onValueChange={(v) => v && setHorizon(v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {HORIZON.map((v) => (
                        <SelectItem key={v} value={v} className="capitalize">
                          {v}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex flex-col gap-2">
                  <Label>Preferred market</Label>
                  <Select value={market} onValueChange={(v) => v && setMarket(v)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {MARKET.map((v) => (
                        <SelectItem key={v} value={v}>
                          {v}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className="flex flex-col gap-2">
                  <Label htmlFor="sectors">Preferred sectors</Label>
                  <Input
                    id="sectors"
                    value={sectors}
                    onChange={(e) => setSectors(e.target.value)}
                    placeholder="technology, banking, energy"
                  />
                  <p className="text-xs text-muted-foreground">Comma-separated.</p>
                </div>

                {message && <p className="text-sm text-green-600">{message}</p>}
                {error && (
                  <p role="alert" className="text-sm text-red-600">
                    {error}
                  </p>
                )}
              </>
            )}
          </CardContent>
          <CardFooter className="mt-4">
            <Button type="submit" disabled={saving || loading}>
              {saving ? "Saving…" : "Save preferences"}
            </Button>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
