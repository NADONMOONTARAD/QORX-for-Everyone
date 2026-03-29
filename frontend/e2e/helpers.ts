import fs from "fs/promises";
import path from "path";
import { expect, type APIRequestContext, type Page } from "@playwright/test";

const screenshotsDir = path.resolve(
  __dirname,
  "..",
  "..",
  "backend",
  "data",
  "test-reports",
  "e2e-screenshots",
);

export type StockListItem = {
  ticker: string;
  company_name?: string | null;
  sector?: string | null;
  industry?: string | null;
  logo_url?: string | null;
};

export type StockDetailResponse = {
  stockInfo: StockListItem | null;
  analysisResult: Record<string, unknown> | null;
  financialData: unknown[];
  segmentRevenue?: unknown;
  portfolioPosition?: unknown;
  documentSummary?: unknown;
  secFilings?: unknown[];
  systemStatus?: { status?: Record<string, unknown> | null } | null;
};

export async function saveShot(page: Page, fileName: string) {
  await fs.mkdir(screenshotsDir, { recursive: true });
  await page.screenshot({
    path: path.join(screenshotsDir, fileName),
    fullPage: true,
  });
}

export async function fetchStocks(request: APIRequestContext): Promise<StockListItem[]> {
  const response = await request.get("/api/stocks");
  expect(response.ok()).toBeTruthy();
  return (((await response.json()) as StockListItem[]) ?? []).map((stock) => ({
    ...stock,
    ticker: stock.ticker.toUpperCase(),
  }));
}

export async function fetchStockDetail(
  request: APIRequestContext,
  ticker: string,
): Promise<StockDetailResponse> {
  const response = await request.get(`/api/stocks/${ticker}`);
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as StockDetailResponse;
}

export function pickStock(
  stocks: StockListItem[],
  predicate: (stock: StockListItem) => boolean = () => true,
  preferredTickers: string[] = [],
): StockListItem | null {
  const preferred = preferredTickers.map((ticker) => ticker.toUpperCase());
  for (const ticker of preferred) {
    const match = stocks.find(
      (stock) => stock.ticker.toUpperCase() === ticker && predicate(stock),
    );
    if (match) {
      return match;
    }
  }

  return stocks.find(predicate) ?? null;
}

export function isFundLike(stock: Pick<StockListItem, "industry" | "company_name">): boolean {
  const industry = (stock.industry ?? "").toLowerCase();
  const companyName = (stock.company_name ?? "").toLowerCase();

  return (
    industry.includes("exchange traded fund") ||
    industry.includes("etf") ||
    companyName.includes(" etf") ||
    companyName.includes(" fund")
  );
}

export function isReitLike(industry?: string | null): boolean {
  return (industry ?? "").toLowerCase().includes("reit");
}

export function buildSearchTerm(stock: StockListItem): string {
  const candidate = (stock.company_name ?? "")
    .split(/[^A-Za-z]+/)
    .find((token) => token.length >= 4);

  return (candidate ?? stock.ticker).toLowerCase();
}

export function buildSuggestionPattern(stock: StockListItem): RegExp {
  const ticker = escapeRegExp(stock.ticker);
  const companyName = escapeRegExp(stock.company_name ?? "");

  if (!companyName) {
    return new RegExp(`^${ticker}$`, "i");
  }

  return new RegExp(`${ticker}\\s*\\|\\s*${companyName}`, "i");
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
