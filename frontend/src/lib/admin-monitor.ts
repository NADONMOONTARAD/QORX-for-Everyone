import {
  spawn,
  type ChildProcess,
} from "node:child_process";
import { existsSync } from "node:fs";
import path from "node:path";
import type { Readable } from "node:stream";

import { getPool } from "@/lib/db";
import type {
  BackendMonitorSnapshot,
  MonitorJobState,
  MonitorLogEntry,
  MonitorLogLevel,
  TickerRunStatus,
  TickerStatusItem,
} from "@/lib/admin-monitor-types";

const LOG_LIMIT = 500;
const SNAPSHOT_LOG_LIMIT = 200;

type InternalState = {
  child: ChildProcess | null;
  jobState: MonitorJobState;
  isRunning: boolean;
  stopRequested: boolean;
  sourceMode: "manual" | "env";
  defaultTickers: string[];
  requestedTickers: string[];
  currentTicker: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  lastUpdatedAt: string | null;
  pid: number | null;
  lastExitCode: number | null;
  lastExitSignal: string | null;
  summary: string;
  logs: MonitorLogEntry[];
  tickerStatuses: Record<string, TickerStatusItem>;
  sequence: number;
};

declare global {
  var __stockAnalysisAdminMonitor: InternalState | undefined;
}

function nowIso(): string {
  return new Date().toISOString();
}

function resolveRepoRoot(): string {
  const candidates = [process.cwd(), path.resolve(process.cwd(), "..")];

  for (const candidate of candidates) {
    if (existsSync(path.join(candidate, "backend", "unified_runner.py"))) {
      return candidate;
    }
  }

  return path.resolve(process.cwd(), "..");
}

const REPO_ROOT = resolveRepoRoot();

function isTruthyEnv(value: string | undefined): boolean {
  return /^(1|true|yes|on)$/i.test((value ?? "").trim());
}

function getRunnerDatabaseTargetLabel(): string {
  return isTruthyEnv(process.env.USE_DEPLOY_DB)
    ? "deploy database (DATABASE_URL_DEPLOY / Supabase)"
    : "local database (DATABASE_URL)";
}

function normalizeTickers(input: string | string[] | null | undefined): string[] {
  const rawItems = Array.isArray(input) ? input : [input ?? ""];
  const flattened = rawItems.flatMap((value) =>
    String(value)
      .split(/[,\n\r\t ]+/)
      .map((part) => part.trim()),
  );

  const unique = new Set<string>();
  for (const item of flattened) {
    if (!item) {
      continue;
    }
    unique.add(item.toUpperCase());
  }

  return Array.from(unique);
}

function createTickerStatuses(tickers: string[]): Record<string, TickerStatusItem> {
  return Object.fromEntries(
    tickers.map((ticker) => [
      ticker,
      {
        ticker,
        status: "pending" satisfies TickerRunStatus,
        message: "Waiting in queue",
        updatedAt: null,
        startedAt: null,
        finishedAt: null,
        source: "memory" satisfies TickerStatusItem["source"],
      },
    ]),
  );
}

function createInitialState(): InternalState {
  return {
    child: null,
    jobState: "idle",
    isRunning: false,
    stopRequested: false,
    sourceMode: "manual",
    defaultTickers: [],
    requestedTickers: [],
    currentTicker: null,
    startedAt: null,
    finishedAt: null,
    lastUpdatedAt: null,
    pid: null,
    lastExitCode: null,
    lastExitSignal: null,
    summary: "Ready",
    logs: [],
    tickerStatuses: {},
    sequence: 0,
  };
}

function getState(): InternalState {
  if (!globalThis.__stockAnalysisAdminMonitor) {
    globalThis.__stockAnalysisAdminMonitor = createInitialState();
  }

  const state = globalThis.__stockAnalysisAdminMonitor;
  if (!state.isRunning && state.requestedTickers.length === 0) {
    state.summary = "Ready";
  }

  return state;
}

