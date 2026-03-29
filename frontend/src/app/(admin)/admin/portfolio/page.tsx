"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import dynamic from "next/dynamic";
import styles from "./portfolio/portfolio.module.css";
import { SearchBox } from "@/components/SearchBox";
import { UserProfileDropdown } from "@/components/UserProfileDropdown";
import { PerformanceChart } from "./portfolio/PerformanceChart";
import { PerformanceScrollTable } from "./portfolio/PerformanceScrollTable";
import DashboardLoading from "./loading";

type PortfolioState = Record<string, unknown>;

type Checkpoint = {
  year: number;
  month: number;
  portfolio_value: number | null;
  cagr: number | null;
  total_return: number | null;
  sharpe: number | null;
  drawdown: number | null;
};

type PositionRow = {
  ticker: string;
  conviction_score: number | null;
  conviction_change_pct: number | null;
  margin_of_safety: number | null;
  mos_change_pct: number | null;
  current_pct: number | null;
  target_pct: number | null;
  delta_pct: number | null;
  action_label: string | null;
  action: string | null;
  current_value: number | null;
};

type DashboardData = {
  state: PortfolioState;
  checkpoints: Checkpoint[];
  positions: PositionRow[];
};

type StockSummary = {
  ticker: string;
  company_name?: string;
};

const callApi = async (path: string, init?: RequestInit) => {
  const res = await fetch(path, init);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} at ${path}`);
  }
  return res;
};

const EMPTY_DATA: DashboardData = {
  state: {},
  checkpoints: [],
  positions: [],
};

const NUMBER_FORMAT = new Intl.NumberFormat(undefined, {
  maximumFractionDigits: 0,
});

const PERCENT_FORMAT = (value: number | null | undefined, fraction = 1) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(fraction)}%`;
};

const normaliseNumber = (value: unknown): number => {
  if (value === null || value === undefined) return 0;
  const num = Number(value);
  return Number.isFinite(num) ? num : 0;
};

const buildSeries = (
  rows: Checkpoint[],
  key: "cagr" | "total_return",
): { label: string; value: number }[] =>
  rows
    .map((row) => {
      const year = Number(row.year ?? 0);
      const month = Number(row.month ?? 0);
      const raw = row[key];
      if (!year || !month || raw === null || raw === undefined) {
        return null;
      }
      const value = Number(raw);
      if (!Number.isFinite(value)) {
        return null;
      }
      const months = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec",
      ];
      const monthIndex = Math.min(Math.max(month, 1), 12) - 1;
      const label = `${months[monthIndex]} ${year}`;
      return { label, value };
    })
    .filter((point): point is { label: string; value: number } => point !== null);

const pickYearlyCheckpoints = (rows: Checkpoint[]) => {
  const map = new Map<number, Checkpoint>();

  rows.forEach((row) => {
    const key = Number(row.year ?? 0);
    const month = Number(row.month ?? 0);
    if (!key) return;
    const existing = map.get(key);
    if (!existing || month >= Number(existing.month ?? 0)) {
      map.set(key, row);
    }
  });

  return Array.from(map.values())
    .map((row) => ({
      year: Number(row.year ?? 0),
      month: Number(row.month ?? 0),
      cagr: row.cagr === null ? null : Number(row.cagr),
      total_return: row.total_return === null ? null : Number(row.total_return),
      sharpe: row.sharpe === null ? null : Number(row.sharpe),
      drawdown: row.drawdown === null ? null : Number(row.drawdown),
    }))
    .filter((entry) => entry.year !== 0)
    .sort((a, b) => b.year - a.year);
};

const splitPositions = (rows: PositionRow[]) => {
  const cash = rows.find((row) => row.ticker === "CASH") ?? null;
  const equities = rows.filter((row) => row.ticker !== "CASH");

  const stockValue = equities.reduce(
    (acc, row) => acc + normaliseNumber(row.current_value),
    0,
  );
  const cashValue = normaliseNumber(cash?.current_value);

  return { cash, equities, stockValue, cashValue };
};

