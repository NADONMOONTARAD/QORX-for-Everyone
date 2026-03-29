import { NextResponse } from "next/server";

import {
  clearBackendMonitorLogs,
  getBackendMonitorSnapshot,
  startBackendMonitorJob,
  stopBackendMonitorJob,
} from "@/lib/admin-monitor";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  const snapshot = await getBackendMonitorSnapshot();
  return NextResponse.json(snapshot);
}

export async function POST(request: Request) {
  try {
    const body = (await request.json().catch(() => ({}))) as {
      tickers?: string | string[];
    };
    const snapshot = await startBackendMonitorJob(body.tickers);
    return NextResponse.json(snapshot);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to start analysis job.";
    return NextResponse.json({ error: message }, { status: 400 });
  }
}

export async function DELETE() {
  try {
    const snapshot = await stopBackendMonitorJob();
    return NextResponse.json(snapshot);
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Failed to stop analysis job.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

export async function PATCH() {
  const snapshot = await clearBackendMonitorLogs();
  return NextResponse.json(snapshot);
}
