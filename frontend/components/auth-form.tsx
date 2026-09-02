"use client";

import { Eye, EyeOff, LoaderCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

type Mode = "login" | "register";

const COPY = {
  login: {
    eyebrow: "Secure workspace",
    title: "Welcome back",
    description: "Sign in to continue your market research.",
    submit: "Sign in",
    pending: "Signing in…",
    alt: "New to FinSight?",
    altHref: "/register",
    altLabel: "Create an account",
  },
  register: {
    eyebrow: "Create your workspace",
    title: "Start with the evidence",
    description: "Build a personalized research workspace in a few seconds.",
    submit: "Create account",
    pending: "Creating account…",
    alt: "Already have an account?",
    altHref: "/login",
    altLabel: "Sign in",
  },
} satisfies Record<Mode, Record<string, string>>;

function safeReturnPath(): string {
  const requested = new URLSearchParams(window.location.search).get("returnTo");
  return requested?.startsWith("/") && !requested.startsWith("//")
    ? requested
    : "/dashboard";
}

function queryMessage(): { error: string | null; notice: string | null } {
  const query = new URLSearchParams(window.location.search);
  const oauthError = query.get("oauthError");
  const reason = query.get("reason");
  return {
    error: oauthError
      ? oauthError === "provider_denied"
        ? "Google sign-in was cancelled. No changes were made."
        : oauthError === "identity_conflict"
          ? "This Google identity conflicts with an existing account. Sign in with your existing method first."
          : "Google sign-in could not be completed. Please try again."
      : null,
    notice:
      reason === "expired"
        ? "Your session expired securely. Sign in to continue."
        : reason === "signedOut"
          ? "You have been signed out on this browser."
          : null,
  };
}

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter();
  const { login, register } = useAuth();
  const copy = COPY[mode];
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const message = queryMessage();
      setError(message.error);
      setNotice(message.notice);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function continueWithGoogle() {
    if (submitting) return;
    window.location.assign(api.googleStartUrl(safeReturnPath()));
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setError(null);
    setNotice(null);
    const normalizedEmail = email.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      setError("Enter a valid email address.");
      return;
    }
    if (mode === "register" && password.length < 8) {
      setError("Use at least 8 characters for your password.");
      return;
    }
    if (!password) {
      setError("Enter your password.");
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "login") await login(normalizedEmail, password);
      else await register(normalizedEmail, password);
      router.replace(safeReturnPath());
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "FinSight could not complete the request. Please try again.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">{copy.eyebrow}</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-[-0.035em]">{copy.title}</h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy.description}</p>

      {notice && <p className="mt-6 border-l-2 border-primary bg-primary/8 px-3 py-2.5 text-sm text-foreground" role="status">{notice}</p>}
      {error && <p id="auth-error" role="alert" className="mt-6 border-l-2 border-negative bg-negative/8 px-3 py-2.5 text-sm leading-5 text-foreground">{error}</p>}

      <div className="mt-8 space-y-5">
        <Button type="button" variant="outline" size="lg" className="h-11 w-full border-border/80 bg-transparent" onClick={continueWithGoogle} disabled={submitting}>
          <span className="grid size-5 place-items-center rounded-full bg-foreground text-[10px] font-bold text-background" aria-hidden="true">G</span>
          Continue with Google
        </Button>
        <div className="flex items-center gap-3 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground" aria-hidden="true"><span className="h-px flex-1 bg-border/70" />or use email<span className="h-px flex-1 bg-border/70" /></div>

        <form className="space-y-5" onSubmit={onSubmit} noValidate aria-busy={submitting}>
          <div className="space-y-2">
            <Label htmlFor="email">Email address</Label>
            <Input id="email" type="email" inputMode="email" autoComplete="email" autoCapitalize="none" spellCheck={false} required value={email} onChange={(event) => setEmail(event.target.value)} onBlur={() => setEmail((value) => value.trim().toLowerCase())} placeholder="you@example.com" aria-invalid={Boolean(error)} aria-describedby={error ? "auth-error" : undefined} className="h-11 bg-muted/25 px-3 autofill:bg-muted" />
          </div>
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-3">
              <Label htmlFor="password">Password</Label>
              {mode === "login" && <Link href="/forgot-password" className="text-xs font-medium text-primary outline-none hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring">Forgot password?</Link>}
            </div>
            <div className="relative">
              <Input id="password" type={showPassword ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={mode === "register" ? 8 : undefined} value={password} onChange={(event) => setPassword(event.target.value)} placeholder={mode === "register" ? "At least 8 characters" : "Your password"} aria-invalid={Boolean(error)} aria-describedby={error ? "auth-error" : mode === "register" ? "password-hint" : undefined} className="h-11 bg-muted/25 px-3 pr-11" />
              <button type="button" className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button>
            </div>
            {mode === "register" && <p id="password-hint" className="text-xs leading-5 text-muted-foreground">Use 8–128 characters. Password managers are fully supported.</p>}
          </div>
          <Button type="submit" size="lg" className="h-11 w-full" disabled={submitting}>
            {submitting && <LoaderCircle className="size-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />}
            {submitting ? copy.pending : copy.submit}
          </Button>
        </form>
      </div>

      <p className="mt-8 text-center text-sm text-muted-foreground">{copy.alt} <Link href={copy.altHref} className="font-medium text-foreground outline-none hover:text-primary hover:underline focus-visible:rounded-sm focus-visible:ring-2 focus-visible:ring-ring">{copy.altLabel}</Link></p>
    </div>
  );
}
