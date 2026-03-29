import { expect, test } from "@playwright/test";
import {
  fetchStockDetail,
  fetchStocks,
  isFundLike,
  isReitLike,
  pickStock,
  saveShot,
} from "./helpers";

test("available stock detail renders live analysis data", async ({ page, request }) => {
  const stocks = await fetchStocks(request);
  const stock =
    pickStock(
      stocks,
      (item) =>
        !isFundLike(item) &&
        !isReitLike(item.industry) &&
        item.sector !== "Financial Services",
      ["AMZN", "GE", "NVDA", "GOOG"],
    ) ??
    pickStock(stocks, (item) => !isFundLike(item), ["AMZN", "O"]);

  test.skip(!stock, "No suitable stock available for live stock-detail coverage.");

  const detail = await fetchStockDetail(request, stock.ticker);
  const companyName = detail.stockInfo?.company_name ?? stock.company_name ?? stock.ticker;

  await page.goto(`/stock/${stock.ticker}`);

  await expect(page.getByRole("heading", { name: companyName })).toBeVisible();
  await expect(page.getByText("CONVICTION")).toBeVisible();
  await expect(page.getByText("MARGIN OF SAFETY")).toBeVisible();
  await expect(page.getByText("CURRENT PRICE")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Quality Overview" })).toBeVisible();
  await expect(page.getByText(stock.ticker, { exact: true })).toBeVisible();
  await saveShot(page, `09-stock-${stock.ticker.toLowerCase()}-live.png`);
});

test("reit stock detail renders live reit flow", async ({ page, request }) => {
  const stocks = await fetchStocks(request);
  const stock = pickStock(stocks, (item) => isReitLike(item.industry), ["O", "WELL"]);

  test.skip(!stock, "No REIT stock available for live stock-detail coverage.");

  const detail = await fetchStockDetail(request, stock.ticker);
  const companyName = detail.stockInfo?.company_name ?? stock.company_name ?? stock.ticker;

  await page.goto(`/stock/${stock.ticker}`);

  await expect(page.getByRole("heading", { name: companyName })).toBeVisible();
  await expect(page.getByText(stock.industry ?? /REIT/i)).toBeVisible();
  await expect(page.getByText("CONVICTION")).toBeVisible();
  await expect(page.getByText("CURRENT PRICE")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Quality Overview" })).toBeVisible();
  await saveShot(page, `10-stock-${stock.ticker.toLowerCase()}-reit-live.png`);
});

test("unknown stock detail shows empty state", async ({ page }) => {
  await page.goto("/stock/UNKNOWN");
  await expect(page.getByText("ยังไม่มีข้อมูลสำหรับ UNKNOWN")).toBeVisible();
  await saveShot(page, "11-stock-unknown-live.png");
});