const fetchDashboard = async (): Promise<DashboardData> => {
  const res = await callApi("/api/portfolio/dashboard", {
    cache: "no-store",
  });
  const data = (await res.json()) as DashboardData;
  return {
    state: data.state ?? {},
    checkpoints: data.checkpoints ?? [],
    positions: data.positions ?? [],
  };
};

const postCashMutation = async (
  action: "deposit" | "withdraw",
  amount: number,
): Promise<DashboardData> => {
  const res = await callApi(`/api/portfolio/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ amount }),
  });

  const data = (await res.json()) as DashboardData;
  return {
    state: data.state ?? {},
    checkpoints: data.checkpoints ?? [],
    positions: data.positions ?? [],
  };
};

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData>(EMPTY_DATA);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [cashAction, setCashAction] = useState<"deposit" | "withdraw" | null>(
    null,
  );
  const [cashAmount, setCashAmount] = useState("");
  const [cashError, setCashError] = useState<string | null>(null);
  const [cashSubmitting, setCashSubmitting] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const next = await fetchDashboard();
      setData(next);
    } catch (err) {
      console.error(err);
      setError(
        err instanceof Error
          ? err.message
          : "ไม่สามารถโหลดข้อมูลพอร์ตได้",
      );
      setData(EMPTY_DATA);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const checkpoints = useMemo(() => {
    return [...data.checkpoints].sort((a, b) => {
      const aIndex = Number(a.year ?? 0) * 12 + Number(a.month ?? 0);
      const bIndex = Number(b.year ?? 0) * 12 + Number(b.month ?? 0);
      return aIndex - bIndex;
    });
  }, [data.checkpoints]);

  const cagrSeries = useMemo(() => buildSeries(checkpoints, "cagr"), [checkpoints]);
  const totalSeries = useMemo(
    () => buildSeries(checkpoints, "total_return"),
    [checkpoints],
  );

  const yearlyRecords = useMemo(() => pickYearlyCheckpoints(checkpoints), [checkpoints]);

  const { cash, equities, stockValue, cashValue } = useMemo(
    () => splitPositions(data.positions),
    [data.positions],
  );

  const equitiesFiltered = equities;

  const portfolioValue = normaliseNumber(data.state.portfolio_value);
  const cagr = data.state.cagr === null ? null : normaliseNumber(data.state.cagr);
  const totalReturn =
    data.state.total_return === null
      ? null
      : normaliseNumber(data.state.total_return);
  const sharpe =
    data.state.sharpe_ratio === null
      ? null
      : Number(data.state.sharpe_ratio);
  const drawdown =
    data.state.max_drawdown === null
      ? null
      : Number(data.state.max_drawdown);

  const totalValueForDonut = stockValue + cashValue || portfolioValue;
  const stockPct =
    totalValueForDonut > 0 ? (stockValue / totalValueForDonut) * 100 : 0;
  const cashPct =
    totalValueForDonut > 0 ? (cashValue / totalValueForDonut) * 100 : 0;

  const sortedCheckpoints = checkpoints;
  let recentChange: number | null = null;
  if (sortedCheckpoints.length >= 2) {
    const last = sortedCheckpoints[sortedCheckpoints.length - 1];
    const prev = sortedCheckpoints[sortedCheckpoints.length - 2];
    const lastVal = Number(last.portfolio_value ?? 0);
    const prevVal = Number(prev.portfolio_value ?? 0);
    if (lastVal > 0 && prevVal > 0) {
      recentChange = ((lastVal - prevVal) / prevVal) * 100;
    }
  }

  // No search filtering on dashboard anymore for now, search navigates to stock page.


  const handleCashSubmit = async (action: "deposit" | "withdraw") => {
    const amount = Number(cashAmount);
    if (!Number.isFinite(amount) || amount <= 0) {
      setCashError("กรุณาระบุจำนวนเงินที่ถูกต้อง");
      return;
    }

    try {
      setCashSubmitting(true);
      const next = await postCashMutation(action, amount);
      setData(next);
      setCashAction(null);
      setCashAmount("");
      setCashError(null);
    } catch (err) {
      console.error(err);
      setCashError(err instanceof Error ? err.message : "เกิดข้อผิดพลาด");
    } finally {
      setCashSubmitting(false);
    }
  };

  if (loading) {
    return <DashboardLoading />;
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className={styles.titleGroup}>
          <h1>Dashboard</h1>
          <p className={styles.leadText}>
            ภาพรวมพอร์ตแบบเรียลไทม์อัปเดตหลังวิเคราะห์ทุกครั้ง
          </p>
        </div>
        <div className={styles.actionRow}>
          <SearchBox placeholder="Search holdings" />
          <UserProfileDropdown />
          <button
            className={styles.depositButton}
            onClick={() => {
              setCashAction((prev) => (prev === "deposit" ? null : "deposit"));
              setCashError(null);
            }}
          >
            Deposit
          </button>
          <button
            className={styles.withdrawButton}
            onClick={() => {
              setCashAction((prev) => (prev === "withdraw" ? null : "withdraw"));
              setCashError(null);
            }}
          >
            Withdraw
          </button>
        </div>
      </header>

      {cashAction ? (
        <div className={styles.cashForm}>
          <span className={styles.cashFormLabel}>
            {cashAction === "deposit" ? "เพิ่มเงินสด" : "ถอนเงินสด"}
          </span>
          <input
            type="number"
            min="0"
            step="100"
            placeholder="Amount"
            value={cashAmount}
            onChange={(event) => setCashAmount(event.target.value)}
            className={styles.cashInput}
          />
          <div className={styles.cashActions}>
            <button
              className={`${styles.cashConfirm} ${
                cashAction === "withdraw" ? styles.cashConfirmWithdraw : ""
              }`}
              onClick={() => handleCashSubmit(cashAction)}
              disabled={cashSubmitting}
            >
              {cashSubmitting ? "Processing..." : "Confirm"}
            </button>
            <button
              className={styles.cashCancel}
              onClick={() => {
                setCashAction(null);
                setCashAmount("");
                setCashError(null);
              }}
            >
              Cancel
            </button>
          </div>
          {cashError ? (
            <p className={styles.errorText}>{cashError}</p>
          ) : null}
        </div>
      ) : null}

      {error ? <div className={styles.errorText}>{error}</div> : null}

      <section className={styles.contentGrid}>
        <article className={`${styles.card} ${styles.portfolioCard}`}>
          <div className={styles.donutWrapper}>
            <div
              className={styles.donut}
              suppressHydrationWarning={true}
              style={{
                "--percent": `${stockPct}%`,
                "--accent": "#0f4dbc",
              } as React.CSSProperties}
            >
              <div className={styles.donutValue}>
                ${NUMBER_FORMAT.format(portfolioValue)}
                <span>Current Value</span>
              </div>
            </div>
          </div>
          <div className={styles.legend}>
            <div className={styles.legendRow}>
              <strong>Stock</strong>
              <span>
                {PERCENT_FORMAT(stockPct)} · ${NUMBER_FORMAT.format(stockValue)}
              </span>
            </div>
            <div className={styles.legendRow}>
              <strong>Cash</strong>
              <span>
                {PERCENT_FORMAT(cashPct)} · ${NUMBER_FORMAT.format(cashValue)}
              </span>
            </div>
            <div className={styles.growthText}>
              {recentChange === null
                ? "ยังไม่มีการเปลี่ยนแปลงล่าสุด"
                : `${recentChange >= 0 ? "+" : ""}${recentChange.toFixed(1)}% since last checkpoint`}
            </div>
          </div>
        </article>

        <article className={styles.card}>
          <h3>Key Metrics</h3>
          <div className={styles.metricsList}>
            <div className={styles.metricItem}>
              <span className={styles.metricLabel}>CAGR</span>
              <span className={styles.metricValue}>{PERCENT_FORMAT(cagr)}</span>
            </div>
            <div className={styles.metricItem}>
              <span className={styles.metricLabel}>Total Return</span>
              <span className={styles.metricValue}>{PERCENT_FORMAT(totalReturn)}</span>
            </div>
            <div className={styles.metricItem}>
              <span className={styles.metricLabel}>Sharpe Ratio</span>
              <span className={styles.metricValue}>
                {sharpe === null ? "—" : sharpe.toFixed(2)}
              </span>
            </div>
            <div className={styles.metricItem}>
              <span className={styles.metricLabel}>Max Drawdown</span>
              <span
                className={`${styles.metricValue} ${
                  drawdown !== null && drawdown < 0 ? styles.metricNegative : ""
                }`}
              >
                {PERCENT_FORMAT(drawdown)}
              </span>
            </div>
          </div>
        </article>
      </section>

      <PerformanceChart
        cagrSeries={cagrSeries}
        totalReturnSeries={totalSeries}
        currentValue={portfolioValue}
      />

      <section className={styles.contentGrid}>
        <PerformanceScrollTable records={yearlyRecords} />

        <article className={styles.tableCard}>
          <div>
            <h3>Portfolio Holdings</h3>
            <p className={styles.mutedCaption}>
              Conviction · Margin of Safety · Action ล่าสุด
            </p>
          </div>
          {loading ? (
            <div className={styles.emptyState}>กำลังโหลดข้อมูล...</div>
          ) : equitiesFiltered.length === 0 && !cash ? (
            <div className={styles.emptyState}>
              ยังไม่มีตำแหน่งในพอร์ต
            </div>
          ) : (
            <table className={styles.holdingsTable}>
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Conviction (%)</th>
                  <th>MoS (%)</th>
                  <th>Target (%)</th>
                  <th>Current (%)</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {equitiesFiltered.map((row) => {
                  const mos = row.margin_of_safety
                    ? row.margin_of_safety * 100
                    : 0;
                  const convChange = row.conviction_change_pct ?? null;
                  const mosChange = row.mos_change_pct ?? null;
                  const actionLabel = (row.action_label ?? "").toLowerCase();

                  return (
                    <tr key={row.ticker}>
                      <td className={styles.tickerCell}>
                        <Link href={`/stock/${row.ticker}`}>{row.ticker}</Link>
                      </td>
                      <td>
                        <div className={styles.cellFlex}>
                          <span>{row.conviction_score?.toFixed(0) ?? "—"}</span>
                          {convChange !== null ? (
                            <span
                              className={
                                convChange >= 0
                                  ? styles.changePositive
                                  : styles.changeNegative
                              }
                            >
                              {convChange >= 0 ? "+" : ""}
                              {convChange.toFixed(1)}%
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <div className={styles.cellFlex}>
                          <span>{mos.toFixed(1)}</span>
                          {mosChange !== null ? (
                            <span
                              className={
                                mosChange >= 0
                                  ? styles.changePositive
                                  : styles.changeNegative
                              }
                            >
                              {mosChange >= 0 ? "+" : ""}
                              {mosChange.toFixed(1)}%
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td>{PERCENT_FORMAT(row.target_pct)}</td>
                      <td>{PERCENT_FORMAT(row.current_pct)}</td>
                      <td>
                        <button
                          className={`${styles.actionButton} ${
                            actionLabel === "sell" || actionLabel === "trim"
                              ? styles.actionButtonSell
                              : ""
                          }`}
                        >
                          {(row.action_label ?? "Hold").toUpperCase()}
                        </button>
                      </td>
                    </tr>
                  );
                })}
                {cash ? (
                  <tr key="cash">
                    <td className={styles.tickerCell}>CASH</td>
                    <td>—</td>
                    <td>—</td>
                    <td>{PERCENT_FORMAT(cash.target_pct)}</td>
                    <td>{PERCENT_FORMAT(cash.current_pct)}</td>
                    <td>
                      <button className={styles.actionButton}>HOLD</button>
                    </td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          )}
        </article>
      </section>
    </div>
  );
}
