import { expect, test } from "@playwright/test";
import { saveShot } from "./helpers";

test("admin entry point requires sign-in or shows the admin shell", async ({ page }) => {
  await page.goto("/admin");

  if (page.url().includes("/login")) {
    await expect(page.getByRole("heading", { name: "Sign in" })).toBeVisible();
    await expect(
      page.getByRole("button", { name: "Continue with Google" }),
    ).toBeVisible();
    await saveShot(page, "12-admin-login-gate-live.png");
    return;
  }

  await expect(page.getByText("Admin Portal")).toBeVisible();
  await saveShot(page, "12-admin-shell-live.png");
});
