"use client";

/**
 * Shared login/register form. One component, two modes, so the two auth pages
 * don't duplicate field/validation/submit logic.
 */

import { useRouter } from "next/navigation";
import Link from "next/link";
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
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

type Mode = "login" | "register";

const COPY: Record<Mode, { title: string; desc: string; cta: string; alt: string; altHref: string; altLabel: string }> = {
  login: {
    title: "Welcome back",
    desc: "Log in to your FinSight AI account.",
    cta: "Log in",
    alt: "Don't have an account?",
    altHref: "/register",
    altLabel: "Create one",
  },
  register: {
    title: "Create your account",
    desc: "Start your personalized market intelligence.",
    cta: "Create account",
    alt: "Already have an account?",
    altHref: "/login",
    altLabel: "Log in",
  },
};

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const { login, register } = useAuth();
  const copy = COPY[mode];

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("oauthError");
    const timer = window.setTimeout(() => {
      if (!code) return;
      setError(
        code === "provider_denied"
          ? "Google sign-in was cancelled."
          : "Google sign-in could not be completed. Please try again.",
      );
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function continueWithGoogle() {
    const requested = new URLSearchParams(window.location.search).get("returnTo");
    const returnTo = requested?.startsWith("/") && !requested.startsWith("//")
      ? requested
      : "/dashboard";
    window.location.assign(api.googleStartUrl(returnTo));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);

    if (mode === "register" && password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      const requested = new URLSearchParams(window.location.search).get("returnTo");
      const returnTo = requested?.startsWith("/") && !requested.startsWith("//")
        ? requested
        : "/dashboard";
      router.replace(returnTo);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Something went wrong. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader>
        <CardTitle className="text-2xl">{copy.title}</CardTitle>
        <CardDescription>{copy.desc}</CardDescription>
      </CardHeader>
      <form onSubmit={onSubmit} noValidate>
        <CardContent className="flex flex-col gap-4">
          <Button type="button" variant="outline" className="w-full" onClick={continueWithGoogle} disabled={submitting}>
            Continue with Google
          </Button>
          <div className="flex items-center gap-3 text-xs text-muted-foreground" aria-hidden="true">
            <span className="h-px flex-1 bg-border" />or<span className="h-px flex-1 bg-border" />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              required
              minLength={mode === "register" ? 8 : undefined}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          {error && (
            <p role="alert" className="text-sm text-red-600">
              {error}
            </p>
          )}
        </CardContent>
        <CardFooter className="mt-4 flex flex-col gap-3">
          <Button type="submit" className="w-full" disabled={submitting}>
            {submitting ? "Please wait…" : copy.cta}
          </Button>
          <p className="text-center text-sm text-muted-foreground">
            {copy.alt}{" "}
            <Link href={copy.altHref} className="font-medium text-blue-600 hover:underline">
              {copy.altLabel}
            </Link>
          </p>
        </CardFooter>
      </form>
    </Card>
  );
}