function isTerminalStatus(status: TickerRunStatus): boolean {
  return (
    status === "success" ||
    status === "error" ||
    status === "skipped" ||
    status === "stopped"
  );
}

function computeProgress(state: InternalState) {
  const total = state.requestedTickers.length;
  const completed = state.requestedTickers.filter((ticker) =>
    isTerminalStatus(state.tickerStatuses[ticker]?.status ?? "pending"),
  ).length;

  return {
    completed,
    total,
    percentage: total > 0 ? Math.round((completed / total) * 100) : 0,
  };
}

function buildSummary(state: InternalState): string {
  const progress = computeProgress(state);
  const counts = {
    success: 0,
    skipped: 0,
    error: 0,
    running: 0,
    pending: 0,
    stopped: 0,
  };

  for (const ticker of state.requestedTickers) {
    const status = state.tickerStatuses[ticker]?.status ?? "pending";
    counts[status] += 1;
  }

  if (state.jobState === "running") {
    return state.currentTicker
      ? `Running ${progress.completed}/${progress.total} · ${state.currentTicker}`
      : `Running ${progress.completed}/${progress.total}`;
  }

  if (state.jobState === "stopping") {
    return "Stopping";
  }

  if (state.jobState === "stopped") {
    return "Stopped";
  }

  if (state.jobState === "completed") {
    return `Completed · ${counts.success} ok`;
  }

  if (state.jobState === "failed") {
    return `Failed · ${counts.error} error`;
  }

  return "Ready";
}

