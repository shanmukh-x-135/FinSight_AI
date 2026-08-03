import type { ReactNode } from "react";

/** Centers auth screens (login/register) on the page. */
export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight">FinSight AI</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          AI-Powered Financial Intelligence
        </p>
      </div>
      {children}
    </div>
  );
}
