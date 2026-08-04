import { readFile } from "node:fs/promises";

import { expect, test } from "@playwright/test";

import { ensureE2EUser, login } from "./support/auth";

test.beforeAll(async ({ request }) => {
  await ensureE2EUser(request);
});

test("generate, open, inspect, and export a report", async ({ page }) => {
  test.setTimeout(60_000);
  await login(page);
  await page.getByRole("link", { name: "Reports", exact: true }).first().click();
  await expect(page).toHaveURL(/\/reports$/);

  const generatedResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/v1/reports/generate") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "Generate report" }).click();
  const response = await generatedResponse;
  expect(response.status()).toBe(201);
  const body = await response.json();
  const reportId = body.data.id as number;

  const openReport = page.locator(`a[href="/reports/${reportId}"]`);
  await expect(openReport).toBeVisible();
  await openReport.click();
  await expect(page).toHaveURL(new RegExp(`/reports/${reportId}$`));
  await expect(
    page.getByRole("heading", { name: "FinSight AI — Daily Report" }),
  ).toBeVisible();
  await expect(page.getByText(`Report #${reportId}`, { exact: false })).toBeVisible();

  const evidenceButton = page.getByRole("button", { name: "Show evidence" }).first();
  await evidenceButton.click();
  await expect(page.getByRole("button", { name: "Hide evidence" }).first()).toBeVisible();

  const markdownEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export Markdown" }).click();
  const markdownDownload = await markdownEvent;
  expect(markdownDownload.suggestedFilename()).toBe(`finsight-report-${reportId}.md`);
  const markdownPath = await markdownDownload.path();
  expect(markdownPath).not.toBeNull();
  const markdown = await readFile(markdownPath!, "utf8");
  expect(markdown).toContain("# FinSight AI — Daily Report");
  expect(markdown).toContain(`Report #${reportId}`);

  const pdfEvent = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export PDF" }).click();
  const pdfDownload = await pdfEvent;
  expect(pdfDownload.suggestedFilename()).toBe(`finsight-report-${reportId}.pdf`);
  const pdfPath = await pdfDownload.path();
  expect(pdfPath).not.toBeNull();
  const pdf = await readFile(pdfPath!);
  expect(pdf.subarray(0, 4).toString()).toBe("%PDF");
  expect(pdf.byteLength).toBeGreaterThan(1_000);
});
