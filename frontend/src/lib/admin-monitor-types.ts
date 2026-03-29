export type MonitorLogLevel = "info" | "success" | "warning" | "error";

export type TickerRunStatus =
  | "pending"
  | "running"
  | "success"
  | "error"
  | "skipped"
  | "stopped";

export type MonitorJobState =
  | "idle"
  | "running"
  | "stopping"
  | "completed"
  | "failed"
  | "stopped";

export interface MonitorLogEntry {
  id: string;
  timestamp: string;
  source: "system" | "stdout" | "stderr";
  level: MonitorLogLevel;
  message: string;
  ticker: string | null;
}

export interface TickerStatusItem {
  ticker: string;
  status: TickerRunStatus;
  message: string;
  updatedAt: string | null;
  startedAt: string | null;
  finishedAt: string | null;
  source: "memory" | "database";
}

export interface BackendMonitorSnapshot {
  jobState: MonitorJobState;
  isRunning: boolean;
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
  progress: {
    completed: number;
    total: number;
    percentage: number;
  };
  tickerStatuses: TickerStatusItem[];
  logs: MonitorLogEntry[];
}
