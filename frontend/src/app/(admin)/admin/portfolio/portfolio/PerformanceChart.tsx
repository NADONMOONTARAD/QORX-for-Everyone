'use client';

import { useMemo, useState } from "react";
import styles from "./portfolio.module.css";

type ChartPoint = {
  label: string;
  value: number;
};

type PerformanceChartProps = {
  cagrSeries: ChartPoint[];
  totalReturnSeries: ChartPoint[];
  currentValue: number;
};

const buildPath = (points: ChartPoint[]) => {
  if (points.length === 0) {
    return { path: "", area: "", coords: [] as { x: number; y: number }[] };
  }

  if (points.length === 1) {
    return {
      path: "M0 80 L100 80",
      area: "M0 80 L100 80 L100 100 L0 100 Z",
      coords: [{ x: 100, y: 80 }],
    };
  }

  const values = points.map((p) => p.value);
  const max = Math.max(...values, 0.0001);
  const min = Math.min(...values, 0);
  const range = max - min || 1;

  const coords = points.map((point, index) => {
    const x = (index / (points.length - 1)) * 100;
    const norm = (point.value - min) / range;
    const y = 90 - norm * 70; // padding top/bottom
    return { x, y };
  });

  const line = coords
    .map((coord, index) =>
      index === 0 ? `M ${coord.x} ${coord.y}` : `L ${coord.x} ${coord.y}`,
    )
    .join(" ");

  const area =
    coords.length >= 2
      ? [
          `M ${coords[0].x} 100`,
          ...coords.map((coord) => `L ${coord.x} ${coord.y}`),
          `L ${coords[coords.length - 1].x} 100`,
          "Z",
        ].join(" ")
      : "";

  return { path: line, area, coords };
};

export function PerformanceChart({
  cagrSeries,
  totalReturnSeries,
  currentValue,
}: PerformanceChartProps) {
  const [mode, setMode] = useState<"cagr" | "total">("cagr");

  const activeSeries =
    mode === "cagr" ? cagrSeries : totalReturnSeries;

  const chartData = useMemo(() => buildPath(activeSeries), [activeSeries]);

  const lastPoint = activeSeries[activeSeries.length - 1];
  const lastCoord =
    chartData.coords[chartData.coords.length - 1] ?? { x: 0, y: 80 };

  return (
    <div className={styles.chartCard}>
      <div className={styles.chartHeader}>
        <div>
          <h3>Portfolio Performance</h3>
          <p className={styles.mutedCaption}>
            {mode === "cagr"
              ? "Compound annual growth rate over time"
              : "Total return trajectory since inception"}
          </p>
        </div>
        <div className={styles.tabGroup}>
          <button
            className={`${styles.tabButton} ${
              mode === "cagr" ? styles.tabButtonActive : ""
            }`}
            onClick={() => setMode("cagr")}
          >
            CAGR
          </button>
          <button
            className={`${styles.tabButton} ${
              mode === "total" ? styles.tabButtonActive : ""
            }`}
            onClick={() => setMode("total")}
          >
            Total Return
          </button>
        </div>
      </div>

      {activeSeries.length === 0 ? (
        <div className={styles.chartPlaceholder}>
          ยังไม่มีข้อมูลเพียงพอสำหรับสร้างกราฟ
        </div>
      ) : (
        <div className={styles.chartCanvas}>
          <svg viewBox="0 0 100 100" width="100%" height="260">
            <defs>
              <linearGradient id="areaFill" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="rgba(15, 77, 188, 0.28)" />
                <stop offset="100%" stopColor="rgba(15, 77, 188, 0.02)" />
              </linearGradient>
            </defs>
            <rect
              x="0"
              y="0"
              width="100"
              height="100"
              fill="url(#gridGradient)"
              opacity="0"
            />
            <path
              d={chartData.area}
              fill="url(#areaFill)"
              stroke="none"
            />
            <path
              d={chartData.path}
              fill="none"
              stroke="#0f4dbc"
              strokeWidth="2.2"
              strokeLinejoin="round"
              strokeLinecap="round"
            />
            <circle
              cx={lastCoord.x}
              cy={lastCoord.y}
              r="2.6"
              fill="#0f4dbc"
            />
          </svg>
          {lastPoint ? (
            <div
              className={styles.chartTooltip}
              style={{
                left: `calc(${lastCoord.x}% - 60px)`,
                top: `${lastCoord.y}%`,
              }}
            >
              <strong className={styles.chartTooltipValue}>
                ${currentValue.toLocaleString(undefined, {
                  maximumFractionDigits: 0,
                })}
              </strong>
              <span className={styles.chartTooltipNote}>
                {mode === "cagr" ? "CAGR" : "Total Return"}{" "}
                {lastPoint.value.toFixed(1)}%
              </span>
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}
