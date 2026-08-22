"use client";

import { useEffect } from "react";

import { DataState } from "@/components/workspace";

export default function DashboardError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return <DataState kind="error" title="Workspace unavailable" description="The requested research view could not be rendered. Your data has not been changed." onRetry={retry} />;
}