function stripAnsi(line: string): string {
  return line.replace(/\x1B\[[0-9;]*m/g, "");
}

function appendLog(
  state: InternalState,
  source: MonitorLogEntry["source"],
  level: MonitorLogLevel,
  message: string,
  ticker: string | null = null,
) {
  const cleaned = stripAnsi(message).trim();
  if (!cleaned) {
    return;
  }

  state.sequence += 1;
  state.lastUpdatedAt = nowIso();
  state.logs.push({
    id: `${Date.now()}-${state.sequence}`,
    timestamp: state.lastUpdatedAt,
    source,
    level,
    message: cleaned,
    ticker,
  });

  if (state.logs.length > LOG_LIMIT) {
    state.logs = state.logs.slice(-LOG_LIMIT);
  }
}

function updateTickerStatus(
  state: InternalState,
  ticker: string,
  update: Partial<TickerStatusItem>,
) {
  const existing = state.tickerStatuses[ticker] ?? {
    ticker,
    status: "pending" as const,
    message: "Waiting in queue",
    updatedAt: null,
    startedAt: null,
    finishedAt: null,
    source: "memory" as const,
  };

  state.tickerStatuses[ticker] = {
    ...existing,
    ...update,
    ticker,
  };
  state.lastUpdatedAt = nowIso();
}

function inferLogLevel(
  message: string,
  source: MonitorLogEntry["source"],
): MonitorLogLevel {
  if (source === "stderr") {
    return "error";
  }

  if (/completed successfully|completed\.|success/i.test(message)) {
    return "success";
  }

  if (/failed|exception|traceback|error/i.test(message)) {
    return "error";
  }

  if (/warning|skipping|stopped/i.test(message)) {
    return "warning";
  }

  return "info";
}

function processLogLine(
  state: InternalState,
  source: MonitorLogEntry["source"],
  rawLine: string,
) {
  const message = stripAnsi(rawLine).trim();
  if (!message) {
    return;
  }

  const timestamp = nowIso();
  let matchedTicker: string | null = null;

  const processingMatch = message.match(/PROCESSING TICKER:\s*([A-Z0-9.-]+)/i);
  if (processingMatch) {
    matchedTicker = processingMatch[1].toUpperCase();
    state.currentTicker = matchedTicker;
    updateTickerStatus(state, matchedTicker, {
      status: "running",
      message: "Runner started processing this ticker",
      startedAt: state.tickerStatuses[matchedTicker]?.startedAt ?? timestamp,
      updatedAt: timestamp,
      finishedAt: null,
      source: "memory",
    });
  }

  const completedMatch = message.match(
    /Full analysis job for\s+([A-Z0-9.-]+)\s+completed successfully/i,
  );
  if (completedMatch) {
    matchedTicker = completedMatch[1].toUpperCase();
    updateTickerStatus(state, matchedTicker, {
      status: "success",
      message: "Analysis completed successfully",
      updatedAt: timestamp,
      finishedAt: timestamp,
      source: "memory",
    });
  }

  const failedMatch = message.match(
    /FAILED UNIFIED ANALYSIS FOR\s+([A-Z0-9.-]+)(?:\s+with.*|\s+due.*)?/i,
  );
  if (failedMatch) {
    matchedTicker = failedMatch[1].toUpperCase();
    updateTickerStatus(state, matchedTicker, {
      status: "error",
      message,
      updatedAt: timestamp,
      finishedAt: timestamp,
      source: "memory",
    });
  }

  const gateMatch = message.match(/\[Gate:([A-Z0-9.-]+)\]\s*(.+)/i);
  if (gateMatch) {
    matchedTicker = gateMatch[1].toUpperCase();
    updateTickerStatus(state, matchedTicker, {
      status: "skipped",
      message: gateMatch[2].trim(),
      updatedAt: timestamp,
      finishedAt: timestamp,
      source: "memory",
    });
  }

  const skipMatch = message.match(/SKIPPING\s+([A-Z0-9.-]+):\s*(.+)/i);
  if (skipMatch) {
    matchedTicker = skipMatch[1].toUpperCase();
    updateTickerStatus(state, matchedTicker, {
      status: "skipped",
      message: skipMatch[2].trim(),
      updatedAt: timestamp,
      finishedAt: timestamp,
      source: "memory",
    });
  }

  const abortedMatch = message.match(/Job aborted early for\s+([A-Z0-9.-]+):\s*(.+)/i);
  if (abortedMatch) {
    matchedTicker = abortedMatch[1].toUpperCase();
    updateTickerStatus(state, matchedTicker, {
      status: "skipped",
      message: abortedMatch[2].trim(),
      updatedAt: timestamp,
      finishedAt: timestamp,
      source: "memory",
    });
  }

  const shellMatch = message.match(/Shell Company block applied for\s+([A-Z0-9.-]+)/i);
  if (shellMatch) {
    matchedTicker = shellMatch[1].toUpperCase();
    updateTickerStatus(state, matchedTicker, {
      status: "skipped",
      message: "Skipped because the company is classified as a shell company",
      updatedAt: timestamp,
      finishedAt: timestamp,
      source: "memory",
    });
  }

  const missingDataMatch = message.match(
    /Missing Data block applied for\s+([A-Z0-9.-]+)/i,
  );
  if (missingDataMatch) {
    matchedTicker = missingDataMatch[1].toUpperCase();
    updateTickerStatus(state, matchedTicker, {
      status: "skipped",
      message: "Skipped because sector or industry data is incomplete",
      updatedAt: timestamp,
      finishedAt: timestamp,
      source: "memory",
    });
  }

  const workerMatch = message.match(/\[Worker:([A-Z0-9.-]+)\]\s*(.+)/i);
  if (workerMatch) {
    matchedTicker = workerMatch[1].toUpperCase();
    const workerMessage = workerMatch[2].trim();
    const currentStatus = state.tickerStatuses[matchedTicker]?.status ?? "pending";
    updateTickerStatus(state, matchedTicker, {
      status: /error|failed/i.test(workerMessage)
        ? "error"
        : currentStatus,
      message: workerMessage,
      updatedAt: timestamp,
      finishedAt: /error|failed/i.test(workerMessage) ? timestamp : null,
      source: "memory",
    });
  }

  appendLog(state, source, inferLogLevel(message, source), message, matchedTicker);
}

function attachLineReader(
  state: InternalState,
  stream: Readable,
  source: MonitorLogEntry["source"],
) {
  let buffer = "";
  stream.setEncoding("utf8");

  stream.on("data", (chunk: string) => {
    buffer += chunk;
    const lines = buffer.split(/\r?\n/);
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      processLogLine(state, source, line);
    }
  });

  stream.on("end", () => {
    if (buffer.trim()) {
      processLogLine(state, source, buffer);
    }
  });
}

