import { NextResponse } from "next/server";
import { getPool } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
    try {
        const pool = getPool();
        const { rows } = await pool.query(
            `SELECT s.ticker, s.company_name, s.logo_url, s.sector, s.industry,
                    a.conviction_score, a.margin_of_safety, a.current_price,
                    a.portfolio_directive
             FROM stocks s
             JOIN stock_analysis_results a on s.ticker = a.ticker
             WHERE a.intrinsic_value_estimate IS NOT NULL
             ORDER BY a.conviction_score DESC NULLS LAST, s.ticker ASC`,
        );
        return NextResponse.json(rows);
    } catch (err) {
        console.error("[API /api/stocks]", err);
        return NextResponse.json([], { status: 500 });
    }
}
