import { expect, test } from "@playwright/test";

const apiURL = process.env.E2E_API_URL ?? "http://localhost:8000";
const email = process.env.E2E_EMAIL ?? "dashboard-e2e@example.com";
const password = process.env.E2E_PASSWORD ?? "Finsight-E2E-2026!";

test.beforeAll(async ({ request }) => {
  const response = await request.post(`${apiURL}/api/v1/auth/register`, {
    data: { email, password },
  });

  // Conflict makes setup idempotent when a developer reuses the same database.
  expect([201, 409]).toContain(response.status());
});

test("login loads real dashboard data and reveals grounded evidence", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Log in" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();

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
