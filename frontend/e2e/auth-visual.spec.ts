import { expect, test } from "@playwright/test";

const routes = [
  { path: "/login", heading: "Welcome back" },
  { path: "/register", heading: "Start with the evidence" },
  { path: "/forgot-password", heading: "Reset your password" },
  {
    path: "/reset-password?token=visual-only-secure-reset-token-123456789",
    heading: "Choose a new password",
  },
];

test("authentication screens are polished and overflow-free across breakpoints", async ({
  page,
}, testInfo) => {
  for (const viewport of [
    { width: 1440, height: 960, name: "desktop" },
    { width: 390, height: 844, name: "mobile" },
  ]) {
    await page.setViewportSize(viewport);
    for (const route of routes) {
      await page.goto(route.path);
      await expect(page.getByRole("heading", { name: route.heading })).toBeVisible();
      if (route.path === "/login") {
        await expect(page.getByRole("button", { name: "Continue with Google" })).toBeVisible();
        await expect(page.getByRole("link", { name: "Forgot password?" })).toBeVisible();
      }
      if (viewport.name === "desktop") {
        await expect(
          page.getByRole("heading", { name: "Research markets with evidence, not noise." }),
        ).toBeVisible();
      }
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
      );
      expect(overflow).toBeLessThanOrEqual(0);
      await page.screenshot({
        path: testInfo.outputPath(
          `${route.path.split("?")[0].slice(1)}-${viewport.name}.png`,
        ),
        fullPage: true,
      });
    }
  }
});
