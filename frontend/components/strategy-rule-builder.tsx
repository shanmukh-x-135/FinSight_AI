"use client";

import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { RuleCondition, RuleField, RuleGroup, RuleNode, RuleOperator } from "@/lib/api";

export interface EditableRule extends RuleCondition { id: string; negated: boolean }

const fields: { value: RuleField; label: string }[] = [
  { value: "price_vs_ema20", label: "Price vs EMA20" },
  { value: "price_vs_ema50", label: "Price vs EMA50" },
  { value: "rsi", label: "RSI" },
  { value: "macd_histogram", label: "MACD histogram" },
  { value: "volume_ratio", label: "Volume ratio" },
  { value: "sector_momentum_20d", label: "Sector momentum (20D)" },
  { value: "market_breadth", label: "Market breadth" },
  { value: "market_regime", label: "Historical regime" },
  { value: "news_sentiment", label: "News sentiment" },
];

const numericOperators: { value: RuleOperator; label: string }[] = [
  { value: "gt", label: ">" }, { value: "gte", label: "≥" },
  { value: "lt", label: "<" }, { value: "lte", label: "≤" },
  { value: "between", label: "between" },
];

export function defaultRule(id = crypto.randomUUID()): EditableRule {
  return { id, negated: false, kind: "condition", field: "price_vs_ema50", operator: "above", value: null };
}

function normalize(rule: EditableRule): RuleNode {
  const condition: RuleCondition = {
    kind: "condition", field: rule.field, operator: rule.operator,
    value: rule.value ?? null, upper_value: rule.operator === "between" ? rule.upper_value ?? null : null,
  };
  return rule.negated ? { kind: "group", operator: "NOT", rules: [condition] } : condition;
}

export function serializeRules(operator: "AND" | "OR", rules: EditableRule[]): RuleGroup {
  return { kind: "group", operator, rules: rules.map(normalize) };
}

function resetForField(rule: EditableRule, field: RuleField): EditableRule {
  if (field.startsWith("price_vs_ema")) return { ...rule, field, operator: "above", value: null, upper_value: null };
  if (field === "market_regime") return { ...rule, field, operator: "is", value: "broad_positive", upper_value: null };
  if (field === "macd_histogram") return { ...rule, field, operator: "positive", value: null, upper_value: null };
  return { ...rule, field, operator: "gt", value: field === "market_breadth" ? 0.55 : 0, upper_value: null };
}

export function StrategyRuleBuilder({ label, operator, rules, onOperatorChange, onChange }: {
  label: string;
  operator: "AND" | "OR";
  rules: EditableRule[];
  onOperatorChange: (value: "AND" | "OR") => void;
  onChange: (rules: EditableRule[]) => void;
}) {
  const update = (id: string, transform: (rule: EditableRule) => EditableRule) => onChange(rules.map((rule) => rule.id === id ? transform(rule) : rule));

  return (
    <fieldset className="space-y-3">
      <legend className="text-xs font-semibold uppercase tracking-[0.14em] text-muted-foreground">{label}</legend>
      <div className="flex flex-wrap items-center justify-end gap-2">
        <label className="flex items-center gap-2 text-xs text-muted-foreground">Match
          <select aria-label={`${label} logical operator`} value={operator} onChange={(event) => onOperatorChange(event.target.value as "AND" | "OR")} className="h-8 rounded-md border border-border bg-background px-2 text-foreground">
            <option value="AND">all rules (AND)</option><option value="OR">any rule (OR)</option>
          </select>
        </label>
      </div>
      <div className="space-y-2">
        {rules.map((rule, index) => {
          const price = rule.field.startsWith("price_vs_ema");
          const regime = rule.field === "market_regime";
          const macd = rule.field === "macd_histogram";
          const operators = price ? [{ value: "above", label: "above" }, { value: "below", label: "below" }] : regime ? [{ value: "is", label: "is" }, { value: "is_not", label: "is not" }] : macd ? [{ value: "positive", label: "positive" }, { value: "negative", label: "negative" }, ...numericOperators] : numericOperators;
          return <div key={rule.id} className="grid gap-2 rounded-lg border border-border/70 bg-muted/20 p-2 sm:grid-cols-[auto_minmax(10rem,1.5fr)_minmax(7rem,1fr)_minmax(7rem,1fr)_auto] sm:items-center">
            <span className="hidden size-6 place-items-center rounded bg-muted text-[10px] font-semibold text-muted-foreground sm:grid">{index + 1}</span>
            <div><Label htmlFor={`${label}-${rule.id}-field`} className="sr-only">Rule field</Label><select id={`${label}-${rule.id}-field`} value={rule.field} onChange={(event) => update(rule.id, (item) => resetForField(item, event.target.value as RuleField))} className="h-9 w-full rounded-md border border-border bg-background px-2 text-sm">{fields.map((field) => <option key={field.value} value={field.value}>{field.label}</option>)}</select></div>
            <select aria-label={`Operator for ${fields.find((field) => field.value === rule.field)?.label}`} value={rule.operator} onChange={(event) => update(rule.id, (item) => ({ ...item, operator: event.target.value as RuleOperator, value: event.target.value === "between" ? item.value ?? 0 : item.value, upper_value: event.target.value === "between" ? item.upper_value ?? 100 : null }))} className="h-9 rounded-md border border-border bg-background px-2 text-sm">{operators.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select>
            {regime ? <select aria-label="Regime value" value={String(rule.value)} onChange={(event) => update(rule.id, (item) => ({ ...item, value: event.target.value }))} className="h-9 rounded-md border border-border bg-background px-2 text-sm"><option value="broad_positive">Broad positive</option><option value="mixed">Mixed</option><option value="broad_negative">Broad negative</option></select> : !price && !(macd && ["positive", "negative"].includes(rule.operator)) ? <div className="flex gap-1"><Input aria-label="Rule value" type="number" step="any" value={typeof rule.value === "number" ? rule.value : 0} onChange={(event) => update(rule.id, (item) => ({ ...item, value: Number(event.target.value) }))} />{rule.operator === "between" && <Input aria-label="Upper rule value" type="number" step="any" value={rule.upper_value ?? 100} onChange={(event) => update(rule.id, (item) => ({ ...item, upper_value: Number(event.target.value) }))} />}</div> : <span className="hidden text-xs text-muted-foreground sm:block">No threshold</span>}
            <div className="flex items-center justify-end gap-1"><Button type="button" size="sm" variant={rule.negated ? "default" : "outline"} aria-pressed={rule.negated} onClick={() => update(rule.id, (item) => ({ ...item, negated: !item.negated }))}>NOT</Button><Button type="button" size="icon-sm" variant="ghost" aria-label={`Remove ${label} rule ${index + 1}`} disabled={rules.length === 1} onClick={() => onChange(rules.filter((item) => item.id !== rule.id))}><Trash2 className="size-3.5" /></Button></div>
          </div>;
        })}
      </div>
      <Button type="button" size="sm" variant="outline" onClick={() => onChange([...rules, defaultRule()])}><Plus className="size-3.5" />Add rule</Button>
    </fieldset>
  );
}
