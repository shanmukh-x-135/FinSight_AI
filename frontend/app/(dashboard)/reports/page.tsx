"use client";

/**
 * Reports list (Phase 8) — browse report history with date/type filters and
 * pagination, generate a new report, and open any report's detail view.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, reportsApi, type ReportSummary } from "@/lib/api";

const PAGE = 10;

const fmtDate = (iso: string) =>
  new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });

const columns: Column<ReportSummary>[] = [
  { key: "date", header: "Generated", render: (r) => fmtDate(r.created_at) },
  {
    key: "type",
    header: "Type",
    render: (r) => <span className="capitalize">{r.report_type}</span>,
  },
  {
    key: "open",
    header: "",
    align: "right",
    render: (r) => (
      <Link href={`/reports/${r.id}`} className="text-blue-600 hover:underline">
        Open →
      </Link>
    ),
  },
];

const fetchReports = (type: string, start: string, end: string, offset: number) =>
  reportsApi.list({
    report_type: type || undefined,
    start_date: start || undefined,
    end_date: end || undefined,
    limit: PAGE,
    offset,
  });

export default function ReportsPage() {
  const [rows, setRows] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);

  // Filters + pagination.
  const [type, setType] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [offset, setOffset] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchReports(type, start, end, offset);
      setRows(data);
      setError(null);
    } catch {
      setError("Could not load your reports.");
    } finally {
      setLoading(false);
    }
  }, [type, start, end, offset]);

  useEffect(() => {
    let cancelled = false;

    async function loadFromEffect() {
      await Promise.resolve();
      if (cancelled) return;
      setLoading(true);
      try {
        const data = await fetchReports(type, start, end, offset);
        if (cancelled) return;
        setRows(data);
        setError(null);
      } catch {
        if (!cancelled) setError("Could not load your reports.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadFromEffect();
    return () => {
      cancelled = true;
    };
  }, [type, start, end, offset]);

  async function onGenerate() {
    setGenerating(true);
    setError(null);
    try {
      await reportsApi.generate();
      setOffset(0);
      await load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not generate a report.");
    } finally {
      setGenerating(false);
    }
  }

  function applyFilters(e: React.FormEvent) {
    e.preventDefault();
    setOffset(0);
    void load();
  }

  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">Reports</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Your evidence-backed report history. Generate, open, and export as Markdown or PDF.
          </p>
        </div>
        <Button onClick={onGenerate} disabled={generating}>
          {generating ? "Generating…" : "Generate report"}
        </Button>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle className="text-base">Filters</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={applyFilters} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="type">Type</Label>
              <select
                id="type"
                value={type}
                onChange={(e) => setType(e.target.value)}
                className="h-9 rounded-md border bg-transparent px-3 text-sm"
              >
                <option value="">All</option>
                <option value="daily">Daily</option>
                <option value="weekly">Weekly</option>
              </select>
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="start">From</Label>
              <Input id="start" type="date" value={start} onChange={(e) => setStart(e.target.value)} className="w-40" />
            </div>
            <div className="flex flex-col gap-1">
              <Label htmlFor="end">To</Label>
              <Input id="end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="w-40" />
            </div>
            <Button type="submit" variant="outline">Apply</Button>
            {(type || start || end) && (
              <Button
                type="button"
                variant="ghost"
                onClick={() => {
                  setType("");
                  setStart("");
                  setEnd("");
                  setOffset(0);
                }}
              >
                Clear
              </Button>
            )}
          </form>
        </CardContent>
      </Card>

      {error && <p role="alert" className="mt-4 text-sm text-red-600">{error}</p>}

      <div className="mt-6">
        {loading ? (
          <p className="text-sm text-muted-foreground">Loading reports…</p>
        ) : (
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            emptyMessage="No reports yet — generate your first one."
          />
        )}
      </div>

      <div className="mt-4 flex items-center justify-between">
        <Button
          variant="outline"
          size="sm"
          disabled={offset === 0 || loading}
          onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
        >
          ← Previous
        </Button>
        <span className="text-xs text-muted-foreground">
          {offset + 1}–{offset + rows.length}
        </span>
        <Button
          variant="outline"
          size="sm"
          disabled={rows.length < PAGE || loading}
          onClick={() => setOffset((o) => o + PAGE)}
        >
          Next →
        </Button>
      </div>
    </div>
  );
}