function mapDbStatus(status: string | undefined): TickerRunStatus {
  switch ((status ?? "").toLowerCase()) {
    case "running":
      return "running";
    case "completed":
      return "success";
    case "success":
      return "success";
    case "gate_skipped":
    case "skipped":
    case "shell_company":
      return "skipped";
    case "stopped":
      return "stopped";
    case "failed":
    case "failure":
    case "qual_failure":
    case "exception":
      return "error";
    default:
      return "pending";
  }
}

function prettifyToken(value: string): string {
  return value.replace(/_/g, " ").trim();
}

function deriveDbMessage(payload: unknown): string {
  if (!payload || typeof payload !== "object") {
    return "Status updated";
  }

  const record = payload as Record<string, unknown>;
  const error =
    typeof record.error === "string" ? record.error.trim() : undefined;
  if (error) {
    return error;
  }

  const reason =
    typeof record.reason === "string" ? prettifyToken(record.reason) : undefined;
  if (reason) {
    return reason;
  }

  const failureStage =
    typeof record.failure_stage === "string"
      ? prettifyToken(record.failure_stage)
      : undefined;
  if (failureStage) {
    return failureStage;
  }

  const runReasons = Array.isArray(record.run_reasons)
    ? record.run_reasons.filter((value): value is string => typeof value === "string")
    : [];
  if (runReasons.length > 0) {
    return `Run reason: ${runReasons.map(prettifyToken).join(", ")}`;
  }

  const status =
    typeof record.status === "string" ? prettifyToken(record.status) : undefined;
  if (status) {
    return status;
  }

  return "Status updated";
}

function toIso(value: unknown): string | null {
  if (!value) {
    return null;
  }

  if (value instanceof Date) {
    return value.toISOString();
  }

  if (typeof value === "string") {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
  }

  return null;
}

async function hydrateStatusesFromDatabase(state: InternalState) {
  if (state.requestedTickers.length === 0) {
    return;
  }

  try {
    const pool = getPool();
    const keys = state.requestedTickers.map((ticker) => `status:${ticker}`);
    const { rows } = await pool.query<{
      key: string;
      value: Record<string, unknown> | null;
      last_updated: Date | string | null;
    }>(
      `SELECT key, value, last_updated
       FROM system_status
       WHERE key = ANY($1::text[])`,
      [keys],
    );

    for (const row of rows) {
      const ticker = row.key.replace(/^status:/, "").toUpperCase();
      const mappedStatus = mapDbStatus((row.value ?? {}).status as string | undefined);
      const existing = state.tickerStatuses[ticker];

      if (existing?.status === "stopped" && mappedStatus !== "stopped") {
        continue;
      }

      if (
        existing &&
        isTerminalStatus(existing.status) &&
        !isTerminalStatus(mappedStatus)
      ) {
        continue;
      }

      const payload = row.value ?? {};
      const dbUpdatedAt = toIso(row.last_updated) ?? nowIso();
      const startedAt = toIso((payload as Record<string, unknown>).started_at);
      const finishedAt =
        toIso((payload as Record<string, unknown>).finished_at) ??
        toIso((payload as Record<string, unknown>).completed_at) ??
        (isTerminalStatus(mappedStatus) ? dbUpdatedAt : null);

      updateTickerStatus(state, ticker, {
        status: mappedStatus,
        message: deriveDbMessage(payload),
        updatedAt: dbUpdatedAt,
        startedAt: startedAt ?? existing?.startedAt ?? null,
        finishedAt,
        source: "database",
      });
    }
  } catch {
    // DB status is a best-effort enhancement only.
  }
}

