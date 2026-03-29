'use client';

import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./portfolio.module.css";

type MetricRow = {
  label: string;
  format?: (value: number | null) => string;
};

type YearRecord = {
  year: number;
  month: number;
  cagr: number | null;
  total_return: number | null;
  sharpe: number | null;
  drawdown: number | null;
};

type Props = {
  records: YearRecord[];
};

const defaultFormat = (value: number | null) => {
  if (value === null || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(1)}%`;
};

const metrics: MetricRow[] = [
  { label: "CAGR" },
  { label: "Total Return" },
  { label: "Sharpe Ratio", format: (v) => (v === null ? "—" : v.toFixed(2)) },
  {
    label: "Max Drawdown",
    format: (v) => (v === null ? "—" : `${v.toFixed(1)}%`),
  },
];

export function PerformanceScrollTable({ records }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [position, setPosition] = useState(0);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const update = () => {
      const maxScroll = el.scrollWidth - el.clientWidth;
      if (maxScroll <= 0) {
        setPosition(0);
        return;
      }
      setPosition(el.scrollLeft / maxScroll);
    };

    update();
    el.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);

    return () => {
      el.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, []);

  const sortedRecords = useMemo(
    () => [...records].sort((a, b) => b.year - a.year),
    [records],
  );

  return (
    <div className={styles.tableCard}>
      <div>
        <h3>Portfolio Performance</h3>
        <p className={styles.mutedCaption}>ขยับแถบเพื่อดูย้อนหลังหลายปี</p>
      </div>
      {sortedRecords.length === 0 ? (
        <div className={styles.emptyState}>
          ยังไม่มี checkpoint สำหรับแสดงผล
        </div>
      ) : (
        <>
          <div className={styles.tableScrollContainer} ref={containerRef}>
            <table className={styles.performanceTable}>
              <thead>
                <tr>
                  <th>Metric</th>
                  {sortedRecords.map((record) => (
                    <th key={record.year}>FY {record.year}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {metrics.map((metric) => (
                  <tr key={metric.label}>
                    <td>{metric.label}</td>
                    {sortedRecords.map((record) => {
                      const value =
                        metric.label === "CAGR"
                          ? record.cagr
                          : metric.label === "Total Return"
                            ? record.total_return
                            : metric.label === "Sharpe Ratio"
                              ? record.sharpe
                              : record.drawdown;
                      const formatter = metric.format ?? defaultFormat;
                      return <td key={`${record.year}-${metric.label}`}>{formatter(value)}</td>;
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className={styles.sliderTrack}>
            <div
              className={styles.sliderThumb}
              style={
                {
                  "--position": position,
                } as React.CSSProperties
              }
            />
          </div>
        </>
      )}
    </div>
  );
}
