"use client";

import { ArrowLeft, LoaderCircle, MailCheck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    const normalized = email.trim().toLowerCase();
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalized)) {
      setError("Enter a valid email address.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.forgotPassword(normalized);
      setSent(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Password recovery is temporarily unavailable.");
    } finally {
      setSubmitting(false);
    }
  }

  if (sent) {
    return (
      <div aria-live="polite">
        <span className="grid size-10 place-items-center rounded-full bg-positive/12 text-positive"><MailCheck className="size-5" /></span>
        <p className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-positive">Request received</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.035em]">Check your inbox</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">If an eligible account exists for <span className="text-foreground">{email.trim().toLowerCase()}</span>, we sent a secure reset link. It expires shortly.</p>
        <Link href="/login" className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-primary hover:underline"><ArrowLeft className="size-4" />Return to sign in</Link>
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Account recovery</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-[-0.035em]">Reset your password</h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">Enter your account email. We’ll send a single-use link if the account is eligible.</p>
      {error && <p id="forgot-error" role="alert" className="mt-6 border-l-2 border-negative bg-negative/8 px-3 py-2.5 text-sm">{error}</p>}
      <form onSubmit={submit} noValidate aria-busy={submitting} className="mt-8 space-y-5">
        <div className="space-y-2"><Label htmlFor="recovery-email">Email address</Label><Input id="recovery-email" type="email" inputMode="email" autoComplete="email" autoCapitalize="none" spellCheck={false} value={email} onChange={(event) => setEmail(event.target.value)} onBlur={() => setEmail((value) => value.trim().toLowerCase())} placeholder="you@example.com" required aria-invalid={Boolean(error)} aria-describedby={error ? "forgot-error" : undefined} className="h-11 bg-muted/25 px-3" /></div>
        <Button type="submit" size="lg" className="h-11 w-full" disabled={submitting}>{submitting && <LoaderCircle className="animate-spin motion-reduce:animate-none" />}{submitting ? "Sending secure link…" : "Send reset link"}</Button>
      </form>
      <Link href="/login" className="mt-8 inline-flex items-center gap-2 text-sm font-medium text-muted-foreground hover:text-foreground"><ArrowLeft className="size-4" />Back to sign in</Link>
    </div>
  );
}
