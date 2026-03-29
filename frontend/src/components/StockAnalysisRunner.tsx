"use client";

import type { CSSProperties, KeyboardEvent } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  LoaderCircle,
  Play,
  RefreshCw,
  RotateCcw,
  Square,
  X,
} from "lucide-react";

import type {
  BackendMonitorSnapshot,
  MonitorJobState,
  MonitorLogEntry,
  TickerRunStatus,
} from "@/lib/admin-monitor-types";

const EMPTY_SNAPSHOT: BackendMonitorSnapshot = {
  jobState: "idle",
  isRunning: false,
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
  progress: {
    completed: 0,
    total: 0,
    percentage: 0,
  },
  tickerStatuses: [],
  logs: [],
};

const JOB_STATE_STYLES: Record<MonitorJobState, string> = {
  idle: "border-slate-700 bg-slate-900 text-slate-200",
  running: "border-blue-700/60 bg-blue-950/50 text-blue-200",
  stopping: "border-amber-700/60 bg-amber-950/50 text-amber-200",
  completed: "border-emerald-700/60 bg-emerald-950/50 text-emerald-200",
  failed: "border-red-700/60 bg-red-950/50 text-red-200",
  stopped: "border-orange-700/60 bg-orange-950/50 text-orange-200",
};

const STATUS_STYLES: Record<TickerRunStatus, string> = {
  pending: "border-slate-700 bg-slate-900 text-slate-300",
  running: "border-blue-700/60 bg-blue-950/50 text-blue-200",
  success: "border-emerald-700/60 bg-emerald-950/50 text-emerald-200",
  error: "border-red-700/60 bg-red-950/50 text-red-200",
  skipped: "border-slate-700 bg-slate-900 text-slate-300",
  stopped: "border-orange-700/60 bg-orange-950/50 text-orange-200",
};

const LOG_LEVEL_STYLES: Record<MonitorLogEntry["level"], string> = {
  info: "border-slate-700 bg-slate-950/80 text-slate-200",
  success: "border-emerald-700/40 bg-emerald-950/70 text-emerald-200",
  warning: "border-amber-700/40 bg-amber-950/70 text-amber-200",
  error: "border-red-700/40 bg-red-950/70 text-red-200",
};

const INPUT_STYLE: CSSProperties = {
  WebkitTextFillColor: "#e5e7eb",
  caretColor: "#e5e7eb",
};

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

function mergeTickers(existing: string[], incoming: string[]): string[] {
  return Array.from(new Set([...existing, ...incoming]));
}

