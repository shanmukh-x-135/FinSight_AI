import type { PerformanceBreakdown, RobustnessAnalysis, ValidationMetricSlice } from "@/lib/api";

import { DataTable, type Column } from "@/components/DataTable";
import { Panel, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";

const pct = (value: number | null) => value == null ? "Unavailable" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
const componentLabels: Record<string, string> = { out_of_sample: "Out-of-sample", parameter_stability: "Parameter stability", regime_independence: "Regime independence", cost_resilience: "Cost resilience", drawdown_control: "Drawdown control" };
const maxima: Record<string, number> = { out_of_sample: 25, parameter_stability: 25, regime_independence: 20, cost_resilience: 15, drawdown_control: 15 };

function ValidationCard({ label, value }: { label: string; value: ValidationMetricSlice | null }) {
  return <div className="rounded-lg border border-border/60 bg-muted/20 p-3"><p className="text-[10px] font-semibold uppercase tracking-[.12em] text-muted-foreground">{label}</p>{value ? <div className="mt-2 grid grid-cols-2 gap-2 text-xs"><span>Return <strong className="block text-sm text-foreground">{pct(value.total_return_percent)}</strong></span><span>Excess <strong className="block text-sm text-foreground">{pct(value.excess_return_percent)}</strong></span><span>Drawdown <strong className="block text-sm text-foreground">{pct(-value.max_drawdown_percent)}</strong></span><span>Trades <strong className="block text-sm text-foreground">{value.total_trades}</strong></span></div> : <p className="mt-2 text-xs text-muted-foreground">Insufficient sessions</p>}</div>;
}

const breakdownColumns: Column<PerformanceBreakdown>[] = [
  { key: "label", header: "Bucket", render: (row) => <span className="capitalize">{row.label.replaceAll("_", " ")}</span> },
  { key: "trades", header: "Trades", align: "right", render: (row) => row.trades },
  { key: "return", header: "Avg return", align: "right", render: (row) => <TrendValue value={row.average_return_percent}>{pct(row.average_return_percent)}</TrendValue> },
  { key: "win", header: "Win rate", align: "right", render: (row) => `${row.win_rate_percent.toFixed(1)}%` },
];

export function RobustnessAnalysisView({ analysis }: { analysis: RobustnessAnalysis }) {
  const sensitivity = [...analysis.parameter_sensitivity.map((row) => ({ ...row, family: "Parameters" })), ...analysis.cost_sensitivity.map((row) => ({ ...row, family: "Execution costs" }))];
  return <section aria-label="Strategy robustness analysis" className="space-y-5">
    <Panel><SectionHeader title="Strategy robustness" description="A decomposable research-quality score—not a forecast or guarantee." action={<StatusBadge label={`${analysis.robustness.score.toFixed(0)} / 100`} tone={analysis.robustness.score >= 70 ? "positive" : analysis.robustness.score >= 45 ? "warning" : "negative"} />} />
      <div className="mt-4 grid gap-4 lg:grid-cols-[14rem_minmax(0,1fr)]"><div className="grid place-items-center rounded-xl border border-primary/20 bg-primary/5 p-5"><span className="text-4xl font-semibold tabular-nums text-primary">{analysis.robustness.score.toFixed(0)}</span><span className="text-xs text-muted-foreground">of 100</span><span className="mt-2 text-[10px] uppercase tracking-[.14em] text-muted-foreground">Robustness</span></div><div className="space-y-2">{Object.entries(analysis.robustness.components).map(([key, score]) => <div key={key}><div className="mb-1 flex justify-between text-xs"><span>{componentLabels[key] ?? key}</span><span className="tabular-nums text-muted-foreground">{score.toFixed(1)} / {maxima[key]}</span></div><div role="progressbar" aria-label={componentLabels[key] ?? key} aria-valuemin={0} aria-valuemax={maxima[key]} aria-valuenow={score} className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${Math.min(100, score / maxima[key] * 100)}%` }} /></div></div>)}</div></div>
      <ul className="mt-4 grid gap-1 text-xs leading-5 text-muted-foreground lg:grid-cols-2">{analysis.robustness.explanation.map((item) => <li key={item}>• {item}</li>)}</ul>
    </Panel>
    <div className="grid gap-5 lg:grid-cols-2"><Panel><SectionHeader title="Chronological validation" description={`${analysis.chronological_split.train_percent}/${analysis.chronological_split.test_percent} split at ${analysis.chronological_split.split_date ?? "unavailable"}. No parameter fitting occurs.`} /><div className="mt-3 grid gap-3 sm:grid-cols-2"><ValidationCard label="Training segment" value={analysis.chronological_split.training} /><ValidationCard label="Out-of-sample segment" value={analysis.chronological_split.test} /></div></Panel>
      <Panel><SectionHeader title="Sensitivity" description="Stable results should not collapse under modest threshold or modeled-cost changes." /><div className="mt-3 overflow-x-auto"><table className="w-full text-xs"><thead><tr className="border-b text-left text-muted-foreground"><th className="py-2">Test</th><th>Variant</th><th className="text-right">Return</th><th className="text-right">Excess</th></tr></thead><tbody>{sensitivity.map((row) => <tr key={`${row.family}-${row.label}`} className="border-b border-border/50 last:border-0"><td className="py-2">{row.family}</td><td>{row.label}</td><td className="text-right tabular-nums">{pct(row.total_return_percent)}</td><td className="text-right tabular-nums">{pct(row.excess_return_percent)}</td></tr>)}</tbody></table></div></Panel></div>
    <Panel><SectionHeader title="Performance by context" description="Trade outcomes are grouped by information known on each entry signal date. Unavailable context stays explicit." /><div className="mt-4 grid gap-4 xl:grid-cols-2">{([ ["Breadth regime", "breadth_regime"], ["Momentum regime", "momentum_regime"], ["Volatility regime", "volatility_regime"], ["Macro stress", "macro_stress"], ["Sector", "sector"], ["Signal confidence", "confidence_bucket"] ] as const).map(([label, key]) => <div key={key}><h3 className="mb-2 text-xs font-semibold">{label}</h3><DataTable columns={breakdownColumns} rows={analysis.breakdowns[key]} rowKey={(row) => row.label} emptyMessage="No completed signals in this context." caption={`${label} performance`} /></div>)}</div></Panel>
  </section>;
}
