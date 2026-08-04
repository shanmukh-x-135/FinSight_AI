import { expect, test } from "@playwright/test";

import { e2eUser, ensureE2EUser, login } from "./support/auth";

test.beforeAll(async ({ request }) => {
  await ensureE2EUser(request);
});

test("login loads real dashboard data and reveals grounded evidence", async ({ page }) => {
  await login(page);

  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText(e2eUser.email)).toBeVisible();

  for (const label of [
    "Market Breadth",
    "Advance / Decline",
    "Portfolio Value",
    "Opportunities",
  ]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }

  await expect(page.getByText("Your Watchlist", { exact: true })).toBeVisible();
  await expect(page.getByText("AI Market Summary", { exact: true })).toBeVisible();

  const evidenceButton = page.getByRole("button", { name: "Show evidence" }).first();
  await expect(evidenceButton).toBeVisible();
  await evidenceButton.click();
  await expect(page.getByText(/^Breadth: \d+ advancers,/)).toBeVisible();
  await expect(page.getByRole("button", { name: "Hide evidence" }).first()).toBeVisible();
});