function markUnfinishedTickers(
  state: InternalState,
  status: Extract<TickerRunStatus, "error" | "skipped" | "stopped">,
  message: string,
) {
  const timestamp = nowIso();
  for (const ticker of state.requestedTickers) {
    const existing = state.tickerStatuses[ticker];
    if (existing && isTerminalStatus(existing.status)) {
      continue;
    }

    updateTickerStatus(state, ticker, {
      status,
      message,
      updatedAt: timestamp,
      finishedAt: timestamp,
      source: "memory",
    });
  }
}

async function finalizeProcessExit(
  state: InternalState,
  code: number | null,
  signal: NodeJS.Signals | null,
) {
  state.child = null;
  state.isRunning = false;
  state.pid = null;
  state.finishedAt = nowIso();
  state.lastUpdatedAt = state.finishedAt;
  state.lastExitCode = code;
  state.lastExitSignal = signal;

  await hydrateStatusesFromDatabase(state);

  if (state.stopRequested) {
    state.jobState = "stopped";
    markUnfinishedTickers(state, "stopped", "Stopped by operator");
    appendLog(state, "system", "warning", "Job stopped by operator.");
  } else if (code === 0) {
    markUnfinishedTickers(
      state,
      "skipped",
      "Runner finished without a terminal status log for this ticker",
    );
    const hasErrors = state.requestedTickers.some(
      (ticker) => state.tickerStatuses[ticker]?.status === "error",
    );
    state.jobState = hasErrors ? "failed" : "completed";
    appendLog(
      state,
      "system",
      hasErrors ? "warning" : "success",
      hasErrors
        ? "Runner exited cleanly but one or more tickers failed."
        : "Runner finished successfully.",
    );
  } else {
    state.jobState = "failed";
    markUnfinishedTickers(
      state,
      "error",
      "Runner exited unexpectedly before finishing this ticker",
    );
    appendLog(
      state,
      "system",
      "error",
      `Runner exited with code ${code ?? "unknown"}${signal ? ` (${signal})` : ""}.`,
    );
  }

  state.stopRequested = false;
  state.currentTicker = null;
  state.summary = buildSummary(state);
}

function resolvePythonCommand(): string {
  const winVenv = path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  if (existsSync(winVenv)) {
    return winVenv;
  }

  const unixVenv = path.join(REPO_ROOT, ".venv", "bin", "python");
  if (existsSync(unixVenv)) {
    return unixVenv;
  }

  return process.platform === "win32" ? "python" : "python3";
}

export async function getBackendMonitorSnapshot(): Promise<BackendMonitorSnapshot> {
  const state = getState();
  await hydrateStatusesFromDatabase(state);
  state.summary = buildSummary(state);
  return toSnapshot(state);
}

