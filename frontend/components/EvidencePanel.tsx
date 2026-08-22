"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useState } from "react";

/**
 * EvidencePanel — the Research Mode "Show Evidence" expander (design doc §7.5).
 *
 * The single reusable disclosure behind every AI insight: it reveals the REAL
 * deterministic inputs the recommendation was built from — the indicators used,
 * the historical analogs, the risks, and how confidence was derived — never a
 * static mock. Reused verbatim across the Dashboard, Market, and Portfolio AI
 * cards so evidence looks and behaves identically everywhere.
 */
export interface EvidencePanelProps {
  evidence: string[];
  risks?: string[];
  confidence?: number;
  historicalContext?: {
    bullish_probability: number | null;
    sample_size: number | null;
  };
  /** Optional extra rows (e.g. portfolio impact) rendered under the evidence. */
  extra?: { label: string; value: string }[];
}

function Row({ children }: { children: React.ReactNode }) {
  return <li className="flex gap-2 text-sm"><span className="text-muted-foreground">•</span><span>{children}</span></li>;
}

export function EvidencePanel({
  evidence,
  risks,
  confidence,
  historicalContext,
  extra,
}: EvidencePanelProps) {
  const [open, setOpen] = useState(false);

  const hist =
    historicalContext &&
    historicalContext.bullish_probability != null &&
    historicalContext.sample_size
      ? `${Math.round(historicalContext.bullish_probability * 100)}% of ${historicalContext.sample_size} similar historical sessions closed higher`
      : null;

  return (
    <div className="mt-3">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex items-center gap-1 text-sm font-medium text-primary hover:underline"
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        {open ? "Hide evidence" : "Show evidence"}
      </button>

      {open && (
        <div className="mt-3 space-y-3 rounded-lg border bg-muted/30 p-4">
          {confidence != null && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Confidence
              </p>
              <div className="mt-1 flex items-center gap-2">
                <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary"
                    style={{ width: `${Math.max(0, Math.min(100, confidence))}%` }}
                  />
                </div>
                <span className="text-sm font-medium tabular-nums">{confidence}%</span>
              </div>
            </div>
          )}

          <div>
            <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Evidence
            </p>
            <ul className="mt-1 space-y-1">
              {evidence.length === 0 && (
                <li className="text-sm text-muted-foreground">No supporting indicators.</li>
              )}
              {evidence.map((e, i) => (
                <Row key={i}>{e}</Row>
              ))}
            </ul>
          </div>

          {hist && !evidence.includes(hist) && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Historical context</p>
              <p className="mt-1 text-sm">{hist}</p>
            </div>
          )}

          {risks && risks.length > 0 && (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Risks
              </p>
              <ul className="mt-1 space-y-1">
                {risks.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm text-warning">
                    <span>⚠</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {extra && extra.length > 0 && (
            <div className="grid grid-cols-2 gap-2 border-t pt-3 text-sm">
              {extra.map((x) => (
                <div key={x.label}>
                  <p className="text-xs text-muted-foreground">{x.label}</p>
                  <p className="font-medium">{x.value}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
