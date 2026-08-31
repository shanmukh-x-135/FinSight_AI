import { expect, test } from "@playwright/test";

import { ensureE2EUser, login } from "./support/auth";

test.beforeAll(async ({ request }) => {
  await ensureE2EUser(request);
});

test("stream a grounded answer, reload persisted history, and clear it", async ({ page }) => {
  await login(page);
  await page.getByRole("link", { name: "AI", exact: true }).first().click();
  await expect(page).toHaveURL(/\/chat$/);
  await expect(page.getByRole("heading", { name: "AI Research Assistant" })).toBeVisible();

  const question = "What does today's market breadth show?";
  const streamedResponse = page.waitForResponse(
    (response) =>
      response.url().includes("/api/v1/chat?stream=true") &&
      response.request().method() === "POST",
  );
  await page.getByPlaceholder(/Ask about your portfolio/).fill(question);
  await page.getByRole("button", { name: "Send question" }).click();

  const response = await streamedResponse;
  expect(response.status()).toBe(200);
  expect(response.headers()["content-type"]).toContain("text/event-stream");
  await expect(page.getByLabel("Your message").last()).toContainText(question);
  const answer = page.getByLabel("FinSight AI response").last();
  await expect(answer).toBeVisible();
  await expect(answer.getByText(/confidence/)).toBeVisible();
  await expect(answer.getByRole("link", { name: /Market analytics/ })).toBeVisible();
  await answer.getByRole("button", { name: "Show evidence" }).click();
  await expect(
    answer.getByText(
      /^Market breadth has \d+ advancers, \d+ decliners, and \d+ unchanged\.$/,
    ),
  ).toBeVisible();
  await expect(
    answer.getByText("End-of-day data may not reflect intraday moves.", {
      exact: true,
    }),
  ).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("FinSight AI response").last()).toBeVisible();
  await expect(page.getByRole("button", { name: question }).last()).toBeVisible();

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete chat history" }).click();
  await expect(page.getByText("Ask about the evidence")).toBeVisible();
});
