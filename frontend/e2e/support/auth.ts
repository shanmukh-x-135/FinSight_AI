import { expect, type APIRequestContext, type Page } from "@playwright/test";

export const e2eUser = {
  apiURL: process.env.E2E_API_URL ?? "http://localhost:8000",
  email: process.env.E2E_EMAIL ?? "dashboard-e2e@example.com",
  password: process.env.E2E_PASSWORD ?? "Finsight-E2E-2026!",
};

export async function ensureE2EUser(request: APIRequestContext): Promise<void> {
  const response = await request.post(`${e2eUser.apiURL}/api/v1/auth/register`, {
    data: { email: e2eUser.email, password: e2eUser.password },
  });

  // Conflict makes setup idempotent when a developer reuses the same database.
  expect([201, 409]).toContain(response.status());
}

export async function login(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByLabel("Email").fill(e2eUser.email);
  await page.getByLabel("Password").fill(e2eUser.password);
  await page.getByRole("button", { name: "Log in" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
}
