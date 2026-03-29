"use client";

import { useMemo, useEffect, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  Cell,
  Customized,
  ReferenceLine,
  Treemap,
  LabelList,
} from "recharts";
import styles from "./stock.module.css";

type ChartDatum = {
  name: string;
  value: number;
};

type ChartDataset = {
  title: string;
  subtitle: string;
  periodLabel: string | null;
  periodType: string | null;
  data: ChartDatum[];
};

type RevenueBreakdownChartProps = {
  product?: ChartDataset | null;
  geo?: ChartDataset | null;
};

const formatCompact = (value: number) => {
  const abs = Math.abs(value);
  const withUnit = (num: number, unit: string, digits = 1) => {
    const formatted = num.toFixed(digits);
    const cleaned = formatted.endsWith(".0")
      ? formatted.slice(0, -2)
      : formatted;
    return `${cleaned} ${unit}`;
  };
  if (abs >= 1_000_000_000_000) {
    return withUnit(value / 1_000_000_000_000, "T");
  }
  if (abs >= 1_000_000_000) {
    return withUnit(value / 1_000_000_000, "B");
  }
  if (abs >= 1_000_000) {
    return withUnit(value / 1_000_000, "M");
  }
  if (abs >= 1_000) {
    return withUnit(value / 1_000, "K");
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
};

// Helper to format snake_case or messy names into Title Case
const formatName = (name: string) => {
  if (!name) return "";
  let spaced = name.replace(/[_-]/g, " ");
  spaced = spaced.replace(/\s*Revenue\s*/i, "");
  return spaced.replace(/\w\S*/g, (txt) => {
    return txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase();
  });
};

// --- Waterfall Chart Logic ---

const WATERFALL_COLORS = {
  positive: "#10B981", // Green-500 (increase)
  negative: "#EF4444", // Red-500 (decrease)
  total: "var(--text-primary, #0F172A)", // adapting total fill
};

const prepareWaterfallData = (dataset?: ChartDataset | null) => {
  if (!dataset || !dataset.data || dataset.data.length === 0) return null;

  const rawData = dataset.data.map((d) => ({ ...d, name: formatName(d.name) }));

  const businessUnits = rawData.filter(
    (d) => d.value >= 0 && !d.name.toLowerCase().includes("elimination"),
  );
  const eliminations = rawData.filter(
    (d) => d.value < 0 || d.name.toLowerCase().includes("elimination"),
  );

  businessUnits.sort((a, b) => b.value - a.value);

  const sortedData = [...businessUnits, ...eliminations];
  const finalTotal = sortedData.reduce((acc, curr) => acc + curr.value, 0);

  let currentSum = 0;
  const chartData = sortedData.map((item) => {
    const prevSum = currentSum;
    currentSum += item.value;

    const isNegative = item.value < 0;
    const placeholder = isNegative ? currentSum : prevSum;
    const barHeight = Math.abs(item.value);

    return {
      name: item.name,
      value: item.value,
      displayValue: barHeight,
      placeholder: placeholder,
      fill: isNegative ? WATERFALL_COLORS.negative : WATERFALL_COLORS.positive,
      isTotal: false,
      totalValue: finalTotal,
    };
  });

  chartData.push({
    name: "Total",
    value: currentSum,
    displayValue: currentSum,
    placeholder: 0,
    fill: WATERFALL_COLORS.total,
    isTotal: true,
    totalValue: finalTotal,
  });

  return {
    meta: dataset,
    chartData,
    total: currentSum,
  };
};

const WaterfallLabel = (props: any) => {
  const { x, y, width, height, value, payload, index, dataLength } = props;
  const formatted = formatCompact(Math.abs(value));
  const sign = value > 0 ? "+" : value < 0 ? "-" : "";
  const text = sign ? `${sign} ${formatted}` : `${formatted}`;

  const isTotalNode = dataLength ? index === dataLength - 1 : payload?.isTotal;
  const total = payload ? payload.totalValue : 0;
  const showPercent = value > 0 && total > 0 && !isTotalNode;

  // If bar is tall enough, put label inside; otherwise put above
  const isTall = height > 30;
  
  // The Total bar is rendered with "var(--text-primary, #ffffff)". We need the text inside it to contrast.
  // In light mode (#ffffff), text should be dark (#1e293b).
  // In dark mode (white text primary), text inside the white bar should be black.
  const fill = isTall 
    ? (isTotalNode ? "var(--background, #1e293b)" : "var(--bar-inside-text, #000)") 
    : "var(--text-primary, #1e293b)";

  if (showPercent) {
    const p = (value / total) * 100;
    const percentText = `(${p.toFixed(0)}%)`;

    // Adjust vertical position for two lines
    // If tall (inside): center ~ height/2.
    // If short (outside): above bar.
    const dyTitle = isTall ? height / 2 - 2 : -20;
    const dySub = 14;

    return (
      <text
        x={x + width / 2}
        y={y}
        textAnchor="middle"
        fontSize={12}
        fontWeight="bold"
        style={{ fill }}
      >
        <tspan x={x + width / 2} dy={dyTitle}>
          {text}
        </tspan>
        <tspan
          x={x + width / 2}
          dy={dySub}
          fontSize={10}
          fontWeight="normal"
        >
          {percentText}
        </tspan>
      </text>
    );
  }

  const dy = isTall ? height / 2 + 4 : -8;

  return (
    <text
      x={x + width / 2}
      y={y}
      dy={dy}
      textAnchor="middle"
      fontSize={12}
      fontWeight="bold"
      style={{ fill }}
      stroke="var(--background, #fff)"
      strokeWidth={isTall ? 0 : 2}
      paintOrder="stroke fill"
    >
      {text}
    </text>
  );
};

// Custom tooltip for waterfall to show `Name : 298.2 B` and negative as `- 4.4 B`
const WaterfallTooltip = (props: any) => {
  const { active, payload, label } = props;
  if (!active || !payload || payload.length === 0) return null;

  const entry =
    payload.find((p: any) => p.dataKey === "displayValue") || payload[0];
  if (!entry || !entry.payload) return null;

  const name = label;
  const rawValue = entry.payload.value;
  const total = entry.payload.totalValue;
  const isNegative = rawValue < 0;

  let valueStr = isNegative
    ? `- ${formatCompact(Math.abs(rawValue))}`
    : `${formatCompact(rawValue)}`;

  if (rawValue > 0 && total > 0 && !entry.payload.isTotal) {
    const p = (rawValue / total) * 100;
    valueStr += ` (${p.toFixed(0)}%)`;
  }

  return (
    <div
      style={{
        background: "var(--card-bg, #fff)",
        padding: 8,
        border: "1px solid var(--border-color, #e6eef8)",
        borderRadius: 6,
      }}
    >
      <div
        style={{ fontWeight: 700, color: "var(--text-primary, #0f2748)" }}
      >{`${name} : ${valueStr}`}</div>
    </div>
  );
};

// Draw connectors between waterfall bars (dashed horizontal between tops)
const WaterfallChart = ({ dataset }: { dataset: ChartDataset }) => {
  const payload = useMemo(() => prepareWaterfallData(dataset), [dataset]);

  // Calculate the angle based on the longest product name
  const xAxisAngle = useMemo(() => {
    if (!payload) return -45;

    const maxNameLength = payload.chartData.reduce((max, item) => {
      return Math.max(max, item.name.length);
    }, 0);

    return maxNameLength <= 20 ? 0 : -45;
  }, [payload]);

  // Draw bridges after chart renders
  useEffect(() => {
    // Small delay to ensure chart is fully rendered
    const timer = setTimeout(() => {
      try {
        // Get all bar rectangles from all BarCharts on the page
        document.querySelectorAll("svg").forEach((svg) => {
          // Check if this SVG likely contains our waterfall chart
          const rects = svg.querySelectorAll("rect");
          if (rects.length < 5) return; // Skip if too few rectangles

          // Find or create the lines group
          let linesGroup = svg.querySelector("#bridge-lines");
          if (!linesGroup) {
            linesGroup = document.createElementNS(
              "http://www.w3.org/2000/svg",
              "g",
            );
            linesGroup.setAttribute("id", "bridge-lines");
            svg.appendChild(linesGroup);
          }

          linesGroup.innerHTML = ""; // Clear previous lines

          // Get all colored (non-transparent) rectangles
          const bars: Array<{
            x: number;
            y: number;
            width: number;
            height: number;
          }> = [];

          rects.forEach((rect) => {
            const fill = rect.getAttribute("fill");
            const x = parseFloat(rect.getAttribute("x") || "NaN");
            const y = parseFloat(rect.getAttribute("y") || "NaN");
            const width = parseFloat(rect.getAttribute("width") || "NaN");
            const height = parseFloat(rect.getAttribute("height") || "NaN");

            // Only include actual bars (colored, not tiny, valid coordinates)
            if (
              fill &&
              fill !== "none" &&
              fill !== "transparent" &&
              !isNaN(x) &&
              !isNaN(y) &&
              !isNaN(width) &&
              !isNaN(height) &&
              width > 0 &&
              height > 2
            ) {
              bars.push({ x, y, width, height });
            }
          });

          // Sort bars by x position to ensure correct order
          bars.sort((a, b) => a.x - b.x);

          // Draw lines connecting bar tops
          for (let i = 0; i < bars.length - 1; i++) {
            const bar1 = bars[i];
            const bar2 = bars[i + 1];

            // Calculate the top center of each bar
            const x1 = bar1.x + bar1.width / 2;
            const y1 = bar1.y;
            const x2 = bar2.x + bar2.width / 2;
            const y2 = bar2.y;

            // Only draw if bars are at different Y positions (to skip stacked bars)
            if (Math.abs(y1 - y2) > 1) {
              const line = document.createElementNS(
                "http://www.w3.org/2000/svg",
                "line",
              );
              line.setAttribute("x1", String(x1));
              line.setAttribute("y1", String(y1));
              line.setAttribute("x2", String(x2));
              line.setAttribute("y2", String(y2));
              line.setAttribute("stroke", "#1f3a63");
              line.setAttribute("stroke-width", "2.5");
              line.setAttribute("stroke-dasharray", "5 5");
              line.setAttribute("opacity", "0.85");
              line.setAttribute("pointer-events", "none");
              linesGroup.appendChild(line);
            }
          }
        });
      } catch (err) {
        console.error("Error drawing bridges:", err);
      }
    }, 400);

    return () => clearTimeout(timer);
  }, [payload]);

  if (!payload) return null;

  return (
    <div className={styles.chartCard} style={{ gridColumn: "span 1" }}>
      <div className={styles.chartHeader}>
        <h4 className={styles.chartTitle}>{payload.meta.title}</h4>
        <span className={styles.chartPeriod}>
          {payload.meta.periodLabel
            ? `Period ${payload.meta.periodLabel}`
            : "Period —"}
        </span>
      </div>
      <div className={styles.chartInner} style={{ display: "flex", flexDirection: "column" }}>
        <div style={{ overflowX: "auto", overflowY: "hidden", paddingBottom: "8px", width: "100%", flex: 1, minHeight: 0 }}>
          <div style={{ minWidth: "100%", width: "max(100%, 500px)", height: "100%" }}>
            <ResponsiveContainer width="100%" height="100%" minWidth={450}>
              <BarChart
            data={payload.chartData}
            margin={{ top: 50, right: 30, left: 20, bottom: 60 }}
          >
            <CartesianGrid
              strokeDasharray="3 3"
              vertical={false}
              opacity={0.5}
            />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 13, fontWeight: 600, fill: "var(--text-secondary, #64748b)" }}
              interval={0}
              angle={xAxisAngle}
              textAnchor={xAxisAngle === 0 ? "middle" : "end"}
              height={xAxisAngle === 0 ? 40 : 80}
            />
            <YAxis
              tickFormatter={(val) => formatCompact(val)}
              tick={{ fontSize: 11, fill: "var(--text-secondary, #64748b)" }}
            />
            <RechartsTooltip
              cursor={{ fill: "rgba(148, 163, 184, 0.12)" }}
              content={WaterfallTooltip}
              wrapperStyle={{ zIndex: 50 }}
              position={{ y: 0 }}
            />
            <ReferenceLine y={0} stroke="#94A3B8" />

            <Bar
              dataKey="placeholder"
              stackId="waterfall"
              fill="transparent"
              isAnimationActive={false}
              shape={() => <g />}
            />
            <Bar
              dataKey="displayValue"
              stackId="waterfall"
              radius={[0, 0, 0, 0]}
              name="Revenue"
            >
              {payload.chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.fill} />
              ))}
              <LabelList dataKey="value" content={(props: any) => <WaterfallLabel {...props} dataLength={payload.chartData.length} />} />
            </Bar>
          </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      <div className={styles.chartFooter}>
        <span style={{ fontWeight: "bold", color: "var(--text-secondary, #64748b)" }}>
          Total {formatCompact(payload?.total || 0)}
        </span>
      </div>
    </div>
  );
};

