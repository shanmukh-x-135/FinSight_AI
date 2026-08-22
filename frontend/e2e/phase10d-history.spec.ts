import { expect, test } from "@playwright/test";

import { ensureE2EUser, login } from "./support/auth";

test.skip(
  process.env.E2E_PHASE10D_LIVE !== "1",
  "requires the populated Phase 10D staging bootstrap",
);

test.beforeAll(async ({ request }) => {
  await ensureE2EUser(request);
});

test("populated market and regime research remain usable end to end", async ({ page }) => {
  await login(page);

  await page.goto("/market");
  await expect(page.getByRole("heading", { name: "Market Intelligence" })).toBeVisible();
  await expect(page.getByText("RELIANCE.NS", { exact: true }).first()).toBeVisible();

  await page.goto("/market/RELIANCE.NS");
  await expect(page.getByRole("heading", { name: /RELIANCE\.NS/ })).toBeVisible();
  await expect(page.getByRole("img", { name: "Daily stock price chart with moving averages" })).toBeVisible();

  await page.goto("/history");
  await expect(page.getByRole("heading", { name: "Historical Similarity" })).toBeVisible();
  await expect(page.getByText("market_regime_v1", { exact: true })).toBeVisible();
  await expect(page.getByText("25 regime features", { exact: true })).toBeVisible();
  await expect(page.getByText(/\d+% constituent coverage/)).toBeVisible();
  await expect(page.getByText(/features have \d+% group similarity/).first()).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Next 5 sessions" })).toBeVisible();
  await expect(page.getByText("Similarity index unavailable", { exact: true })).toHaveCount(0);
});
