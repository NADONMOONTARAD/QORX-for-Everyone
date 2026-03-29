"use client";

import React, { useMemo, useState, useRef } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  Cell,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ReferenceLine,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatPercentFromRatio } from "./valuation-formatters";
import { LottieIcon } from "@/components/LottieIcon";
import { NAVTooltip } from "./NAVTooltip";
import questionAnimation from "@/assets/lottie/icons8-info.json";

import styles from "./ValuationInputsPanel.module.css";

type DiscountRateAdjustment = {
  code?: string;
  label?: string;
  delta?: number | null;
  type?: string;
  reason?: string | null;
};

type DiscountRateInsight = {
  base_rate?: number | null;
  final_rate?: number | null;
  adjustments?: DiscountRateAdjustment[] | null;
  explanation?: string | null;
};

type GrowthAssumption = {
  initial_growth?: number | null;
  terminal_growth?: number | null;
  method?: string | null;
  window_years?: number | null;
  source_metric?: string | null;
  justification?: string | null;
  discount_rate?: number | null;
};

type ValuationProjectionRow = {
  year_index?: number | null;
  growth_rate?: number | null;
  projected_fcf?: number | null;
  projected_fcfe?: number | null;
  projected_owner_earnings?: number | null;
  normalized_delta_wc?: number | null;
  future_revenue?: number | null;
  discount_factor?: number | null;
  discounted_fcf?: number | null;
  discounted_fcfe?: number | null;
};

type ValuationIntrinsicSummary = {
  equity_value_total?: number | null;
  intrinsic_value_per_share?: number | null;
  shares_outstanding?: number | null;
  margin_of_safety?: number | null;
  current_price?: number | null;
};

type ValuationModelDetail = {
  model_label?: string;
  model_type?: string | null;
  base_metric?: string | null;
  discount_rate?: number | null;
  projection_years?: number | null;
  growth_metric_source?: string | null;
  growth_metric_key?: string | null;
  inputs?: Record<string, unknown> | null;
  projections?: ValuationProjectionRow[] | null;
  fcf_history?: Array<{
    year: number | string;
    value: number;
    growth?: number;
    is_estimate?: boolean;
    note?: string;
  }> | null;
  terminal_value?: Record<string, unknown> | null;
  intrinsic_value?: ValuationIntrinsicSummary | null;
  discounted_fcf_sum?: number | null;
  cyclical_tier?: string | null;
  cyclical_premium?: number | null;
  adjusted_discount_rate?: number | null;
  note?: string | null;
  growth_curve?: number[] | null;
  initial_growth_original?: number | null;
  first_year_growth_applied?: number | null;
  growth_step_per_year?: number | null;
  avg_line_value?: number | null;
  implied_growth?: number | null;
};

type ValuationInputsPanelProps = {
  discountInfo: DiscountRateInsight | null;
  discountExplanation: string;
  adjustments: DiscountRateAdjustment[];
  discountReasons: string[];
  growthEntries: [string, GrowthAssumption][];
  modelEntries: [string, ValuationModelDetail][];
  modelUsedKey: string | null;
};

const HoverLottieIcon = ({ animationData, className, width = 22, height = 22, style }: { animationData: any, className?: string, width?: number, height?: number, style?: React.CSSProperties }) => {
  const [play, setPlay] = useState(false);
  return (
    <span 
      className={className} 
      style={{ display: 'inline-flex', width, height, cursor: 'pointer', ...style }}
      onMouseEnter={() => setPlay(true)}
      onMouseLeave={() => setPlay(false)}
    >
      <LottieIcon animationData={animationData} loop={false} play={play} />
    </span>
  );
};