function formatDateTime(value: string | null): string {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }

  return new Intl.DateTimeFormat("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}

function prettifyLabel(value: string): string {
  return value.replace(/_/g, " ");
}

async function parseApiResponse(response: Response) {
  const data = (await response.json().catch(() => null)) as
    | BackendMonitorSnapshot
    | { error?: string }
    | null;

  if (!response.ok) {
    throw new Error(
      (data && "error" in data && data.error) || "Request failed.",
    );
  }

  return data as BackendMonitorSnapshot;
}

export function StockAnalysisRunner({ className = "" }: { className?: string }) {
  const [snapshot, setSnapshot] = useState<BackendMonitorSnapshot>(EMPTY_SNAPSHOT);
  const [tickerInput, setTickerInput] = useState("");
  const [draftTickers, setDraftTickers] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<
    "start" | "stop" | "clear" | null
  >(null);
  const seededDraftRef = useRef(false);

  const recentLogs = useMemo(() => [...snapshot.logs].reverse(), [snapshot.logs]);
  const canEditTickers = !snapshot.isRunning && pendingAction === null;

  const loadSnapshot = async (keepExistingError = false) => {
    try {
      const response = await fetch("/api/admin/stocks-sync", {
        cache: "no-store",
      });
      const data = await parseApiResponse(response);
      setSnapshot(data);
      if (!keepExistingError) {
        setError(null);
      }
    } catch (requestError) {
      if (!keepExistingError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Failed to load runner.",
        );
      }
    }
  };

  useEffect(() => {
    void loadSnapshot();

    const timer = window.setInterval(() => {
      void loadSnapshot(true);
    }, 3000);

    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (seededDraftRef.current || snapshot.requestedTickers.length === 0) {
      return;
    }

    setDraftTickers(snapshot.requestedTickers);
    seededDraftRef.current = true;
  }, [snapshot.requestedTickers]);

  const addTickers = (rawValue: string) => {
    const parsed = normalizeTickers(rawValue);
    if (parsed.length === 0) {
      return;
    }

    setDraftTickers((current) => mergeTickers(current, parsed));
    setTickerInput("");
    seededDraftRef.current = true;
  };

  const handleStart = async () => {
    const manualTickers = mergeTickers(draftTickers, normalizeTickers(tickerInput));
    setPendingAction("start");

    try {
      const response = await fetch("/api/admin/stocks-sync", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          tickers: manualTickers,
        }),
      });
      const data = await parseApiResponse(response);
      setSnapshot(data);
      setDraftTickers(data.requestedTickers);
      setTickerInput("");
      seededDraftRef.current = true;
      setError(null);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to start analysis job.",
      );
    } finally {
      setPendingAction(null);
    }
  };

  const handleStop = async () => {
    setPendingAction("stop");
    try {
      const response = await fetch("/api/admin/stocks-sync", {
        method: "DELETE",
      });
      const data = await parseApiResponse(response);
      setSnapshot(data);
      setError(null);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to stop analysis job.",
      );
    } finally {
      setPendingAction(null);
    }
  };

  const handleClearLogs = async () => {
    setPendingAction("clear");
    try {
      const response = await fetch("/api/admin/stocks-sync", {
        method: "PATCH",
      });
      const data = await parseApiResponse(response);
      setSnapshot(data);
      setError(null);
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : "Failed to clear logs.",
      );
    } finally {
      setPendingAction(null);
    }
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key !== "Enter" && event.key !== ",") {
      return;
    }

    event.preventDefault();
    addTickers(tickerInput);
  };

  const handleRemoveTicker = (ticker: string) => {
    setDraftTickers((current) => current.filter((item) => item !== ticker));
    seededDraftRef.current = true;
  };

  return (
    <section
      className={`rounded-3xl border border-slate-800 bg-[#0b1120] p-5 text-slate-100 shadow-sm ${className}`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="text-xl font-semibold">Analyze</div>
        <div
          className={`inline-flex items-center gap-2 self-start rounded-full border px-3 py-1 text-sm capitalize ${JOB_STATE_STYLES[snapshot.jobState]}`}
        >
          {snapshot.jobState === "running" || snapshot.jobState === "stopping" ? (
            <LoaderCircle className="h-4 w-4 animate-spin" />
          ) : null}
          {prettifyLabel(snapshot.jobState)}
        </div>
      </div>

      {error ? (
        <div className="mt-4 flex items-start gap-2 rounded-2xl border border-red-900/60 bg-red-950/40 px-3 py-2 text-sm text-red-200">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>{error}</span>
        </div>
      ) : null}

      <div className="mt-4 flex flex-col gap-3 lg:flex-row">
        <input
          value={tickerInput}
          onChange={(event) => setTickerInput(event.target.value)}
          onKeyDown={handleKeyDown}
          autoComplete="off"
          autoCapitalize="characters"
          spellCheck={false}
          placeholder="DNP, UNH"
          disabled={!canEditTickers}
          style={INPUT_STYLE}
          className="h-12 flex-1 rounded-2xl border border-slate-700 bg-slate-950 px-4 text-base text-slate-100 outline-none transition placeholder:text-slate-500 focus:border-blue-500 disabled:cursor-not-allowed disabled:opacity-60"
        />
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={() => addTickers(tickerInput)}
            disabled={!canEditTickers || normalizeTickers(tickerInput).length === 0}
            className="inline-flex h-12 items-center justify-center rounded-2xl border border-slate-700 px-4 text-sm font-medium text-slate-100 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Add
          </button>
          <button
            type="button"
            onClick={handleStart}
            disabled={snapshot.isRunning || pendingAction !== null}
            className="inline-flex h-12 items-center justify-center gap-2 rounded-2xl bg-blue-600 px-4 text-sm font-semibold text-white transition hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-blue-400/70"
          >
            {pendingAction === "start" ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Run
          </button>
          <button
            type="button"
            onClick={handleStop}
            disabled={!snapshot.isRunning || pendingAction !== null}
            className="inline-flex h-12 items-center justify-center gap-2 rounded-2xl bg-rose-500 px-4 text-sm font-semibold text-white transition hover:bg-rose-400 disabled:cursor-not-allowed disabled:bg-rose-300/70"
          >
            {pendingAction === "stop" ? (
              <LoaderCircle className="h-4 w-4 animate-spin" />
            ) : (
              <Square className="h-4 w-4" />
            )}
            Stop
          </button>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        {draftTickers.map((ticker) => (
          <span
            key={ticker}
            className="inline-flex items-center gap-2 rounded-full border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm"
          >
            {ticker}
            <button
              type="button"
              onClick={() => handleRemoveTicker(ticker)}
              disabled={!canEditTickers}
              className="rounded-full p-0.5 text-slate-400 transition hover:bg-slate-800 hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
              aria-label={`Remove ${ticker}`}
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </span>
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-slate-300">
        <span>{snapshot.summary}</span>
        <span className="text-slate-500">•</span>
        <span>{snapshot.progress.completed}/{snapshot.progress.total || 0}</span>
        <span className="text-slate-500">•</span>
        <span>{snapshot.currentTicker || "-"}</span>
      </div>

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={() => void loadSnapshot()}
          className="inline-flex items-center gap-2 rounded-2xl border border-slate-700 px-3 py-2 text-sm text-slate-200 transition hover:border-slate-500"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
        <button
          type="button"
          onClick={handleClearLogs}
          disabled={pendingAction !== null || snapshot.logs.length === 0}
          className="inline-flex items-center gap-2 rounded-2xl border border-slate-700 px-3 py-2 text-sm text-slate-200 transition hover:border-slate-500 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <RotateCcw className="h-4 w-4" />
          Clear Logs
        </button>
      </div>

      <div className="mt-5 grid grid-cols-1 gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div className="mb-3 text-sm font-semibold">Queue</div>
          <div className="space-y-2">
            {snapshot.tickerStatuses.length === 0 ? (
              <div className="text-sm text-slate-500">-</div>
            ) : (
              snapshot.tickerStatuses.map((item) => (
                <div
                  key={item.ticker}
                  className="rounded-2xl border border-slate-800 bg-slate-950 px-3 py-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium">{item.ticker}</span>
                    <span
                      className={`rounded-full border px-2 py-0.5 text-xs capitalize ${STATUS_STYLES[item.status]}`}
                    >
                      {prettifyLabel(item.status)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
          <div className="mb-3 text-sm font-semibold">Logs</div>
          <div className="max-h-[18rem] space-y-2 overflow-y-auto">
            {recentLogs.length === 0 ? (
              <div className="text-sm text-slate-500">-</div>
            ) : (
              recentLogs.map((log) => (
                <div
                  key={log.id}
                  className={`rounded-2xl border px-3 py-2 font-mono text-xs ${LOG_LEVEL_STYLES[log.level]}`}
                >
                  <div className="mb-1 flex flex-wrap gap-2 text-[10px] uppercase tracking-[0.16em] text-white/50">
                    <span>{formatDateTime(log.timestamp)}</span>
                    <span>{log.source}</span>
                    {log.ticker ? <span>{log.ticker}</span> : null}
                  </div>
                  <div className="whitespace-pre-wrap break-words">{log.message}</div>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      <style jsx>{`
        input:-webkit-autofill,
        input:-webkit-autofill:hover,
        input:-webkit-autofill:focus,
        input:-webkit-autofill:active {
          -webkit-text-fill-color: #e5e7eb !important;
          box-shadow: 0 0 0 1000px #020617 inset !important;
          transition: background-color 9999s ease-in-out 0s;
        }
      `}</style>
    </section>
  );
}