// --- Treemap Logic ---

const TREEMAP_COLORS_LIGHT = [
  "#1e3a8a", // Blue-900 (Highest)
  "#1e40af", // Blue-800
  "#1d4ed8", // Blue-700
  "#2563eb", // Blue-600
  "#3b82f6", // Blue-500
  "#60a5fa", // Blue-400
  "#93c5fd", // Blue-300 (Lowest)
];

const TREEMAP_COLORS_DARK = [
  "#172554", // Blue-950 (Highest)
  "#1e3a8a", // Blue-900
  "#1e40af", // Blue-800
  "#1d4ed8", // Blue-700
  "#2563eb", // Blue-600
  "#3b82f6", // Blue-500
  "#60a5fa", // Blue-400 (Lowest)
];

const prepareTreemapData = (dataset?: ChartDataset | null, isDark = false) => {
  if (!dataset || !dataset.data || dataset.data.length === 0) return null;

  const colors = isDark ? TREEMAP_COLORS_DARK : TREEMAP_COLORS_LIGHT;

  const sorted = [...dataset.data]
    .map((d) => ({ name: formatName(d.name), value: d.value }))
    .sort((a, b) => b.value - a.value);

  const TOP_N = 12;
  let finalData = sorted;

  if (sorted.length > TOP_N) {
    const top = sorted.slice(0, TOP_N);
    const others = sorted.slice(TOP_N);
    const othersSum = others.reduce((sum, item) => sum + item.value, 0);

    finalData = [...top, { name: "Others", value: othersSum }];
  }

  const totalValue = finalData.reduce((sum, item) => sum + item.value, 0);

  const chartData = finalData.map((item, index) => {
    const colorIndex = Math.min(
      Math.floor((index / finalData.length) * colors.length),
      colors.length - 1,
    );
    // Always white text — tiles are dark enough in both modes
    const textColor = "#ffffff";

    return {
      ...item,
      fill: colors[colorIndex],
      textColor,
      percent: (item.value / totalValue) * 100,
    };
  });

  return {
    meta: dataset,
    chartData,
    total: totalValue,
  };
};