const DCFInfoTooltip = ({ detail }: { detail: ValuationModelDetail | null }) => {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({ top: -9999, left: -9999 });

  const showTooltip = () => {
    if (!wrapperRef.current || !tooltipRef.current) return;
    const anchor = wrapperRef.current.getBoundingClientRect();
    const tipW = tooltipRef.current.offsetWidth || 300;
    const tipH = tooltipRef.current.offsetHeight || 120;
    const GAP = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let top = anchor.bottom + GAP;
    let left = anchor.left;

    if (top + tipH > vh - GAP) top = anchor.top - tipH - GAP;
    if (left + tipW > vw - GAP) left = vw - tipW - GAP;
    if (left < GAP) left = GAP;
    if (top < GAP) top = GAP;

    setTooltipStyle({ top, left });
    setVisible(true);
  };

  const hideTooltip = () => setVisible(false);

  if (!detail) return null;

  const title = detail.model_label || "Discounted Cash Flow (DCF)";
  
  // Parse note logic (e.g. "Base: Avg (5 yrs) (incl. TTM). Growth (MEDIAN_5Y): 8.3%. Capped at 15%.")
  const rawNote = detail.note || "ใช้สูตร baseline ของ public edition";
  let baseLogic = "อิงตามค่าที่เหมาะสมในปัจจุบัน";
  let growthLogic = "อิงตามอัตราอุตสาหกรรม";
  
  // Try to cleanly split the backend note into Base and Growth components if possible
  if (rawNote.includes("Base:") && rawNote.includes("Growth")) {
      const parts = rawNote.split(". Growth");
      baseLogic = parts[0].replace("Base:", "").trim();
      // Scrub colons and percentages (e.g., ": 6.3%." -> "") for backward compatibility
      growthLogic = ("Growth" + parts[1])
        .replace(/:\s*[-+]?[\d.]+%?\.?/g, "")
        .replace(/\s*\(?Capped\)?/gi, "") // Also remove cap notes if they have numbers in them coming from backend
        .trim();
  } else {
      baseLogic = rawNote; // Fallback
  }

  return (
    <span
      ref={wrapperRef}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onClick={() => setVisible(!visible)}
      style={{ position: "relative", display: "inline-flex", alignItems: "center", marginLeft: "8px", cursor: "pointer" }}
    >
      <HoverLottieIcon animationData={questionAnimation} width={22} height={22} style={{ filter: "var(--icon-filter, none)" }} />
      <div
        ref={tooltipRef}
        data-visible={visible ? "true" : "false"}
        style={{
          ...tooltipStyle,
          position: "fixed",
          zIndex: 9999,
          minWidth: '320px',
          maxWidth: '400px',
          padding: '20px',
          textAlign: 'left',
          lineHeight: '1.6',
          cursor: 'default',
          backgroundColor: 'var(--card-bg, #ffffff)',
          border: '1px solid var(--border-color, #e2e8f0)',
          borderRadius: '12px',
          boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
          pointerEvents: visible ? 'auto' : 'none',
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateY(0)' : 'translateY(5px)',
          transition: 'all 0.2s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px', borderBottom: '1px solid var(--border-color, #e2e8f0)', paddingBottom: '10px' }}>
            <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary, #0f172a)' }}>
                วิธีการประเมินมูลค่า (Public Edition)
            </div>
        </div>

        <div style={{ fontSize: '13px', color: 'var(--text-secondary, #475569)', marginBottom: '16px' }}>
            หน้า public ใช้ <strong>baseline valuation logic</strong> แบบโปร่งใสสำหรับการเรียนและการรีวิวโค้ด โดยตั้งใจไม่แสดง heuristic ภายในทั้งหมดของเวอร์ชัน private
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ background: 'var(--background, #f8fafc)', padding: '12px', borderRadius: '8px', borderLeft: '3px solid var(--chart-orange, #ea580c)' }}>
                <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600, color: 'var(--text-muted, #64748b)', marginBottom: '2px' }}>
                    DCF Base (จุดเริ่มต้น)
                </div>
                <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary, #1e293b)' }}>
                    {baseLogic}
                </div>
            </div>

            <div style={{ background: 'var(--background, #f8fafc)', padding: '12px', borderRadius: '8px', borderLeft: '3px solid var(--chart-growth, #10b981)' }}>
                <div style={{ fontSize: '11px', textTransform: 'uppercase', fontWeight: 600, color: 'var(--text-muted, #64748b)', marginBottom: '2px' }}>
                    Growth Rate (อัตราเติบโต)
                </div>
                <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-primary, #1e293b)' }}>
                    {growthLogic}
                </div>
            </div>
        </div>
      </div>
    </span>
  );
};

const formatPercentForChart = (value: number | null | undefined) => {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return null;
  }
  return value * 100;
};

