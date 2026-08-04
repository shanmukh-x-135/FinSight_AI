import type { ReactNode } from "react";

import { AIAnalysisState } from "@/components/AIAnalysisState";

/**
 * Reusable Analytics page template (design doc §7.4):
 *   Header → Summary Cards → Charts → AI Analysis → Supporting Tables.
 *
 * Screens compose these slots so the layout stays consistent across Market,
 * Portfolio, and Historical Similarity pages. The shared empty state keeps the
 * slot honest when a successful response contains no current signal.
 */
export interface AnalyticsPageTemplateProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  summaryCards?: ReactNode;
  charts?: ReactNode;
  aiAnalysis?: ReactNode;
  tables?: ReactNode;
}

function Section({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="mt-8 first:mt-6">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {heading}
      </h3>
      {children}
    </section>
  );
}

export function AnalyticsPageTemplate({
  title,
  subtitle,
  actions,
  summaryCards,
  charts,
  aiAnalysis,
  tables,
}: AnalyticsPageTemplateProps) {
  return (
    <div className="mx-auto max-w-5xl">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {actions}
      </div>

      {summaryCards && <Section heading="Summary">{summaryCards}</Section>}
      {charts && <Section heading="Charts">{charts}</Section>}

      <Section heading="AI Analysis">
        {aiAnalysis ?? (
          <AIAnalysisState
            status="empty"
            message="No AI analysis is available for this view."
          />
        )}
      </Section>

      {tables && <Section heading="Details">{tables}</Section>}
    </div>
  );
}
