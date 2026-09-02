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
  await expect(waitingTab).toHaveURL(
    /\/login\?returnTo=%2Fportfolio&reason=signedOut$/,
  );
  await expect(directTab).toHaveURL(
    /\/login\?returnTo=%2Fwatchlist&reason=signedOut$/,
  );
});

test("an authenticated visit to login returns to the intended route", async ({ page }) => {
  await login(page);
  await page.goto("/login?returnTo=%2Freports");
  await expect(page).toHaveURL(/\/reports$/);
});

test("a refresh cookie restores a reloaded session after access expiry", async ({
  context,
  page,
}) => {
  await login(page);
  const refresh = (await context.cookies()).find(
    (cookie) => cookie.name === "finsight_refresh",
  );
  expect(refresh).toBeDefined();

  await context.clearCookies();
  await context.addCookies([refresh!]);
  await page.reload();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Overview", level: 1 })).toBeVisible();
  expect((await context.cookies()).some((cookie) => cookie.name === "finsight_access")).toBe(true);
});

test("an invalid session returns safely to sign in", async ({ context, page }) => {
  await context.clearCookies();
  await context.addCookies([
    {
      name: "finsight_access",
      value: "invalid-session-token",
      url: process.env.E2E_BASE_URL ?? "http://localhost:3000",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.goto("/settings");
  await expect(page).toHaveURL(/\/login\?returnTo=%2Fsettings$/);
  await expect(page.getByRole("heading", { name: "Welcome back" })).toBeVisible();
});

test("registration creates a session and OAuth denial remains recoverable", async ({ page }) => {
  const uniqueEmail = `phase13-${Date.now()}@example.com`;
  await page.goto("/register");
  await page.getByLabel("Email").fill(uniqueEmail);
  await page.getByLabel("Password", { exact: true }).fill("Phase13-E2E-Strong!");
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);

  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/login/);
  await page.goto("/login?oauthError=provider_denied");
  await expect(page.getByText("Google sign-in was cancelled. No changes were made.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
});
