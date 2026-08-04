import type { ReactNode } from "react";

/**
 * Report page template (design doc §7.4) — the reading order for a single
 * report: Header → Executive Summary → Analysis → Recommendations (each
 * recommendation carries its own evidence via Show Evidence). Slots are
 * rendered only when provided, so a report missing an optional section (no
 * portfolio, no history) still lays out cleanly.
 */
export interface ReportPageTemplateProps {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  executiveSummary?: ReactNode;
  analysis?: ReactNode;
  recommendations?: ReactNode;
  appendix?: ReactNode;
}

function Section({ heading, children }: { heading: string; children: ReactNode }) {
  return (
    <section className="mt-8">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted-foreground">
        {heading}
      </h3>
      {children}
    </section>
  );
}

export function ReportPageTemplate({
  title,
  subtitle,
  actions,
  executiveSummary,
  analysis,
  recommendations,
  appendix,
}: ReportPageTemplateProps) {
  return (
    <div className="mx-auto max-w-4xl">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">{title}</h2>
          {subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}
        </div>
        {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
      </div>

      {executiveSummary && <Section heading="Executive Summary">{executiveSummary}</Section>}
      {analysis && <Section heading="Analysis">{analysis}</Section>}
      {recommendations && <Section heading="Recommendations">{recommendations}</Section>}
      {appendix && <Section heading="Appendix">{appendix}</Section>}
    </div>
  );
}
