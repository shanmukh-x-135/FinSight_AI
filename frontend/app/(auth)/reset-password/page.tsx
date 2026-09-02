"use client";

import { Eye, EyeOff, LoaderCircle, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState, type FormEvent } from "react";

import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

export default function ResetPasswordPage() {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [complete, setComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setError(null);
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) return setError("This reset link is incomplete. Request a new one.");
    if (password.length < 8) return setError("Use at least 8 characters for your new password.");
    if (password !== confirmation) return setError("The passwords do not match.");
    setSubmitting(true);
    try {
      await api.resetPassword(token, password);
      setComplete(true);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "FinSight could not reset your password.");
    } finally {
      setSubmitting(false);
    }
  }

  if (complete) {
    return (
      <div aria-live="polite">
        <span className="grid size-10 place-items-center rounded-full bg-positive/12 text-positive"><ShieldCheck className="size-5" /></span>
        <p className="mt-6 text-xs font-semibold uppercase tracking-[0.18em] text-positive">Password secured</p>
        <h1 className="mt-3 text-3xl font-semibold tracking-[-0.035em]">Your password has been reset</h1>
        <p className="mt-3 text-sm leading-6 text-muted-foreground">Existing sessions were signed out. Use your new password to return to FinSight.</p>
        <Link href="/login" className={buttonVariants({ size: "lg", className: "mt-8 h-11 w-full" })}>Continue to sign in</Link>
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-primary">Secure recovery</p>
      <h1 className="mt-3 text-3xl font-semibold tracking-[-0.035em]">Choose a new password</h1>
      <p className="mt-2 text-sm leading-6 text-muted-foreground">The reset link is single-use. Completing it signs out existing sessions.</p>
      {error && <p id="reset-error" role="alert" className="mt-6 border-l-2 border-negative bg-negative/8 px-3 py-2.5 text-sm">{error}</p>}
      <form onSubmit={submit} noValidate aria-busy={submitting} className="mt-8 space-y-5">
        <div className="space-y-2"><Label htmlFor="new-password">New password</Label><div className="relative"><Input id="new-password" type={showPassword ? "text" : "password"} autoComplete="new-password" minLength={8} required value={password} onChange={(event) => setPassword(event.target.value)} className="h-11 bg-muted/25 px-3 pr-11" aria-invalid={Boolean(error)} aria-describedby="reset-password-hint" /><button type="button" onClick={() => setShowPassword((value) => !value)} className="absolute inset-y-0 right-0 grid w-11 place-items-center text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring" aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}</button></div><p id="reset-password-hint" className="text-xs text-muted-foreground">Use 8–128 characters.</p></div>
        <div className="space-y-2"><Label htmlFor="confirm-password">Confirm new password</Label><Input id="confirm-password" type={showPassword ? "text" : "password"} autoComplete="new-password" required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} className="h-11 bg-muted/25 px-3" aria-invalid={Boolean(error)} aria-describedby={error ? "reset-error" : undefined} /></div>
        <Button type="submit" size="lg" className="h-11 w-full" disabled={submitting}>{submitting && <LoaderCircle className="animate-spin motion-reduce:animate-none" />}{submitting ? "Securing password…" : "Reset password"}</Button>
      </form>
      <p className="mt-8 text-center text-sm text-muted-foreground">Need another link? <Link href="/forgot-password" className="font-medium text-foreground hover:text-primary hover:underline">Start again</Link></p>
    </div>
  );
}