const CustomTreemapContent = (props: any) => {
  const {
    root,
    x,
    y,
    width,
    height,
    index,
    payload,
    name,
    value,
  } = props;

  // Get text color from payload
  const textColor = payload && payload.textColor ? payload.textColor : "#fff";

  // Calculate percentage
  let percentValue = 0;
  if (root && root.value) {
    percentValue = (value / root.value) * 100;
  } else if (payload && typeof payload.percent === "number") {
    percentValue = payload.percent;
  }

  const percentStr = percentValue > 0 ? `${percentValue.toFixed(1)}%` : "0%";
  const valueStr = formatCompact(value);
  const statsStr = `${valueStr} (${percentStr})`;

  // Determine layout based on available space
  const showTwoLines = width > 50 && height > 45;
  const showOneLine = !showTwoLines && width > 40 && height > 20;

  // Smart truncation
  const truncateName = (text: string, maxWidth: number, fontSize: number): string => {
    const estimatedCharWidth = fontSize * 0.55;
    const availableWidth = maxWidth * 0.9;
    const maxChars = Math.floor(availableWidth / estimatedCharWidth);
    if (maxChars < 3) return "…";
    if (text.length > maxChars) return text.slice(0, Math.max(3, maxChars - 1)) + "…";
    return text;
  };

  const nameForDisplay = truncateName(name, width, 20);
  const statsForDisplay = truncateName(statsStr, width, 14);

  return (
    <g>
      <rect
        x={x}
        y={y}
        rx={6}
        ry={6}
        width={width}
        height={height}
        style={{
          fill: props.fill || "#2563eb",
          stroke: "var(--background, #fff)",
          strokeWidth: 2.5,
          strokeOpacity: 1,
        }}
      />
      {(showTwoLines || showOneLine) && (
        <foreignObject x={x} y={y} width={width} height={height}>
          <div
            style={{
              width: "100%",
              height: "100%",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "4px",
              boxSizing: "border-box",
              pointerEvents: "none",
              overflow: "hidden",
            }}
          >
            {showTwoLines ? (
              <>
                <div
                  style={{
                    color: textColor,
                    fontSize: "20px",
                    fontWeight: 600,
                    fontFamily: "'Segoe UI', Helvetica, Arial, sans-serif",
                    textAlign: "center",
                    lineHeight: 1.2,
                    whiteSpace: "nowrap",
                  }}
                >
                  {nameForDisplay}
                </div>
                <div
                  style={{
                    color: textColor,
                    fontSize: "14px",
                    fontWeight: 400,
                    fontFamily: "'Segoe UI', Helvetica, Arial, sans-serif",
                    textAlign: "center",
                    lineHeight: 1.3,
                    whiteSpace: "nowrap",
                    opacity: 0.9,
                  }}
                >
                  {statsForDisplay}
                </div>
              </>
            ) : (
              <div
                style={{
                  color: textColor,
                  fontSize: "12px",
                  fontWeight: 500,
                  fontFamily: "'Segoe UI', Helvetica, Arial, sans-serif",
                  textAlign: "center",
                  whiteSpace: "nowrap",
                }}
              >
                {truncateName(name, width, 12).slice(0, 8)}
              </div>
            )}
          </div>
        </foreignObject>
      )}
    </g>
  );
};

