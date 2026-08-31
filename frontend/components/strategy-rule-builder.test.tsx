import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { serializeRules, StrategyRuleBuilder, type EditableRule } from "./strategy-rule-builder";

const rule: EditableRule = { id: "r1", negated: true, kind: "condition", field: "rsi", operator: "between", value: 45, upper_value: 65 };

describe("StrategyRuleBuilder", () => {
  it("serializes NOT without executable expressions", () => {
    expect(serializeRules("AND", [rule])).toEqual({ kind: "group", operator: "AND", rules: [{ kind: "group", operator: "NOT", rules: [{ kind: "condition", field: "rsi", operator: "between", value: 45, upper_value: 65 }] }] });
  });

  it("exposes explicit field, operator, threshold, and negation controls", () => {
    const onChange = vi.fn();
    render(<StrategyRuleBuilder label="Entry" operator="AND" rules={[rule]} onOperatorChange={vi.fn()} onChange={onChange} />);

    expect(screen.getByRole("group", { name: "Entry" })).toBeVisible();
    expect(screen.getByRole("combobox", { name: "Rule field" })).toHaveValue("rsi");
    expect(screen.getByRole("spinbutton", { name: "Rule value" })).toHaveValue(45);
    expect(screen.getByRole("spinbutton", { name: "Upper rule value" })).toHaveValue(65);
    fireEvent.click(screen.getByRole("button", { name: "NOT" }));
    expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ negated: false })]);
  });
});
