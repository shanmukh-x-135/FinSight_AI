"use client";

/**
 * Reports list (Phase 8) — browse report history with date/type filters and
 * pagination, generate a new report, and open any report's detail view.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { DataTable, type Column } from "@/components/DataTable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { ApiError, reportsApi, type ReportSummary } from "@/lib/api";
import { PageHeader, Panel, SectionHeader } from "@/components/workspace";

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
      <Link href={`/reports/${r.id}`} className="text-primary hover:underline">
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
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader eyebrow="Research archive" title="Reports" description="Generate, review, and export evidence-backed research as Markdown or PDF." actions={<Button onClick={onGenerate} disabled={generating}>
          {generating ? "Generating…" : "Generate report"}
        </Button>} />

      <Panel><SectionHeader title="Report filters" description="Narrow the archive by report type and generation date." /><div className="mt-4">
          <form onSubmit={applyFilters} className="flex flex-wrap items-end gap-3">
            <div className="flex flex-col gap-1">
              <Label htmlFor="type">Type</Label>
              <Select
                value={type || "all"}
                onValueChange={(value) => setType(value === "all" || value == null ? "" : value)}
              >
                <SelectTrigger id="type" className="h-9 w-32">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All</SelectItem>
                  <SelectItem value="daily">Daily</SelectItem>
                  <SelectItem value="weekly">Weekly</SelectItem>
                </SelectContent>
              </Select>
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
        </div></Panel>

      {error && <p role="alert" className="mt-4 text-sm text-negative">{error}</p>}

      <Panel><SectionHeader title="Generated reports" description="Most recent reports appear first." /><div className="mt-4">
          <DataTable
            columns={columns}
            rows={rows}
            rowKey={(r) => r.id}
            loading={loading}
            loadingMessage="Loading reports"
            emptyMessage="No reports yet — generate your first one."
          />
      </div></Panel>

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
