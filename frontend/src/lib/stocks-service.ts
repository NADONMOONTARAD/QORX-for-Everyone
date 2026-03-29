import { getPool } from "./db";

export type StockInfo = {
  ticker: string;
  company_name?: string;
  sector?: string;
  industry?: string;
  industry_group?: string;
  logo_url?: string | null;
  market_cap?: number | null;
};

export type AnalysisResult = {
  conviction_score?: number | null;
  margin_of_safety?: number | null;
  current_price?: number | null;
  intrinsic_value_estimate?: number | null;
  intrinsic_value_reason?: string | null;
  ai_recommendation_summary?: string | null;
  moat_rating?: string | null;
  key_risks?: string | null;
  ai_reasoning?: string | null;
  portfolio_directive?: any;
  checklist_details?: any;
};

export type FinancialRow = {
  report_date: string;
  total_revenue?: number | null;
  revenue_growth?: number | null;
  eps_growth_diluted?: number | null;
  net_income?: number | null;
  net_profit_margin?: number | null;
  eps_diluted?: number | null;
  gross_margin?: number | null;
  free_cash_flow?: number | null;
  fcf_margin?: number | null;
  roe?: number | null;
  roic?: number | null;
  debt_to_equity?: number | null;
  payout_ratio?: number | null;
  interest_coverage?: number | null;
};

export type SecFilingEntry = {
  report_date?: string | null;
  filing_date?: string | null;
  form_type?: string | null;
  sec_url?: string | null;
};

export type StockDetailResponse = {
  stockInfo: StockInfo | null;
  analysisResult: AnalysisResult | null;
  financialData: FinancialRow[];
  segmentRevenue: any | null;
  portfolioPosition: any | null;
  documentSummary: any | null;
  secFilings: SecFilingEntry[];
  systemStatus: { status: any | null };
};

export async function getDetailedStockInfo(ticker: string): Promise<StockDetailResponse> {
  const pool = getPool();
  try {
    const [
      stockRes,
      analysisRes,
      financialRes,
      portfolioRes,
      docSummaryRes,
      secFilingsRes,
      statusRes,
    ] = await Promise.all([
      // 1. Stock info
      pool.query(`SELECT * FROM stocks WHERE ticker = $1`, [ticker]),

      // 2. Latest analysis result
      pool.query(
        `SELECT * FROM stock_analysis_results
         WHERE ticker = $1
         ORDER BY analysis_date DESC
         LIMIT 1`,
        [ticker],
      ),

      // 3. Financial data
      pool.query(
        `SELECT * FROM financial_data
         WHERE ticker = $1
         ORDER BY report_date DESC`,
        [ticker],
      ),

      // 4. Portfolio position
      pool.query(
        `SELECT * FROM portfolio_positions WHERE ticker = $1`,
        [ticker],
      ),

      // 7. Document summary (latest 10-K)
      pool.query(
        `SELECT ds.gemini_summary_json
         FROM document_summaries ds
         JOIN sec_filings_metadata sf ON ds.filing_id = sf.filing_id
         WHERE sf.ticker = $1
         ORDER BY sf.filing_date DESC
         LIMIT 1`,
        [ticker],
      ),

      // 8. SEC filings (10-K only)
      pool.query(
        `SELECT report_date, filing_date, form_type, sec_url
         FROM sec_filings_metadata
         WHERE ticker = $1 AND form_type = '10-K' AND sec_url IS NOT NULL
         ORDER BY report_date DESC`,
        [ticker],
      ),

      // 9. System status
      pool.query(
        `SELECT key, value FROM system_status WHERE key = $1`,
        [`status:${ticker}`],
      ),
    ]);

    const stockInfo = stockRes.rows[0] ?? null;
    const analysisResult = analysisRes.rows[0] ?? null;
    const statusMap: Record<string, any> = {};
    for (const row of statusRes.rows) {
      statusMap[row.key] = row.value;
    }

    return {
      stockInfo: stockInfo
        ? {
            ...stockInfo,
            logo_url: stockInfo.logo_url ?? null,
            market_cap: stockInfo.market_cap ? Number(stockInfo.market_cap) : null,
          }
        : null,
      analysisResult: analysisResult
        ? {
            ...analysisResult,
            conviction_score: analysisResult.conviction_score ? Number(analysisResult.conviction_score) : null,
            margin_of_safety: analysisResult.margin_of_safety ? Number(analysisResult.margin_of_safety) : null,
            intrinsic_value_estimate: analysisResult.intrinsic_value_estimate ? Number(analysisResult.intrinsic_value_estimate) : null,
            current_price: analysisResult.current_price ? Number(analysisResult.current_price) : null,
          }
        : null,
      financialData: financialRes.rows,
      segmentRevenue: null,
      portfolioPosition: portfolioRes.rows[0] ?? null,
      documentSummary: docSummaryRes.rows[0]?.gemini_summary_json ?? null,
      secFilings: secFilingsRes.rows,
      systemStatus: {
        status: statusMap[`status:${ticker}`] ?? null,
      },
    };
  } catch (err) {
    console.error(`[Service getDetailedStockInfo] ${ticker}:`, err);
    throw err;
  }
}