const growthSourceLabelMap: Record<string, string> = {
  owner_earnings: "Owner Earnings",
  owner_earnings_growth: "Owner Earnings",
  net_income: "Net Income",
  net_income_growth: "Net Income",
  fcf: "Free Cash Flow",
  fcf_growth: "Free Cash Flow",
  free_cash_flow: "Free Cash Flow",
  affo: "AFFO",
  affo_growth: "AFFO",
  revenue: "Revenue",
  revenue_growth: "Revenue",
  book_value_per_share: "Book Value per Share",
  book_value_per_share_growth: "Book Value per Share",
};

const formatGrowthSourceLabel = (rawValue: string | null | undefined) => {
  if (typeof rawValue !== "string") {
    return null;
  }
  const normalized = rawValue.trim().toLowerCase();
  if (!normalized) {
    return null;
  }
  if (growthSourceLabelMap[normalized]) {
    return growthSourceLabelMap[normalized];
  }
  const sanitized = normalized.replace(/_?growth$/i, "");
  const tokens = sanitized.split(/[_\s]+/).filter((token) => token.length > 0);
  if (tokens.length === 0) {
    return null;
  }
  return tokens
    .map((token) => token.charAt(0).toUpperCase() + token.slice(1))
    .join(" ");
};

const interpretGrowthMethod = (
  value: string | null | undefined,
): "linear" | "exponential" | null => {
  if (!value) return null;
  const normalized = value.toLowerCase();
  if (/(exp|เอ็กซ์โป|exponential)/.test(normalized)) {
    return "exponential";
  }
  if (/(lin|เชิงเส้น|linear)/.test(normalized)) {
    return "linear";
  }
  if (/(curve|smooth|decay)/.test(normalized)) {
    return "exponential";
  }
  return null;
};

const detectFadeKindFromCurve = (
  curve: Array<number | null | undefined>,
): "linear" | "exponential" | null => {
  const points = curve
    .map((value) =>
      typeof value === "number" && Number.isFinite(value) ? value : null,
    )
    .filter((value): value is number => value !== null);
  if (points.length < 4) {
    return null;
  }
  const diffs: number[] = [];
  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1];
    const current = points[index];
    diffs.push(prev - current);
  }
  if (!diffs.some((value) => Math.abs(value) > 1e-6)) {
    return null;
  }
  const meanDiff =
    diffs.reduce((total, value) => total + value, 0) / diffs.length;
  if (Math.abs(meanDiff) < 1e-6) {
    return null;
  }
  const variance =
    diffs.reduce((total, value) => total + (value - meanDiff) ** 2, 0) /
    diffs.length;
  const normalizedVariance = variance / (meanDiff ** 2 + 1e-9);
  return normalizedVariance < 0.2 ? "linear" : "exponential";
};

interface XAxisConfig {
  angle: number;
  textAnchor: "start" | "middle" | "end";
  bottomMargin: number;
}

const detectXAxisCrowding = (
  data: Array<{ year?: string | number }>,
): XAxisConfig => {
  if (!Array.isArray(data) || data.length === 0) {
    return { angle: 0, textAnchor: "middle", bottomMargin: 55 };
  }

  // Convert all year values to strings and get their lengths
  const labels = data
    .map((item) => String(item.year ?? "").trim())
    .filter((label) => label.length > 0);

  if (labels.length === 0) {
    return { angle: 0, textAnchor: "middle", bottomMargin: 55 };
  }

  const maxLabelLength = Math.max(...labels.map((label) => label.length));
  const avgLabelLength =
    labels.reduce((sum, label) => sum + label.length, 0) / labels.length;

  // Crowding logic: rotate when labels are crowded with multiple items OR very long labels
  const isCrowded =
    labels.length >= 9 || // Many data points (≥9 labels)
    maxLabelLength > 14 || // Very long single label
    (labels.length >= 7 && avgLabelLength > 12); // Multiple items with long avg length

  if (isCrowded) {
    return { angle: -45, textAnchor: "end", bottomMargin: 75 };
  }

  return { angle: 0, textAnchor: "middle", bottomMargin: 55 };
};

const detectNumericAxisConfig = (): XAxisConfig => {
  return { angle: 0, textAnchor: "middle", bottomMargin: 45 };
};

