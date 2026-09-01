import { expect, test } from "@playwright/test";

import { ensureE2EUser, login } from "./support/auth";

test.beforeEach(async ({ request }) => {
  await ensureE2EUser(request);
});

test("login, direct routes, reload, new tabs, and logout share one session", async ({
  context,
  page,
}) => {
  const waitingTab = await context.newPage();
  await waitingTab.goto("/portfolio");
  await expect(waitingTab).toHaveURL(/\/login\?returnTo=%2Fportfolio$/);

  await login(page);
  await expect(waitingTab).toHaveURL(/\/portfolio$/);
  await expect(waitingTab.getByRole("heading", { name: /Portfolio/i }).first()).toBeVisible();

  await waitingTab.reload();
  await expect(waitingTab).toHaveURL(/\/portfolio$/);

  const directTab = await context.newPage();
  await directTab.goto("/watchlist");
  await expect(directTab).toHaveURL(/\/watchlist$/);
  await expect(directTab.getByRole("heading", { name: "Watchlist" })).toBeVisible();

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await expect(waitingTab).toHaveURL(/\/login\?returnTo=%2Fportfolio$/);
  await expect(directTab).toHaveURL(/\/login\?returnTo=%2Fwatchlist$/);
});

test("an authenticated visit to login returns to the intended route", async ({ page }) => {
  await login(page);
  await page.goto("/login?returnTo=%2Freports");
  await expect(page).toHaveURL(/\/reports$/);
});
