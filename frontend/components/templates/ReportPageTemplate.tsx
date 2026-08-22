import type { ReactNode } from "react";

import { PageHeader, Panel, SectionHeader } from "@/components/workspace";

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
    <Panel><SectionHeader title={heading} /><div className="mt-4">{children}</div></Panel>
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
    <div className="mx-auto max-w-6xl space-y-5">
      <PageHeader eyebrow="Research report" title={title} description={subtitle} actions={actions} />

      {executiveSummary && <Section heading="Executive Summary">{executiveSummary}</Section>}
      {analysis && <Section heading="Analysis">{analysis}</Section>}
      {recommendations && <Section heading="Recommendations">{recommendations}</Section>}
      {appendix && <Section heading="Appendix">{appendix}</Section>}
    </div>
  );
}
