import { NextResponse } from "next/server";
import { getDetailedStockInfo } from "@/lib/stocks-service";

export const dynamic = "force-dynamic";

export async function GET(
    _request: Request,
    { params }: { params: Promise<{ ticker: string }> },
) {
    const { ticker: rawTicker } = await params;
    const ticker = rawTicker?.toUpperCase();
    if (!ticker) {
        return NextResponse.json({ error: "Missing ticker" }, { status: 400 });
    }

    try {
        const data = await getDetailedStockInfo(ticker);
        return NextResponse.json(data);
    } catch (err) {
        console.error(`[API /api/stocks/${ticker}]`, err);
        return NextResponse.json(
            {
                stockInfo: null,
                analysisResult: null,
                financialData: [],
                segmentRevenue: null,
                portfolioPosition: null,
                documentSummary: null,
                secFilings: [],
                systemStatus: { status: null },
            },
            { status: 500 },
        );
    }
}
