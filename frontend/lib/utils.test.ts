import { describe, expect, it } from "vitest";

import { pct, ratioPct } from "./utils";

describe("percentage formatters", () => {
  it("scales decimal ratios for historical percentages", () => {
    expect(ratioPct(0.01)).toBe("+1.00%");
    expect(ratioPct(-0.025)).toBe("-2.50%");
    expect(ratioPct(0.6, 1, false)).toBe("60.0%");
    expect(ratioPct(null)).toBe("—");
  });

  it("keeps already-scaled market and portfolio percentages unchanged", () => {
    expect(pct(5)).toBe("+5.00%");
    expect(pct(-3.5)).toBe("-3.50%");
  });
});