export async function startBackendMonitorJob(
  input: string | string[] | null | undefined,
): Promise<BackendMonitorSnapshot> {
  if (process.env.VERCEL || process.env.VERCEL_ENV) {
    throw new Error(
      "This runner cannot start on Vercel serverless. Run the admin monitor from your local machine or move the Python job to a dedicated worker.",
    );
  }

  const state = getState();
  if (state.isRunning) {
    throw new Error("An analysis job is already running.");
  }

  const manualTickers = normalizeTickers(input);
  const requestedTickers = manualTickers;

  if (requestedTickers.length === 0) {
    throw new Error("Enter at least one ticker.");
  }

  state.child = null;
  state.jobState = "running";
  state.isRunning = true;
  state.stopRequested = false;
  state.sourceMode = "manual";
  state.defaultTickers = [];
  state.requestedTickers = requestedTickers;
  state.currentTicker = null;
  state.startedAt = nowIso();
  state.finishedAt = null;
  state.lastUpdatedAt = state.startedAt;
  state.pid = null;
  state.lastExitCode = null;
  state.lastExitSignal = null;
  state.logs = [];
  state.tickerStatuses = createTickerStatuses(requestedTickers);
  state.summary = `Starting ${requestedTickers.join(", ")}`;

  const command = resolvePythonCommand();
  const child = spawn(command, ["-u", "-m", "backend.unified_runner"], {
    cwd: REPO_ROOT,
    env: {
      ...process.env,
      TEST_TICKER: requestedTickers.join(", "),
      PYTHONIOENCODING: "utf-8",
    },
    detached: process.platform !== "win32",
    stdio: ["ignore", "pipe", "pipe"],
  });

  state.child = child;
  state.pid = child.pid ?? null;

  appendLog(
    state,
    "system",
    "info",
    `Started runner for ${requestedTickers.join(", ")}`,
  );
  appendLog(
    state,
    "system",
    "info",
    `Database target: ${getRunnerDatabaseTargetLabel()}`,
  );

  attachLineReader(state, child.stdout, "stdout");
  attachLineReader(state, child.stderr, "stderr");

  let finalized = false;
  const finalizeOnce = (code: number | null, signal: NodeJS.Signals | null) => {
    if (finalized) {
      return;
    }
    finalized = true;
    void finalizeProcessExit(state, code, signal);
  };

  child.once("error", (error) => {
    appendLog(state, "system", "error", `Failed to start runner: ${error.message}`);
    finalizeOnce(1, null);
  });

  child.once("close", (code, signal) => {
    finalizeOnce(code, signal);
  });

  return toSnapshot(state);
}

async function killProcessTree(pid: number) {
  if (process.platform === "win32") {
    await new Promise<void>((resolve, reject) => {
      const killer = spawn("taskkill", ["/pid", String(pid), "/t", "/f"], {
        stdio: "ignore",
      });
      killer.once("error", reject);
      killer.once("close", (code) => {
        if (code === 0) {
          resolve();
          return;
        }
        reject(new Error(`taskkill exited with code ${code}`));
      });
    });
    return;
  }

  process.kill(-pid, "SIGTERM");
}

export async function stopBackendMonitorJob(): Promise<BackendMonitorSnapshot> {
  const state = getState();
  if (!state.isRunning || !state.child || !state.pid) {
    state.summary = buildSummary(state);
    return toSnapshot(state);
  }

  state.stopRequested = true;
  state.jobState = "stopping";
  state.summary = "Stopping the current analysis job...";
  appendLog(state, "system", "warning", `Stopping runner pid ${state.pid}...`);

  await killProcessTree(state.pid);
  return toSnapshot(state);
}

export async function clearBackendMonitorLogs(): Promise<BackendMonitorSnapshot> {
  const state = getState();
  state.logs = [];
  state.lastUpdatedAt = nowIso();
  state.summary = buildSummary(state);
  return toSnapshot(state);
}

function toSnapshot(state: InternalState): BackendMonitorSnapshot {
  const progress = computeProgress(state);

  return {
    jobState: state.jobState,
    isRunning: state.isRunning,
    sourceMode: state.sourceMode,
    defaultTickers: state.defaultTickers,
    requestedTickers: state.requestedTickers,
    currentTicker: state.currentTicker,
    startedAt: state.startedAt,
    finishedAt: state.finishedAt,
    lastUpdatedAt: state.lastUpdatedAt,
    pid: state.pid,
    lastExitCode: state.lastExitCode,
    lastExitSignal: state.lastExitSignal,
    summary: state.summary,
    progress,
    tickerStatuses: state.requestedTickers.map(
      (ticker) =>
        state.tickerStatuses[ticker] ?? {
          ticker,
          status: "pending",
          message: "Waiting in queue",
          updatedAt: null,
          startedAt: null,
          finishedAt: null,
          source: "memory",
        },
    ),
    logs: state.logs.slice(-SNAPSHOT_LOG_LIMIT),
  };
}
