"use client";

import { Archive, FlaskConical, Save } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { BacktestChart } from "@/components/backtest-chart";
import { RobustnessAnalysisView } from "@/components/robustness-analysis";
import { DataTable, type Column } from "@/components/DataTable";
import { defaultRule, serializeRules, StrategyRuleBuilder, type EditableRule } from "@/components/strategy-rule-builder";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { DataState, PageHeader, Panel, SectionHeader, StatusBadge, TrendValue } from "@/components/workspace";
import { ApiError, strategiesApi, type Backtest, type BacktestSummary, type BacktestTrade, type ExecutionConfig, type Strategy, type StrategyDefinition } from "@/lib/api";

const executionDefaults: ExecutionConfig = { initial_capital: 100000, max_positions: 10, transaction_cost_bps: 10, slippage_bps: 5, stop_loss_percent: 3, take_profit_percent: 8, max_holding_sessions: 20, benchmark_symbol: "^NSEI" };
const initialEntry = (): EditableRule[] => [{ ...defaultRule("entry-1"), field: "price_vs_ema50", operator: "above" }, { ...defaultRule("entry-2"), field: "rsi", operator: "between", value: 45, upper_value: 65 }, { ...defaultRule("entry-3"), field: "macd_histogram", operator: "positive" }];
const initialExit = (): EditableRule[] => [{ ...defaultRule("exit-1"), field: "rsi", operator: "gt", value: 75 }, { ...defaultRule("exit-2"), field: "price_vs_ema20", operator: "below" }];
const percent = (value: number | null | undefined) => value == null ? "Unavailable" : `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
const ratio = (value: number | null | undefined) => value == null ? "Unavailable" : value.toFixed(2);

function parseNode(node: StrategyDefinition["entry"]["rules"][number], index: number): EditableRule | null {
  const negated = node.kind === "group" && node.operator === "NOT";
  const child = negated ? node.rules[0] : node;
  if (!child || child.kind !== "condition") return null;
  return { ...child, id: `loaded-${index}-${child.field}`, negated };
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [name, setName] = useState("EMA momentum");
  const [description, setDescription] = useState("Trend confirmation with disciplined risk exits.");
  const [entryOperator, setEntryOperator] = useState<"AND" | "OR">("AND");
  const [exitOperator, setExitOperator] = useState<"AND" | "OR">("OR");
  const [entryRules, setEntryRules] = useState<EditableRule[]>(initialEntry);
  const [exitRules, setExitRules] = useState<EditableRule[]>(initialExit);
  const [execution, setExecution] = useState(executionDefaults);
  const [startDate, setStartDate] = useState("2024-01-01");
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [universe, setUniverse] = useState("NIFTY100");
  const [membershipMode, setMembershipMode] = useState("current_universe");
  const [result, setResult] = useState<Backtest | null>(null);
  const [pastRuns, setPastRuns] = useState<BacktestSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try { const rows = await strategiesApi.list(); setStrategies(rows); setError(null); }
    catch { setError("Could not load your strategies."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => {
    let cancelled = false;
    async function loadInitial() {
      await Promise.resolve();
      try {
        const rows = await strategiesApi.list();
        if (!cancelled) { setStrategies(rows); setError(null); }
      } catch {
        if (!cancelled) setError("Could not load your strategies.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void loadInitial();
    return () => { cancelled = true; };
  }, []);

  const definition = useMemo<StrategyDefinition>(() => ({ entry: serializeRules(entryOperator, entryRules), exit: serializeRules(exitOperator, exitRules), execution }), [entryOperator, entryRules, exitOperator, exitRules, execution]);

  function selectStrategy(strategy: Strategy) {
    const value = strategy.latest_version.definition;
    setSelectedId(strategy.id); setName(strategy.name); setDescription(strategy.description ?? "");
    setEntryOperator(value.entry.operator === "OR" ? "OR" : "AND"); setExitOperator(value.exit.operator === "AND" ? "AND" : "OR");
    setEntryRules(value.entry.rules.map(parseNode).filter((rule): rule is EditableRule => rule != null));
    setExitRules(value.exit.rules.map(parseNode).filter((rule): rule is EditableRule => rule != null));
    setExecution(value.execution); setResult(null); setPastRuns([]); setError(null);
    void strategiesApi.runs(strategy.id).then(setPastRuns).catch(() => setError("The strategy loaded, but its replay history is unavailable."));
  }
  function newStrategy() { setSelectedId(null); setName("EMA momentum"); setDescription("Trend confirmation with disciplined risk exits."); setEntryOperator("AND"); setExitOperator("OR"); setEntryRules(initialEntry()); setExitRules(initialExit()); setExecution(executionDefaults); setResult(null); setPastRuns([]); }
  async function save() {
    setBusy(true); setError(null);
    try {
      const saved = selectedId ? await strategiesApi.update(selectedId, { name, description, definition }) : await strategiesApi.create({ name, description, definition });
      setSelectedId(saved.id); await load();
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Could not save the strategy."); }
    finally { setBusy(false); }
  }
  async function archive() {
    if (!selectedId) return;
    setBusy(true);
    try { await strategiesApi.archive(selectedId); newStrategy(); await load(); }
    catch { setError("Could not archive the strategy."); }
    finally { setBusy(false); }
  }
  async function run() {
    setBusy(true); setError(null);
    try {
      let id = selectedId;
      if (!id) { const saved = await strategiesApi.create({ name, description, definition }); id = saved.id; setSelectedId(id); await load(); }
      const completed = await strategiesApi.run(id, { start_date: startDate, end_date: endDate, universe_code: universe, membership_mode: membershipMode });
      setResult(completed);
      setPastRuns(await strategiesApi.runs(id));
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Backtest could not be completed."); }
    finally { setBusy(false); }
  }
  async function analyze() {
    if (!result) return;
    setBusy(true); setError(null);
    try {
      const robustness_analysis = await strategiesApi.analyze(result.id);
      setResult({ ...result, robustness_analysis });
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "Robustness analysis could not be completed."); }
    finally { setBusy(false); }
  }

  const tradeColumns: Column<BacktestTrade>[] = [
    { key: "symbol", header: "Symbol", render: (trade) => <span className="font-medium">{trade.symbol}</span> },
    { key: "entry", header: "Signal → entry", render: (trade) => <span className="whitespace-nowrap">{trade.entry_signal_date} → {trade.entry_date}</span> },
    { key: "exit", header: "Exit", render: (trade) => <span className="whitespace-nowrap">{trade.exit_date} · {trade.exit_reason.replaceAll("_", " ")}</span> },
    { key: "hold", header: "Hold", align: "right", render: (trade) => `${trade.holding_sessions} sessions` },
    { key: "return", header: "Net return", align: "right", render: (trade) => <TrendValue value={trade.return_percent}>{percent(trade.return_percent)}</TrendValue> },
    { key: "cost", header: "Costs", align: "right", render: (trade) => `₹${trade.transaction_cost.toFixed(2)}` },
  ];

  return <div className="space-y-5">
    <PageHeader eyebrow="Deterministic research" title="Strategy Lab" description="Build explicit rules, replay close signals with next-session execution, and compare against a benchmark. Backtests are research evidence—not forecasts." actions={<><Button variant="outline" onClick={newStrategy}>New strategy</Button><Button onClick={save} disabled={busy || !name.trim()}><Save className="size-4" />{selectedId ? "Save new version" : "Save strategy"}</Button></>} />
    {error && <p role="alert" className="rounded-lg border border-negative/25 bg-negative/10 px-3 py-2 text-sm text-negative">{error}</p>}
    <div className="grid gap-5 xl:grid-cols-[16rem_minmax(0,1fr)]">
      <Panel className="h-fit"><SectionHeader title="Saved strategies" description="Each edit creates an immutable version." />
        <div className="mt-3 space-y-1">{loading ? <p role="status" className="text-xs text-muted-foreground">Loading strategies…</p> : strategies.length === 0 ? <p className="text-xs text-muted-foreground">No saved strategies yet.</p> : strategies.map((strategy) => <button type="button" key={strategy.id} onClick={() => selectStrategy(strategy)} aria-pressed={selectedId === strategy.id} className="flex w-full items-center justify-between rounded-lg px-2.5 py-2 text-left text-sm hover:bg-muted/60 aria-pressed:bg-primary/10 aria-pressed:text-primary"><span className="truncate">{strategy.name}</span><StatusBadge label={`v${strategy.latest_version.version}`} /></button>)}</div>
        {selectedId && <><div className="mt-5 border-t border-border/60 pt-4"><p className="text-[10px] font-semibold uppercase tracking-[.14em] text-muted-foreground">Replay history</p><div className="mt-2 space-y-1">{pastRuns.length === 0 ? <p className="text-xs text-muted-foreground">No completed replays.</p> : pastRuns.slice(0, 8).map((run) => <button key={run.id} type="button" onClick={() => { setBusy(true); void strategiesApi.backtest(run.id).then(setResult).catch(() => setError("Could not load the replay result.")).finally(() => setBusy(false)); }} className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-xs hover:bg-muted"><span>{run.start_date.slice(0, 4)}–{run.end_date.slice(0, 4)} · v{run.strategy_version}</span><span className="tabular-nums text-muted-foreground">{percent(run.metrics?.total_return_percent)}</span></button>)}</div></div><Button variant="ghost" size="sm" className="mt-3 w-full text-negative" onClick={archive} disabled={busy}><Archive className="size-3.5" />Archive</Button></>}
      </Panel>
      <div className="min-w-0 space-y-5">
        <Panel><SectionHeader title="Strategy definition" description="All rules are validated structured data; no executable expressions are accepted." />
          <div className="mt-4 grid gap-3 sm:grid-cols-2"><div><Label htmlFor="strategy-name">Name</Label><Input id="strategy-name" value={name} onChange={(event) => setName(event.target.value)} maxLength={120} /></div><div><Label htmlFor="strategy-description">Description</Label><Input id="strategy-description" value={description} onChange={(event) => setDescription(event.target.value)} maxLength={1000} /></div></div>
          <div className="mt-5 space-y-6"><StrategyRuleBuilder label="Entry" operator={entryOperator} rules={entryRules} onOperatorChange={setEntryOperator} onChange={setEntryRules} /><StrategyRuleBuilder label="Exit" operator={exitOperator} rules={exitRules} onOperatorChange={setExitOperator} onChange={setExitRules} /></div>
        </Panel>
        <Panel><SectionHeader title="Execution & risk" description="Signals use session-close data. The earliest fill is the next eligible session, with adverse slippage and transaction costs." />
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{([ ["Initial capital", "initial_capital", 1], ["Max positions", "max_positions", 1], ["Costs (bps)", "transaction_cost_bps", .1], ["Slippage (bps)", "slippage_bps", .1], ["Stop loss (%)", "stop_loss_percent", .1], ["Take profit (%)", "take_profit_percent", .1], ["Max hold (sessions)", "max_holding_sessions", 1] ] as const).map(([label, key, step]) => <div key={key}><Label htmlFor={key}>{label}</Label><Input id={key} type="number" min="0" step={step} value={execution[key] ?? ""} onChange={(event) => setExecution({ ...execution, [key]: event.target.value === "" ? null : Number(event.target.value) })} /></div>)}<div><Label htmlFor="benchmark">Benchmark</Label><Input id="benchmark" value={execution.benchmark_symbol} onChange={(event) => setExecution({ ...execution, benchmark_symbol: event.target.value })} /></div></div>
        </Panel>
        <Panel><SectionHeader title="Replay settings" description="Current membership is convenient but may contain survivorship bias. Historical mode requires recorded membership coverage." />
          <div className="mt-4 flex flex-wrap items-end gap-3"><div><Label htmlFor="start-date">Start date</Label><Input id="start-date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></div><div><Label htmlFor="end-date">End date</Label><Input id="end-date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></div><div><Label htmlFor="universe">Universe</Label><select id="universe" value={universe} onChange={(event) => setUniverse(event.target.value)} className="block h-9 rounded-md border border-border bg-background px-3 text-sm"><option value="NIFTY50">NIFTY 50</option><option value="NIFTYNEXT50">NIFTY Next 50</option><option value="NIFTY100">NIFTY 100</option></select></div><div><Label htmlFor="membership">Membership</Label><select id="membership" value={membershipMode} onChange={(event) => setMembershipMode(event.target.value)} className="block h-9 rounded-md border border-border bg-background px-3 text-sm"><option value="current_universe">Current universe</option><option value="historical_membership">Historical membership</option></select></div><Button onClick={run} disabled={busy || !name.trim() || startDate >= endDate}><FlaskConical className="size-4" />{busy ? "Running…" : "Run backtest"}</Button></div>
        </Panel>
      </div>
    </div>
    {result && result.metrics && <section aria-label="Backtest results" className="space-y-5">
      <Panel><SectionHeader title={`Backtest result · strategy v${result.strategy_version}`} description={`${result.start_date} to ${result.end_date} · ${result.universe_code} · hash ${result.result_hash?.slice(0, 12) ?? "unavailable"}`} action={<><StatusBadge label={result.status} tone="positive" /><Button size="sm" variant="outline" onClick={analyze} disabled={busy}>{busy ? "Analyzing…" : result.robustness_analysis ? "Re-run robustness" : "Analyze robustness"}</Button></>} /><p className="mt-3 rounded-lg bg-warning/10 px-3 py-2 text-xs leading-5 text-warning">{result.membership_disclaimer}</p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8">{[
          ["Total return", percent(result.metrics.total_return_percent)], ["Benchmark", percent(result.metrics.benchmark_return_percent)], ["Excess", percent(result.metrics.excess_return_percent)], ["CAGR", percent(result.metrics.cagr_percent)], ["Sharpe", ratio(result.metrics.sharpe_ratio)], ["Sortino", ratio(result.metrics.sortino_ratio)], ["Max drawdown", percent(result.metrics.max_drawdown_percent)], ["Win rate", percent(result.metrics.win_rate_percent)], ["Profit factor", ratio(result.metrics.profit_factor)], ["Expectancy", percent(result.metrics.expectancy_percent)], ["Trades", String(result.metrics.total_trades)], ["Avg hold", ratio(result.metrics.average_holding_sessions)], ["Turnover", percent(result.metrics.turnover_percent)], ["Costs", `₹${result.metrics.estimated_transaction_costs.toFixed(2)}`], ["Avg winner", percent(result.metrics.average_winner_percent)], ["Avg loser", percent(result.metrics.average_loser_percent)],
        ].map(([label, value]) => <div key={label} className="rounded-lg border border-border/60 bg-muted/20 p-2.5"><p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p><p className="mt-1 text-sm font-semibold tabular-nums">{value}</p></div>)}</div>
      </Panel>
      <Panel><SectionHeader title="Equity, benchmark & drawdown" description="Markers show executed trades; close signals always precede execution." /><div className="mt-3"><BacktestChart result={result} /></div></Panel>
      <Panel><SectionHeader title="Executed trades" description="Signal and execution dates are shown separately for auditability." /><div className="mt-3"><DataTable columns={tradeColumns} rows={result.trades} rowKey={(trade, index) => `${trade.symbol}-${trade.entry_date}-${index}`} emptyMessage="No trades met the complete rule set." caption="Backtest trades" /></div></Panel>
      {result.robustness_analysis && <RobustnessAnalysisView analysis={result.robustness_analysis} />}
    </section>}
    {!result && <DataState kind="empty" title="No replay selected" description="Save or configure a strategy, then run a backtest to inspect benchmark-relative performance and fills." />}
  </div>;
}