const CustomXAxisTick = (props: {
  x?: number;
  y?: number;
  payload?: { value: string | number };
  angle?: number;
  textAnchor?: "start" | "middle" | "end";
}) => {
  const { x = 0, y = 0, payload, angle = 0, textAnchor = "middle" } = props;

  if (angle === 0) {
    return (
      <text
        x={x}
        y={y}
        fill="var(--text-primary, #5b6a86)"
        fontSize="12"
        textAnchor={textAnchor}
        dy="0.5em"
      >
        {payload?.value}
      </text>
    );
  }

  return (
    <g transform={`translate(${x},${y})`}>
      <text
        x={0}
        y={0}
        fill="var(--text-primary, #5b6a86)"
        fontSize="12"
        textAnchor={textAnchor}
        transform={`rotate(${angle})`}
        dy={4}
      >
        {payload?.value}
      </text>
    </g>
  );
};

export function ValuationInputsPanel(props: ValuationInputsPanelProps) {
  const {
    discountInfo,
    discountExplanation: _discountExplanation,
    adjustments,
    discountReasons,
    growthEntries,
    modelEntries,
    modelUsedKey,
  } = props;
  void _discountExplanation;
  const discountReasonEntries = discountReasons
    .map((reason) => (typeof reason === "string" ? reason.trim() : ""))
    .filter((reason) => reason.length > 0);

  const activeEntry = useMemo(() => {
    if (modelEntries.length === 0) {
      return null;
    }
    if (modelUsedKey) {
      const matched = modelEntries.find(
        ([label]) => label.toLowerCase() === modelUsedKey.toLowerCase(),
      );
      if (matched) {
        return matched;
      }
    }
    return modelEntries[0];
  }, [modelEntries, modelUsedKey]);

  const activeLabel = activeEntry?.[0] ?? null;
  const activeDetail = activeEntry?.[1] ?? null;

  const rawInputs = useMemo(
    () => (activeDetail?.inputs ?? {}) as Record<string, unknown>,
    [activeDetail],
  );

  const valueFromInputs = (key: string): number | null => {
    const value = rawInputs[key];
    return typeof value === "number" ? value : null;
  };

  const textFromInputs = (key: string): string | null => {
    const value = rawInputs[key];
    return typeof value === "string" ? value : null;
  };

  const growthCurve = useMemo(
    () =>
      Array.isArray(activeDetail?.growth_curve)
        ? (activeDetail?.growth_curve as number[])
        : [],
    [activeDetail],
  );

  const initialGrowthOriginal =
    typeof activeDetail?.initial_growth_original === "number"
      ? activeDetail.initial_growth_original
      : (valueFromInputs("initial_growth_original") ??
        (growthCurve.length > 0 ? growthCurve[0] : null));

  const firstYearGrowth =
    typeof activeDetail?.first_year_growth_applied === "number"
      ? activeDetail.first_year_growth_applied
      : (valueFromInputs("first_year_growth") ??
        (growthCurve.length > 0 ? growthCurve[0] : null));

  const rawGrowthStep =
    typeof activeDetail?.growth_step_per_year === "number"
      ? activeDetail.growth_step_per_year
      : valueFromInputs("growth_step_per_year");

  const terminalGrowthRate =
    valueFromInputs("terminal_growth_rate") ??
    (growthCurve.length > 0 ? growthCurve[growthCurve.length - 1] : null);

  const inferredGrowthStep =
    rawGrowthStep ??
    (() => {
      const first = initialGrowthOriginal ?? growthCurve[0];
      const last =
        growthCurve.length > 0 ? growthCurve[growthCurve.length - 1] : null;
      if (
        typeof first === "number" &&
        typeof last === "number" &&
        activeDetail?.projection_years &&
        activeDetail.projection_years > 0
      ) {
        return (first - last) / activeDetail.projection_years;
      }
      return null;
    })();

  const fcfHistoryData = useMemo(() => {
    const raw = Array.isArray(activeDetail?.fcf_history)
      ? activeDetail.fcf_history
      : [];

    const baseIndex = raw.findIndex((item) => item.year === "DCF Base");
    const baseItem = baseIndex !== -1 ? raw[baseIndex] : null;
    const baseValue = baseItem ? baseItem.value : null;
    const impliedGrowth = activeDetail?.implied_growth ?? null;

    let explosionDetected = false;
    // Check for "Y-Axis Explosion"
    if (baseValue !== null && impliedGrowth !== null && baseIndex !== -1) {
      const lastIndex = raw.length - 1;
      const lastItem = raw[lastIndex];
      const yearsOut = lastIndex - baseIndex;
      if (
        yearsOut > 0 &&
        (lastItem as any).is_projection &&
        lastItem.value > 0
      ) {
        const projectedVal = lastItem.value;
        const marketVal = baseValue * Math.pow(1 + impliedGrowth, yearsOut);
        // If Market Expectation is > 2.5x the Projected Value, we clamp
        if (marketVal > 2.5 * projectedVal) {
          explosionDetected = true;
        }
      }
    }

    return raw.map((item, index) => {
      const isProjection = (item as any).is_projection;
      let marketValue = null;

      if (
        baseValue !== null &&
        impliedGrowth !== null &&
        index > baseIndex &&
        isProjection
      ) {
        const yearsPassed = index - baseIndex;
        // Ghost bars only for Year 1-5, and if exploded, only up to Year 3
        if (
          yearsPassed <= 5 &&
          (!explosionDetected || yearsPassed <= 3)
        ) {
          marketValue = baseValue * Math.pow(1 + impliedGrowth, yearsPassed);
        }
      }

      let originalGrowthPct = typeof item.growth === "number" ? item.growth * 100 : null;
      let growthPct = originalGrowthPct;
      let isCapped = false;
      
      // Cap at +300% and -100% to avoid crushing the chart scale
      if (growthPct !== null) {
        if (growthPct > 300) {
          growthPct = 300;
          isCapped = true;
        } else if (growthPct < -100) {
          growthPct = -100;
          isCapped = true;
        }
      }

      return {
        ...item,
        year: String(item.year).replace(/^A\(/, "Avg ("),
        growthPct,
        originalGrowthPct,
        isGrowthCapped: isCapped,
        marketValue,
      };
    }).filter(d => {
      // Keep if it has a valid numeric value other than 0
      if (typeof d.value === 'number' && d.value !== 0) return true;
      // Keep if it's the anchor (DCF Base) or a Projection
      if (d.year === "DCF Base") return true;
      if (String(d.year).includes("Year ")) return true;
      // Otherwise skip if no data
      return false;
    });
  }, [activeDetail]);

  const fcfHistoryXAxisConfig = useMemo(
    () => detectXAxisCrowding(fcfHistoryData),
    [fcfHistoryData],
  );

  const chartDomains = useMemo(() => {
    if (!fcfHistoryData || fcfHistoryData.length === 0) {
      return { 
        leftDomain: [0, (dataMax: number) => dataMax * 1.15] as any, 
        rightDomain: ["auto", "auto"] as any 
      };
    }

    let minVal = 0;
    let maxVal = 0;
    let minPct = 0;
    let maxPct = 0;

    fcfHistoryData.forEach((d) => {
      if (typeof d.value === "number") {
        minVal = Math.min(minVal, d.value);
        maxVal = Math.max(maxVal, d.value);
      }
      if (typeof d.marketValue === "number") {
        minVal = Math.min(minVal, d.marketValue);
        maxVal = Math.max(maxVal, d.marketValue);
      }
      if (typeof d.growthPct === "number") {
        minPct = Math.min(minPct, d.growthPct);
        maxPct = Math.max(maxPct, d.growthPct);
      }
    });

    if (maxVal <= 0) maxVal = 1;
    if (maxPct <= 0) maxPct = 1;

    // Apply baseline padding of 15%
    maxVal *= 1.15;
    maxPct *= 1.15;
    minVal = minVal < 0 ? minVal * 1.15 : minVal;
    minPct = minPct < 0 ? minPct * 1.15 : minPct;

    const valRatio = minVal / maxVal;
    const pctRatio = minPct / maxPct;
    
    // Calculate the most extreme negative ratio needed
    let targetRatio = Math.min(valRatio, pctRatio, 0);

    // If there is an extreme outlier (like a single massive dip), clamping the ratio prevents crushing the rest of the chart
    // We cap the maximum negative space to be no more than 1.5x the positive max space (-1.5)
    targetRatio = Math.max(targetRatio, -1.5);

    // Now recalculate the minimums bound to this target ratio
    const finalMinVal = Math.min(minVal, targetRatio * maxVal);
    const finalMinPct = Math.min(minPct, targetRatio * maxPct);

    return {
      leftDomain: [finalMinVal, maxVal],
      rightDomain: [finalMinPct, maxPct],
    };
  }, [fcfHistoryData]);

  const avgLineValue = activeDetail?.avg_line_value;

  const growthFadeData = useMemo(() => {
    const points: Array<{ year: number; growth: number }> = [];
    const first = formatPercentForChart(initialGrowthOriginal);
    if (first !== null) {
      points.push({ year: 0, growth: first });
    }
    growthCurve.forEach((value, index) => {
      const converted = formatPercentForChart(value);
      if (converted !== null) {
        points.push({ year: index + 1, growth: converted });
      }
    });
    if (points.length === 0) {
      const fallback = formatPercentForChart(firstYearGrowth);
      if (fallback !== null) {
        points.push({ year: 0, growth: fallback });
      }
    }
    return points;
  }, [growthCurve, initialGrowthOriginal, firstYearGrowth]);

  const growthFadeXAxisConfig = useMemo(() => detectNumericAxisConfig(), []);

  const growthAssumptionEntry = useMemo(() => {
    if (growthEntries.length === 0) {
      return null;
    }
    if (activeLabel) {
      const matched = growthEntries.find(
        ([label]) => label.toLowerCase() === activeLabel.toLowerCase(),
      );
      if (matched) {
        return matched;
      }
    }
    return growthEntries[0];
  }, [growthEntries, activeLabel]);

  const growthLabelStart = firstYearGrowth ?? initialGrowthOriginal ?? null;
  const activeMethodLabel = null;
  const assumptionMethodCandidate = growthAssumptionEntry?.[1] ?? null;
  const assumptionMethodLabel =
    assumptionMethodCandidate &&
    typeof assumptionMethodCandidate.method === "string"
      ? assumptionMethodCandidate.method
      : null;
  const assumptionWindowYears =
    typeof assumptionMethodCandidate?.window_years === "number"
      ? assumptionMethodCandidate.window_years
      : null;
  const assumptionSourceKey =
    typeof assumptionMethodCandidate?.source_metric === "string"
      ? assumptionMethodCandidate.source_metric
      : null;
  const modelSourceKey =
    typeof activeDetail?.growth_metric_source === "string"
      ? activeDetail.growth_metric_source
      : typeof activeDetail?.growth_metric_key === "string"
        ? activeDetail.growth_metric_key
        : null;
  const inputSourceKey =
    textFromInputs("growth_metric_source") ??
    textFromInputs("growth_metric_key");
  const growthSourceLabel = formatGrowthSourceLabel(
    assumptionSourceKey ?? modelSourceKey ?? inputSourceKey ?? null,
  );
  const growthSourceDisplay =
    growthSourceLabel && growthSourceLabel.length > 0
      ? growthSourceLabel.toUpperCase()
      : null;
  const fadeKind =
    interpretGrowthMethod(activeMethodLabel) ??
    interpretGrowthMethod(assumptionMethodLabel) ??
    detectFadeKindFromCurve([
      initialGrowthOriginal,
      firstYearGrowth,
      ...growthCurve,
    ]) ??
    (typeof inferredGrowthStep === "number" ? "linear" : "exponential");

  const methodLabel =
    fadeKind === "linear" ? "Linear Fade" : "Exponential Fade";

  const linearDelta =
    fadeKind === "linear" && typeof inferredGrowthStep === "number"
      ? formatPercentFromRatio(Math.abs(inferredGrowthStep), 2)
      : null;
  const fadeDeltaLabel =
    fadeKind === "linear" && linearDelta
      ? { label: "Δ ต่อปี", value: linearDelta }
      : null;
  const normalizedModelUsedKey =
    typeof modelUsedKey === "string" ? modelUsedKey.toLowerCase() : "";
  const normalizedModelType =
    typeof activeDetail?.model_type === "string"
      ? activeDetail.model_type.toLowerCase()
      : "";
  const isFundNavModel = Boolean(
    normalizedModelUsedKey.includes("nav") ||
      normalizedModelUsedKey.includes("fund net asset") ||
      normalizedModelType.includes("fund nav") ||
      normalizedModelType.includes("fund net asset"),
  );
  const valuationCardTitle = isFundNavModel
    ? "Fund NAV"
    : activeDetail?.base_metric ?? "Historical FCF";

  return (
    <div className={styles.wrapper}>
      <div className={styles.cardGrid}>
        {discountInfo && !isFundNavModel ? (
          <Card className={styles.cardSurface}>
            <CardHeader>
              <div className={styles.discountHeaderRow}>
                <CardTitle>Discount Rate</CardTitle>
              </div>
            </CardHeader>
            <CardContent className={styles.discountBody}>
              <div className={styles.rateRow}>
                <span className={styles.rateValue}>
                  {formatPercentFromRatio(discountInfo.final_rate, 2)}
                </span>
                <span className={styles.baseTag}>
                  Base {formatPercentFromRatio(discountInfo.base_rate, 2)}
                </span>
              </div>
              {adjustments.length > 0 ? (
                <div className={styles.adjustments}>
                  {adjustments.map((item, index) => (
                    <details
                      key={`${item.code ?? item.label ?? "adj"}-${index}`}
                      className={styles.adjustmentItem}
                    >
                      <summary className={styles.adjustmentSummary}>
                        <span className={styles.adjustmentLabel}>
                          {item.label ?? item.code ?? `Adjustment ${index + 1}`}
                        </span>
                        <span className={styles.adjustmentDelta}>
                          {formatPercentFromRatio(item.delta, 2)}
                        </span>
                      </summary>
                      {item.reason && (
                         <div className={styles.adjustmentReason}>
                           {item.reason}
                         </div>
                      )}
                    </details>
                  ))}
                </div>
              ) : null}
            </CardContent>
          </Card>
        ) : null}

        <Card className={styles.cardSurface}>
          <CardHeader>
            <div
              style={{ display: "flex", flexDirection: "column", gap: "2px" }}
            >
              <div style={{ display: "flex", alignItems: "center" }}>
                <CardTitle>{valuationCardTitle}</CardTitle>
                {isFundNavModel ? (
                  <NAVTooltip />
                ) : (
                  <DCFInfoTooltip detail={activeDetail} />
                )}
              </div>
            </div>
          </CardHeader>
          <CardContent className={styles.growthBody}>
            {fcfHistoryData.length > 0 ? (
              <div className={styles.chartWrapper}>
                <div style={{ overflowX: "auto", overflowY: "hidden", paddingBottom: "12px", width: "100%" }}>
                  <div style={{ minWidth: "100%", width: "max(100%, 700px)", height: "300px" }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ComposedChart
                    data={fcfHistoryData}
                    barGap={-24}
                    margin={{
                      top: 30,
                      right: 30,
                      left: 20,
                      bottom: fcfHistoryXAxisConfig.bottomMargin,
                    }}
                  >
                    <XAxis
                      dataKey="year"
                      type="category"
                      interval={0}
                      tick={
                        <CustomXAxisTick
                          angle={fcfHistoryXAxisConfig.angle}
                          textAnchor={fcfHistoryXAxisConfig.textAnchor}
                        />
                      }
                      tickLine={false}
                      axisLine={{ stroke: "var(--border-color, #d7def1)" }}
                    />
                    <YAxis
                      yAxisId="left"
                      domain={chartDomains.leftDomain as any}
                      tickFormatter={(value) =>
                        new Intl.NumberFormat("en-US", {
                          notation: "compact",
                          compactDisplay: "short",
                        }).format(value)
                      }
                      tick={{ fontSize: 12, fill: "var(--text-secondary, #5b6a86)" }}
                      width={40}
                      tickLine={false}
                      axisLine={{ stroke: "var(--border-color, #d7def1)" }}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      domain={chartDomains.rightDomain as any}
                      tickFormatter={(value) => `${value.toFixed(0)}%`}
                      tick={{ fontSize: 12, fill: "var(--chart-growth, #34d399)" }}
                      width={40}
                      tickLine={false}
                      axisLine={false}
                    />
                    <RechartsTooltip
                      position={{ y: 0 }}
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const fcfPayload = payload.find(
                            (p) => p.dataKey === "value",
                          );
                          const growthPayload = payload.find(
                            (p) => p.dataKey === "growthPct",
                          );
                          const marketPayload = payload.find(
                            (p) => p.dataKey === "marketValue",
                          );
                          const item = payload[0].payload;

                          return (
                            <div
                              style={{
                                backgroundColor: "var(--card-bg, #fff)",
                                padding: "8px 12px",
                                border: "1px solid var(--border-color, #e2e8f0)",
                                borderRadius: "8px",
                                boxShadow: "0 4px 6px -1px var(--card-shadow, rgba(0, 0, 0, 0.1))",
                                fontSize: "12px",
                                color: "var(--text-primary, #1e293b)",
                              }}
                            >
                              <div
                                style={{
                                  fontWeight: 600,
                                  marginBottom: "6px",
                                  color: "var(--text-primary, #1e293b)",
                                }}
                              >
                                {item.year}
                              </div>
                              {marketPayload && marketPayload.value != null && (
                                <div
                                  style={{
                                    color: "#ef4444",
                                    marginBottom: "4px",
                                    fontWeight: 600,
                                  }}
                                >
                                  Market Expectation :{" "}
                                  {new Intl.NumberFormat("en-US", {
                                    notation: "compact",
                                    compactDisplay: "short",
                                    maximumFractionDigits: 2,
                                  })
                                    .format(marketPayload.value as number)
                                    .replace("T", "T")
                                    .replace("B", " B")
                                    .replace("M", " M")}
                                </div>
                              )}
                              {fcfPayload && (
                                <div
                                  style={{
                                    color: item.is_estimate
                                      ? "var(--chart-orange, #f59e0b)"
                                      : "var(--chart-blue, #1453d1)",
                                    fontWeight: 600,
                                  }}
                                >
                                  {item.note ||
                                    (activeDetail?.base_metric
                                      ? activeDetail.base_metric.replace(
                                          / \(.*\)/,
                                          "",
                                        )
                                      : "FCF")}{" "}
                                  :{" "}
                                  {new Intl.NumberFormat("en-US", {
                                    notation: "compact",
                                    compactDisplay: "short",
                                    maximumFractionDigits: 2,
                                  })
                                    .format(fcfPayload.value as number)
                                    .replace("T", "T")
                                    .replace("B", " B")
                                    .replace("M", " M")}
                                </div>
                              )}
                              {growthPayload && growthPayload.value != null && (
                                <div
                                  style={{ color: "var(--chart-growth, #10b981)", marginTop: "4px" }}
                                >
                                  Growth{(item as any).growth_cap_label || ""} :{" "}
                                  {(item.originalGrowthPct != null ? item.originalGrowthPct as number : growthPayload.value as number).toFixed(1)} %
                                  {item.isGrowthCapped ? " (Chart Capped)" : ""}
                                </div>
                              )}
                            </div>
                          );
                        }
                        return null;
                      }}
                      cursor={{ fill: "rgba(20, 83, 209, 0.05)" }}
                    />
                    <Bar
                      yAxisId="left"
                      dataKey="value"
                      radius={[4, 4, 0, 0]}
                      barSize={24}
                    >
                      {fcfHistoryData.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={
                            entry.year === "DCF Base"
                              ? "var(--chart-orange, #ea580c)" // Solid Orange (Deep) for Base
                              : (entry as any).is_projection
                                ? "var(--chart-orange-faded, #fdba74)" // Light/Faded Orange for Projection
                                : "var(--chart-blue, #1453d1)" // Solid Blue for History
                          }
                        />
                      ))}
                    </Bar>
                    <Bar
                      yAxisId="left"
                      dataKey="marketValue"
                      barSize={24}
                      radius={[4, 4, 0, 0]}
                      fill="transparent"
                      stroke="#ef4444"
                      strokeDasharray="4 4"
                      strokeWidth={2}
                      isAnimationActive={false}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="growthPct"
                      stroke="var(--chart-growth, #34d399)"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                    />
                  </ComposedChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              </div>
            ) : isFundNavModel ? (
              <div className={styles.chartEmpty}>
                <div style={{ marginBottom: "8px", color: "var(--text-secondary, #64748b)" }}>
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
                </div>
                <div style={{ fontSize: "16px", fontWeight: 600, color: "var(--text-primary, #1e293b)", marginBottom: "4px" }}>
                  Fund NAV Valuation
                </div>
                <div style={{ fontSize: "13px", color: "var(--text-secondary, #64748b)", maxWidth: "300px", margin: "0 auto", lineHeight: 1.5 }}>
                  Net Asset Value (NAV) is calculated based on the total net assets of this fund. Free Cash Flow projections are not applicable.
                </div>
              </div>
            ) : (
              <div className={styles.chartEmpty}>No FCF History</div>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
