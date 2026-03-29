import { NextResponse } from "next/server";
import { getPool } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
    try {
        const pool = getPool();

        const [stateRes, checkpointsRes, positionsRes] = await Promise.all([
            pool.query(
                `SELECT * FROM portfolio_state WHERE state_id = 1`,
            ),
            pool.query(
                `SELECT * FROM portfolio_checkpoints ORDER BY year, month`,
            ),
            pool.query(
                `SELECT * FROM portfolio_positions ORDER BY current_pct DESC`,
            ),
        ]);

        return NextResponse.json({
            state: stateRes.rows[0] ?? {},
            checkpoints: checkpointsRes.rows,
            positions: positionsRes.rows,
        });
    } catch (err) {
        console.error("[API /api/portfolio/dashboard]", err);
        return NextResponse.json(
            { state: {}, checkpoints: [], positions: [] },
            { status: 500 },
        );
    }
}
