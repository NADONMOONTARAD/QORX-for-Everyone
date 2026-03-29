import { expect, test } from "@playwright/test";
import {
  buildSearchTerm,
  buildSuggestionPattern,
  fetchStocks,
  pickStock,
  saveShot,
} from "./helpers";

test("dashboard supports filter and sort flow", async ({ page, request }) => {
  const stocks = await fetchStocks(request);
  test.skip(stocks.length === 0, "No stocks available for the dashboard.");

  const primaryStock = pickStock(stocks, () => true, ["AMZN", "O"]);
  test.skip(!primaryStock, "No stock available for the dashboard.");

  const otherSectorStock =
    primaryStock?.sector
      ? stocks.find(
          (stock) =>
            stock.ticker !== primaryStock.ticker &&
            stock.sector &&
            stock.sector !== primaryStock.sector,
        ) ?? null
      : null;

  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Top Rated Stocks" }),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: primaryStock.ticker, exact: true }),
  ).toBeVisible();
  await saveShot(page, "01-dashboard-home-live.png");

  await page.getByRole("button", { name: "Filter by sector or industry" }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await saveShot(page, "02-dashboard-filter-modal-live.png");

  if (primaryStock.sector) {
    await page
      .getByRole("button")
      .filter({ hasText: primaryStock.sector })
      .first()
      .click();
    await expect(
      page.getByRole("heading", { name: primaryStock.sector, exact: true }),
    ).toBeVisible();
    await saveShot(page, "03-dashboard-filter-sector-live.png");
  }

  if (primaryStock.industry) {
    await page
      .getByRole("button")
      .filter({ hasText: primaryStock.industry })
      .first()
      .click();
    await expect(
      page.getByRole("link", { name: primaryStock.ticker, exact: true }),
    ).toBeVisible();
    if (otherSectorStock) {
      await expect(
        page.getByRole("link", { name: otherSectorStock.ticker, exact: true }),
      ).toHaveCount(0);
    }
    await saveShot(page, "04-dashboard-filter-industry-live.png");
  }

  await page.getByRole("columnheader", { name: /Price/i }).click();
  await saveShot(page, "05-dashboard-sorted-price-live.png");
});

test("dashboard search navigates to stock detail", async ({ page, request }) => {
  const stocks = await fetchStocks(request);
  test.skip(stocks.length === 0, "No stocks available for search.");

  const stock = pickStock(stocks, () => true, ["AMZN", "O"]);
  test.skip(!stock, "No stock available for search.");

  await page.goto("/");

  const searchInput = page.locator('input[placeholder*="Ticker"], input[placeholder*="บริษัท"]').first();
  await searchInput.fill(buildSearchTerm(stock));

  const suggestion = page
    .getByRole("listitem")
    .filter({ hasText: buildSuggestionPattern(stock) })
    .first();
  await expect(suggestion).toBeVisible();
  await suggestion.click();

  await expect(page).toHaveURL(new RegExp(`/stock/${stock.ticker}$`, "i"));
  await expect(
    page.getByRole("heading", { name: stock.company_name ?? stock.ticker }),
  ).toBeVisible();
  await expect(page.getByText("CONVICTION")).toBeVisible();
  await saveShot(page, `06-dashboard-search-to-${stock.ticker.toLowerCase()}-live.png`);
});

test("dashboard handles empty data state", async ({ page }) => {
  await page.route("**/api/stocks", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.goto("/");

  await expect(
    page.getByText("ไม่พบข้อมูลหุ้นในหมวดหมู่ที่เลือก"),
  ).toBeVisible();
  await saveShot(page, "07-dashboard-empty-state-live.png");
});

test("dashboard handles API failure state without crashing", async ({ page }) => {
  await page.route("**/api/stocks", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify([]),
    });
  });

  await page.goto("/");

  await expect(
    page.getByText("ไม่พบข้อมูลหุ้นในหมวดหมู่ที่เลือก"),
  ).toBeVisible();
  await saveShot(page, "08-dashboard-error-state-live.png");
});