// Treemap tooltip that shows name, value and percent
const TreemapTooltip = (props: any) => {
  const { active, payload } = props;
  if (!active || !payload || payload.length === 0) return null;
  const node = payload[0].payload;
  if (!node) return null;
  const name = node.name;
  const value = node.value;
  const percent = typeof node.percent === "number" ? node.percent : null;
  const tooltipText = `${name} : ${formatCompact(value)}${percent !== null ? ` (${percent.toFixed(1)}%)` : ""}`;

  return (
    <div
      style={{
        background: "var(--card-bg, #fff)",
        padding: "8px 12px",
        borderRadius: 8,
        border: "1px solid var(--border-color, #e6eef8)",
      }}
    >
      <div style={{ fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>{tooltipText}</div>
    </div>
  );
};

const TreemapChart = ({ dataset }: { dataset: ChartDataset }) => {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    // Detect dark mode from document
    const checkDark = () => {
      const html = document.documentElement;
      setIsDark(
        html.classList.contains("dark") ||
        html.getAttribute("data-theme") === "dark"
      );
    };
    checkDark();

    // Observe changes to class/attribute on <html>
    const observer = new MutationObserver(checkDark);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class", "data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  const payload = useMemo(() => prepareTreemapData(dataset, isDark), [dataset, isDark]);

  if (!payload) return null;

  return (
    <div className={styles.chartCard} style={{ gridColumn: "span 1" }}>
      <div className={styles.chartHeader}>
        <h4 className={styles.chartTitle}>{payload.meta.title}</h4>
        <span className={styles.chartPeriod}>
          {payload.meta.periodLabel
            ? `Period ${payload.meta.periodLabel}`
            : "Period —"}
        </span>
      </div>
      <div className={`${styles.chartInner} ${styles.treemapWrap}`}>
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={payload.chartData}
            dataKey="value"
            aspectRatio={4 / 3}
            stroke="var(--background, #fff)"
            fill="#8884d8"
            content={<CustomTreemapContent />}
          >
            <RechartsTooltip
              content={TreemapTooltip}
              wrapperStyle={{ zIndex: 50 }}
            />
          </Treemap>
        </ResponsiveContainer>
      </div>
      <div className={styles.chartFooter}>
        <span style={{ fontWeight: "bold", color: "var(--text-secondary, #64748b)" }}>
          Total {formatCompact(payload.total)}
        </span>
      </div>
    </div>
  );
};

// --- Main Export ---

export default function RevenueBreakdownChart({
  product,
  geo,
}: RevenueBreakdownChartProps) {
  if (!product && !geo) return null;

  let showProduct = !!product;
  let showGeo = !!geo;

  if (product && geo) {
    const productTotal = product.data?.reduce((sum, item) => sum + item.value, 0) || 0;
    const geoTotal = geo.data?.reduce((sum, item) => sum + item.value, 0) || 0;
    
    // Check if both totals are greater than 0
    if (productTotal > 0 && geoTotal > 0) {
      const maxTotal = Math.max(productTotal, geoTotal);
      const diff = Math.abs(productTotal - geoTotal);

      // If difference is more than 50% of the max total
      if (diff > maxTotal * 0.5) {
        if (productTotal < geoTotal) {
          showProduct = false;
        } else {
          showGeo = false;
        }
      }
    }
  }

  if (!showProduct && !showGeo) return null;

  return (
    <div className={styles.revenueCharts}>
      {showProduct && product && <WaterfallChart dataset={product} />}
      {showGeo && geo && <TreemapChart dataset={geo} />}
    </div>
  );
}
