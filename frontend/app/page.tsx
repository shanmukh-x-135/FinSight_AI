"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { buttonVariants } from "@/components/ui/button";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ConnState = "checking" | "connected" | "unreachable";

interface HealthResponse {
  status: string;
  service?: string;
  env?: string;
}

/** Public landing page with a live API health signal and auth entry points. */
export default function Home() {
  const [state, setState] = useState<ConnState>("checking");
  const [health, setHealth] = useState<HealthResponse | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch(`${API_URL}/health`, { cache: "no-store" });
        if (!res.ok) throw new Error(`status ${res.status}`);
        const data: HealthResponse = await res.json();
        if (!cancelled) {
          setHealth(data);
          setState("connected");
        }
      } catch {
        if (!cancelled) setState("unreachable");
      }
    }

    check();
    return () => {
      cancelled = true;
    };
  }, []);

  const statusColor =
    state === "connected"
      ? "text-green-600"
      : state === "unreachable"
        ? "text-red-600"
        : "text-blue-600";

  const statusLabel =
    state === "connected"
      ? "Backend connected"
      : state === "unreachable"
        ? "Backend unreachable"
        : "Checking backend…";

  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <div className="text-center">
        <h1 className="text-4xl font-bold tracking-tight">FinSight AI</h1>
        <p className="mt-2 text-sm text-gray-500">
          AI-Powered Financial Intelligence Platform
        </p>
      </div>

      <div className="flex flex-col items-center gap-2 rounded-xl border border-gray-200 px-8 py-6 shadow-sm dark:border-gray-800">
        <div className="flex items-center gap-2">
          <span
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              state === "connected"
                ? "bg-green-500"
                : state === "unreachable"
                  ? "bg-red-500"
                  : "bg-blue-500 animate-pulse"
            }`}
            aria-hidden
          />
          <span className={`font-medium ${statusColor}`}>{statusLabel}</span>
        </div>
        {health && (
          <p className="text-xs text-gray-500">
            {health.service} · env: {health.env}
          </p>
        )}
        <p className="mt-1 text-xs text-gray-400">API: {API_URL}</p>
      </div>

      <div className="flex gap-3">
        <Link href="/register" className={buttonVariants()}>
          Get started
        </Link>
        <Link href="/login" className={buttonVariants({ variant: "outline" })}>
          Log in
        </Link>
      </div>
    </main>
  );
}
