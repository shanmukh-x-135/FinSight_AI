import { expect, test } from "@playwright/test";

import { e2eUser, ensureE2EUser, login } from "./support/auth";

test.beforeAll(async ({ request }) => {
  await ensureE2EUser(request);
});

test("login loads real dashboard data and reveals grounded evidence", async ({ page }) => {
  await login(page);

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByText(e2eUser.email)).toBeVisible();

  for (const label of [
    "Market breadth",
    "A/D ratio",
    "Portfolio value",
    "Active signals",
  ]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }

  await expect(page.getByText("Your Watchlist", { exact: true })).toBeVisible();
  await expect(page.getByText("Intelligence brief", { exact: true })).toBeVisible();

  const evidenceControl = page.getByText("Review evidence", { exact: true });
  await expect(evidenceControl).toBeVisible();
  await evidenceControl.click();
  await expect(page.getByText(/^Breadth: \d+ advancers,/)).toBeVisible();
});
