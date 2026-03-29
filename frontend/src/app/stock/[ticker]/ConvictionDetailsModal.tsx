"use client";

import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip,
  AreaChart,
  Area,
  YAxis
} from "recharts";
import { LottieIcon } from "@/components/LottieIcon";
import exitAnimation from "@/assets/lottie/icons8-exit.json";
import infoAnimation from "@/assets/lottie/icons8-info.json";
import styles from "./ConvictionDetailsModal.module.css";

// --- Types matching the backend structure ---

export type CheckComponent = {
  value?: number | string | boolean | null;
  value_pp?: number | null; // For percentage points
  threshold?: number | string;
  points: number;
  max_points?: number;
  band?: string;
  note?: string;
  [key: string]: unknown;
};

export type ScoreBlock = {
  points: number;
  max_points: number;
  components: Record<string, CheckComponent | unknown>;
};

export type QuantitativeBreakdown = {
  total: number;
  weight?: number;
  max_points?: number;
  blocks: Record<string, ScoreBlock>;
};

export type QualitativeBreakdown = {
  total: number;
  weight?: number;
  max_points?: number;
  blocks: Record<string, ScoreBlock>;
};

export type EthicalBreakdown = {
  points: number;
  max_points: number;
  components: Record<string, unknown>;
};

export type PhaseBreakdown = {
  total: number;
  quantitative?: QuantitativeBreakdown;
  qualitative?: QualitativeBreakdown;
  ethical?: EthicalBreakdown | number; // Number in phase 2, object in phase 1
  [key: string]: unknown;
};

export type ConvictionBreakdown = {
  final_score?: number;
  quantitative?: QuantitativeBreakdown;
  qualitative?: QualitativeBreakdown;
  ethical?: EthicalBreakdown;
  final_dr?: number;
  phase1?: PhaseBreakdown;
  phase2?: PhaseBreakdown;
  weights?: unknown;
  industry_group?: string;
};

// --- Component Props ---

type Props = {
  isOpen: boolean;
  onClose: () => void;
  breakdown: ConvictionBreakdown | null;
  score: number | null;
  financialData?: any[]; // Using any[] to avoid strict type dependency for now
};

// --- Helper Functions ---

const normalizeLabel = (key: string, finalDr?: string | null, comp?: CheckComponent): string => {
  if (key === "roic_minus_r") {
    return `ROIC vs Cost of Capital (${finalDr ?? "?"}%)`;
  }
  let label = key
    .replace(/_/g, " ")
    .replace(/([a-z])([A-Z])/g, "$1 $2")  // Only split camelCase, not ALL_CAPS
    .replace(/\b\w+/g, (word) => {
      // Title-case each word: first letter uppercase, rest lowercase
      return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    })
    .replace("Gte", "≥")
    .replace("Gt", ">")
    .replace("Lt", "<")
    .replace("Lte", "≤")
    .replace("pct", " %")
    .trim();

  // Dynamically replace hardcoded text with actual backend thresholds
  if (comp && comp.threshold !== undefined && comp.threshold !== null && typeof comp.threshold === 'number') {
    if (label.includes("%") && comp.threshold >= 0 && comp.threshold <= 1) {
       const percentVal = Math.round(comp.threshold * 100);
       label = label.replace(/\d+\s*%/, `${percentVal}%`);
    } else if (label.toLowerCase().includes("x")) {
       label = label.replace(/\d+\s*[xX]/, `${comp.threshold}x`);
    }
  }

  return label;
};

const METRIC_DESCRIPTIONS: Record<string, string> = {
  // Profitability
  'roic_minus_r': 'วัดส่วนต่างระหว่างผลตอบแทนต่อเงินลงทุน (ROIC) และต้นทุนเงินทุน (WACC) แสดงถึงความสามารถในการสร้างมูลค่าเพิ่ม (Value Creation) ยิ่งบวกเยอะยิ่งดี',
  'roic_gt_12pct': 'วัดผลตอบแทนต่อเงินลงทุน (ROIC) ว่าผ่านเกณฑ์ขั้นต่ำ 12 % หรือไม่ เพื่อดูประสิทธิภาพการนำทุนไปใช้ให้เกิดกำไร',
  'roic_gte_15pct': 'วัดผลตอบแทนต่อเงินลงทุน (ROIC) ว่ามากกว่าหรือเท่ากับ 15 % หรือไม่ เป็นเกณฑ์สำหรับกิจการที่มีขีดความสามารถการแข่งขันสูง',
  'roe_gt_15pct': 'วัดผลตอบแทนต่อส่วนของผู้ถือหุ้น (ROE) ว่ามากกว่า 15 % หรือไม่ แสดงถึงทักษะบริหารเงินทุนของผู้ถือหุ้นให้งอกเงย',
  'roe_gte_12pct': 'วัดผลตอบแทนต่อส่วนของผู้ถือหุ้น (ROE) ว่ามากกว่าหรือเท่ากับ 12 % หรือไม่',
  'gross_margin_gt_20pct': 'วัดอัตรากำไรขั้นต้น (Gross Margin) > 20 % บ่งชี้ว่าบริษัทมีอำนาจในการตั้งราคา (Pricing Power) และคุมต้นทุนการผลิตได้ดี',
  'net_margin_gt_10pct': 'วัดอัตรากำไรสุทธิ (Net Margin) > 10 % บ่งบอกถึงความสามารถในการทำกำไรบรรทัดสุดท้ายแบบแข็งแกร่ง',
  'net_margin_gte_15pct': 'วัดอัตรากำไรสุทธิ (Net Margin) ≥ 15 % เกณฑ์เข้มงวดสำหรับการทำกำไรระดับพิเศษ',
  'roe': 'ประเมินและให้คะแนนจากข้อมูลทางการเงินของบริษัท เพื่อพิจารณาประสิทธิภาพในการสร้างผลตอบแทนจากส่วนของผู้ถือหุ้น',
  'roic': 'ประเมินและให้คะแนนจากข้อมูลทางการเงินของบริษัท เพื่อวิเคราะห์ความสามารถในการนำเงินลงทุนไปสร้างกำไร',
  'fcf_margin': 'ประเมินสัดส่วนของกระแสเงินสดอิสระ (Free Cash Flow) เปรียบเทียบกับรายได้รวม เพื่อดูประสิทธิภาพการแปลงยอดขายเป็นเงินสด',
  'fcf_margin_gt_10pct': 'อัตรากำไรกระแสเงินสดอิสระ (FCF Margin) > 10% แสดงว่ารายได้แปลงเป็นเงินสดได้ดีเยี่ยม ถือเป็นบริษัทที่แข็งแกร่งด้านสภาพคล่อง',
  'gross_margin': 'ประเมินและให้คะแนนจากข้อมูลทางการเงินของบริษัท เพื่อวิเคราะห์ความแข็งแกร่งของอัตรากำไรขั้นต้น',
  'net_profit_margin': 'ประเมินและให้คะแนนจากข้อมูลทางการเงินของบริษัท เพื่อวิเคราะห์ความสามารถในการแข่งขันและการควบคุมค่าใช้จ่ายทั้งหมด',
  
  // Growth
  'growth_magnitude': 'ประเมินความเร็วและความแรงของการเติบโต โดยพิจารณาจากอัตราการเติบโตเฉลี่ย (CAGR) ของกำไรสุทธิหรือกระแสเงินสด ว่าโตในระดับน่าประทับใจหรือไม่',
  'growth_consistency': 'ตรวจสอบความสม่ำเสมอในการเติบโต โดยดูความถี่ที่กำไรสามารถทำสถิติ All-time High ยิ่งโตต่อเนื่อง ไม่ผันผวน ยิ่งได้คะแนนดี',
  'revenue_growth_gte_10pct': 'วัดการเติบโตของรายได้หลัก (Revenue Growth) ≥ 10 % เพื่อความมั่นใจว่ายอดขายขยายตัวได้จริง',
  'eps_growth_gte_10pct': 'วัดการเติบโตของกำไรต่อหุ้น (EPS Growth) ≥ 10 % บ่งชี้ถึงการเติบโตที่ส่งผลถึงผู้ถือหุ้นโดยตรง',
  'fcf_growth_gte_8pct': 'วัดการเติบโตของกระแสเงินสดอิสระ (FCF Growth) ≥ 8 % บ่งบอกว่าบริษัทมีเงินสดเหลือเพื่อนำไปจ่ายปันผลหรือลงทุนต่ออย่างต่อเนื่อง',

  // Financial Health
  'debt_to_equity_lt_1': 'ตรวจสอบภาระหนี้สิน โดยหนี้สินที่มีดอกเบี้ยต่อทุน (D/E) ควร < 1 เท่า แสดงถึงฐานะการเงินที่ปลอดภัย ไม่เสี่ยงล้มละลายช่วงวิกฤต',
  'interest_coverage_gt_10x': 'ความสามารถในการชำระดอกเบี้ย (Interest Coverage Ratio) > 10 เท่า แสดงว่ากำไรจากการดำเนินงานมีมากพอจ่ายดอกเบี้ยได้อย่างสบาย ๆ',
  'payout_ratio_balance': 'อัตราการจ่ายปันผล (Payout Ratio) มีความสมดุล คือจ่ายปันผลในระดับที่ไม่รบกวนการนำเงินไปลงทุนให้บริษัทเติบโตในระยะยาว',
  'dilution_lt_3pct': 'ตรวจสอบการแจกหุ้นหรือ ESOP ให้พนักงาน โดยจำนวนหุ้นจดทะเบียนไม่ควรเพิ่มเกิน 3 % เพื่อป้องกันไม่ให้กำไรต่อหุ้นถูกเจือจาง',
  'cash_gt_debt': 'เงินสดและรายการเทียบเท่าเงินสด (Cash) ต้องมากกว่าหนี้สินที่มีดอกเบี้ยทั้งหมด ถือเป็นงบดุลระดับที่แข็งแกร่งและปลอดภัยมาก',

  // Financial sector specific
  'underwriting_float_quality': 'คุณภาพการปล่อยสินเชื่อ หรือการนำ Float ยอดเงินสำรองประกันไปลงทุน เพื่อสร้างผลตอบแทนสม่ำเสมอในกลุ่มการเงินหรือประกัน',
  'combined_ratio_quality': 'Combined Ratio ถ้าน้อยกว่า 1 หมายถึงสามารถทำกำไรจากการรับประกันภัย (Underwriting Profit) ได้โดยไม่ต้องพึ่งผลตอบแทนจากการลงทุนเพียงอย่างเดียว',
  'reit_return_quality': 'วัดคุณภาพผลตอบแทนของ REIT โดยใช้กระแสเงินสดอิสระต่อรายได้ (FCF Margin หรือ Owner Earnings)',
};

const METRIC_CRITERIA: Record<string, string> = {
  // Profitability
  'roic_minus_r': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'roic_gt_12pct': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'roic_gte_15pct': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'roe_gt_15pct': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'roe_gte_12pct': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'gross_margin_gt_20pct': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'net_margin_gt_10pct': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'net_margin_gte_15pct': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  
  // Growth
  'growth_magnitude': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'growth_consistency': 'ประเมินความสม่ำเสมอใน 5 ปีล่าสุด',
  'revenue_growth_gte_10pct': 'การเติบโต 5 ปีล่าสุด',
  'eps_growth_gte_10pct': 'การเติบโต 5 ปีล่าสุด',
  'fcf_growth_gte_8pct': 'การเติบโต 5 ปีล่าสุด',

  // Financial Health
  'debt_to_equity_lt_1': 'ข้อมูลไตรมาสล่าสุด',
  'interest_coverage_gt_10x': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'payout_ratio_balance': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'dilution_lt_3pct': 'ข้อมูลรายปีล่าสุด เทียบปีก่อนหน้า (Annual YoY)',
  'cash_gt_debt': 'ข้อมูลไตรมาสล่าสุด',

  // Financial sector specific
  'underwriting_float_quality': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'combined_ratio_quality': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด',
  'reit_return_quality': 'ค่าขจัดความแปรปรวน (Robust Median) 5 ปีล่าสุด'
};

// Sub-component to handle hover state for Lottie icons independently
const HoverLottieIcon = ({ animationData, className, width = 22, height = 22, speed = 1, style }: { animationData: any, className?: string, width?: number, height?: number, speed?: number, style?: React.CSSProperties }) => {
  const [play, setPlay] = useState(false);
  return (
    <span 
      className={className} 
      style={{ display: 'inline-flex', width, height, cursor: 'pointer', ...style }}
      onMouseEnter={() => setPlay(true)}
      onMouseLeave={() => setPlay(false)}
    >
      <LottieIcon animationData={animationData} loop={false} play={play} speed={speed} />
    </span>
  );
};

const formatBigNumber = (num: number | null | undefined): string => {
  if (num === null || num === undefined) return "N/A";
  const abs = Math.abs(num);
  if (abs >= 1e12) return (num / 1e12).toFixed(2) + "T";
  if (abs >= 1e9) return (num / 1e9).toFixed(2) + "B";
  if (abs >= 1e6) return (num / 1e6).toFixed(2) + "M";
  if (abs >= 1e3) return (num / 1e3).toFixed(2) + "K";
  return num.toLocaleString();
};

const formatValue = (val: unknown, key: string): string => {
  if (val === null || val === undefined) return "—";
  if (typeof val === "boolean") return val ? "Pass" : "Fail";
  
  if (Array.isArray(val)) {
     return val.map(v => typeof v === 'number' ? formatBigNumber(v) : String(v)).join(" > ");
  }
  
  if (typeof val === "number") {
    const absVal = Math.abs(val);
    const sign = val < 0 ? "- " : "";

    // Handle roic_minus_r which is already in percentage points (e.g. 5.0 = 5%)
    if (key === "roic_minus_r") {
        return `${sign}${absVal.toFixed(2)}%`;
    }

    const lowerKey = key.toLowerCase();
    const isRatio = lowerKey.includes("debt") || lowerKey.includes("equity") || lowerKey.includes("coverage") || lowerKey.includes("ratio_balance");
    // Exclude 'consistency' from percentage formatting (it's a count of years)
    const isPercentage = (lowerKey.includes("growth") || lowerKey.includes("margin") || lowerKey.includes("roe") || lowerKey.includes("roic") || lowerKey.includes("pct") || lowerKey.includes("yield") || lowerKey.includes("payout")) && !lowerKey.includes("consistency");

    if (isRatio && !isPercentage) {
       return `${sign}${absVal.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    }

    // Default to percentage for most metrics in this context if < 1 or explicitly a percentage key
    if (isPercentage || (absVal < 1 && absVal > 0)) {
        if (absVal < 0.0001 && val !== 0) return "< 0.01%";
        return `${sign}${(absVal * 100).toFixed(2)}%`;
    }

    // Use BigNumber formatting for large absolute numbers (e.g. > 1000) that aren't ratios/percentages
    if (absVal >= 1000) {
        return formatBigNumber(val);
    }

    return `${sign}${absVal.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
  }
  return String(val);
};

const CustomTooltip = ({ active, payload, label }: any) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    const value = data.A;
    // Calculate color based on value (0-100)
    const hue = Math.min(120, Math.max(0, value * 1.2)); 
    const color = `hsl(${hue}, 80%, 35%)`;

    return (
      <div style={{
        backgroundColor: 'var(--card-bg, #fff)',
        border: '1px solid var(--border-color, #e2e8f0)',
        padding: '8px 12px',
        borderRadius: '8px',
        boxShadow: 'var(--card-shadow, 0 4px 6px -1px rgba(0, 0, 0, 0.1))',
        fontSize: '13px',
        fontWeight: 600,
        color: 'var(--text-primary, #000000)'
      }}>
        {label} : <span style={{ color: color }}>{value.toFixed(0)}%</span>
      </div>
    );
  }
  return null;
};

const RadarTick = ({ payload, x, y, textAnchor }: any) => {
  let value = payload.value as string;

  const words = value.split(" ");
  let line1 = value;
  let line2 = "";

  if (words.length > 2) {
    const half = Math.ceil(words.length / 2);
    line1 = words.slice(0, half).join(" ");
    line2 = words.slice(half).join(" ");
  } else if (words.length === 2) {
    line1 = words[0];
    line2 = words[1];
  }

  return (
    <text x={x} y={y} fontSize={11} fill="var(--text-secondary, #64748b)" textAnchor={textAnchor} dominantBaseline="central">
      <tspan x={x} dy={line2 ? "-0.5em" : "0"}>{line1}</tspan>
      {line2 && <tspan x={x} dy="1.2em">{line2}</tspan>}
    </text>
  );
};


const getTrendData = (data: any[], key: string, isFinance: boolean = false, comp?: any) => {
  if (!data || data.length === 0) return null;

  // Skip trend graphs for specific checks where a 5-year trend chart is misleading/unnecessary
  // (e.g., when backend uses a weighted average or MRQ that differs from simple annual/quarterly trends)
  const skipTrendForKeys = [
    "dilution_lt_3pct", "cash_gt_debt", "roic_minus_r", 
    "is_simple_and_understandable", "has_strong_economic_moat", 
    "management_is_rational", "is_zero_sum_game", "has_unpredictable_regulatory_risk",
    "interest_coverage_gt_10x", "roe_gte_12pct", "payout_ratio_balance",
    "combined_ratio_quality", "underwriting_float_quality", "debt_to_equity_lt_1"
  ];
  if (skipTrendForKeys.includes(key)) return null;
  
  const isNetIncomeGrowth = comp && typeof comp.note === 'string' && comp.note.includes("Net Income");
  const growthMetric = isNetIncomeGrowth ? "net_income" : "owner_earnings";

  const map: Record<string, string> = {
    // Explicit mappings for Conviction Score keys
    roic_minus_r: "roic",
    growth_magnitude: growthMetric,
    growth_consistency: growthMetric,
    roic_gt_12pct: "roic",
    roic_gte_15pct: "roic",
    roe_gt_15pct: "roe",
    gross_margin_gt_20pct: "gross_margin",
    net_margin_gt_10pct: "net_profit_margin",
    fcf_margin_gt_10pct: "fcf_margin",
    revenue_growth_gte_10pct: "revenue_growth",
    eps_growth_gte_10pct: "eps_growth_diluted",
    fcf_growth_gte_8pct: "free_cash_flow", // Proxy with absolute FCF
    debt_to_equity_lt_1: "debt_to_equity",
    interest_coverage_gt_10x: "interest_coverage",
    payout_ratio_balance: "payout_ratio",
    dilution_lt_3pct: "share_outstanding_diluted", // Proxy: rising EPS often implies no massive dilution, but not perfect.
    cash_gt_debt: "cash_and_equivalents",
    roe_gte_12pct: "roe",
    net_margin_gte_15pct: "net_profit_margin",
    underwriting_float_quality: "combined_ratio",
    combined_ratio_quality: "combined_ratio",
    
    // Legacy/Generic mappings
    roic: "roic",
    gross_margin_trend: "gross_margin",
    operating_margin_trend: "net_profit_margin",
    net_margin_trend: "net_profit_margin",
    revenue_growth: "revenue_growth",
    earnings_growth: "eps_growth_diluted",
    book_value_growth: "book_value_growth",
    debt_to_equity: "debt_to_equity",
    interest_coverage: "interest_coverage",
    fcf_growth: "free_cash_flow",
    fcf_yield: "fcf_margin",
    current_ratio: "current_ratio",
  };
  
  // 1. Try direct map
  let field = map[key];
  
  // 2. Try normalized key matching if no direct map
  if (!field) {
     const lowerKey = key.toLowerCase();
     if (lowerKey.includes("gross_margin")) field = "gross_margin";
     else if (lowerKey.includes("operating_margin")) field = "net_profit_margin";
     else if (lowerKey.includes("net_margin")) field = "net_profit_margin";
     else if (lowerKey.includes("revenue")) field = "total_revenue";
     else if (lowerKey.includes("earnings") || lowerKey.includes("eps")) field = "eps_diluted";
     else if (lowerKey.includes("debt")) field = "debt_to_equity";
     else if (lowerKey.includes("payout")) field = "payout_ratio";
     else if (lowerKey.includes("interest")) field = "interest_coverage";
     else if (key in data[0]) field = key;
  }
  
  if (!field) return null;

  // All balance-sheet items use MRQ (quarterly) data
  const mrqKeys = ["debt_to_equity_lt_1", "debt_to_equity", "cash_gt_debt", "current_ratio", "dilution_lt_3pct"];
  const isMRQ = mrqKeys.includes(key);

  let periodData = data.filter(r => {
    const t = (r.period_type || "").toLowerCase();
    if (isMRQ) {
       return t === "quarterly" || t === "q";
    }
    return t === "annual" || t === "a";
  });

  if (periodData.length === 0) {
      periodData = data;
  }

  // Process data: Filter, Sort, Dedupe
  const processed = periodData
    .filter(row => {
        if (!row.report_date) return false;
        if (field === "owner_earnings") {
            return row.cash_flow_from_operations !== null || row.net_income !== null;
        }
        const cellValue = row[field];
        return cellValue !== null && cellValue !== undefined && cellValue !== '';
    })
    .map(row => {
      let val = 0;
      if (field === "owner_earnings") {
          if (isFinance) {
              val = Number(row.net_income || 0);
          } else {
              const cfo = row.cash_flow_from_operations;
              if (cfo !== null && cfo !== undefined) {
                  val = Number(cfo) - Math.abs(Number(row.capital_expenditures || 0)) - Number(row.stock_based_compensation || 0);
              } else {
                  val = 0;
              }
          }
      } else {
          val = Number(row[field]);
      }

      const d = new Date(row.report_date);
      const q = Math.floor(d.getMonth() / 3) + 1;
      return {
        date: d,
        year: d.getFullYear(),
        label: isMRQ ? `Q${q} ${d.getFullYear().toString().slice(-2)}` : d.getFullYear().toString(),
        value: val
      };
    })
    .filter(item => !isNaN(item.value) && !isNaN(item.year))
    .sort((a, b) => a.date.getTime() - b.date.getTime());

  // Deduplicate by label (keeping the latest date per label)
  const uniqueByKey = new Map<string, { year: number, label: string, value: number, date: Date }>();
  processed.forEach(item => {
    uniqueByKey.set(item.label, { year: item.year, label: item.label, value: item.value, date: item.date });
  });

  // Only keep the last N+1 periods if we are doing YoY growth so the final diff array has N items.
  const limit = isMRQ ? 4 : 5;
  let isGrowthCalc = key === "growth_magnitude" || key === "growth_consistency";
  const rawLimit = isGrowthCalc ? limit + 1 : limit;

  let sortedUnique = Array.from(uniqueByKey.values())
    .sort((a, b) => a.date.getTime() - b.date.getTime())
    .slice(-rawLimit);

  // If calculating growth magnitude or consistency, we need YoY growth rates
  let finalData = sortedUnique;

  if (isGrowthCalc && sortedUnique.length > 1) {
    const growthData = [];
    for (let i = 1; i < sortedUnique.length; i++) {
        const prev = sortedUnique[i - 1].value;
        const curr = sortedUnique[i].value;
        // Calculate YoY growth percentage (handle negative/zero cases gracefully if needed, here we use simple formula)
        const growth = prev !== 0 ? (curr - prev) / Math.abs(prev) : 0;
        growthData.push({
            year: sortedUnique[i].year,
            label: sortedUnique[i].label,
            date: sortedUnique[i].date,
            value: growth
        });
    }
    finalData = growthData;
  }

  // Only filter out far future years
  const currentYear = new Date().getFullYear();
  const relevant = finalData
    .filter(d => d.year <= currentYear + 1);

  if (relevant.length < 2) return null;
  
  // Determine if percentage based on field name, value range, or explicit flag
  const isPercent = 
    isGrowthCalc || 
    key.includes("margin") || key.includes("growth") || key.includes("roic") || key.includes("roe") || key.includes("yield") || key.includes("payout") ||
    field.includes("margin") || field.includes("growth") || field.includes("roic") || field.includes("roe") || field.includes("yield") || field.includes("payout");
  
  return { data: relevant, isPercent, title: isMRQ ? "4 Quarter Trend" : "5 Year Trend" };
};

const InfoTooltip = ({ label, compKey, data, comp }: { label: string, compKey: string, data: any[] | undefined, comp?: CheckComponent }) => {
  const wrapperRef = React.useRef<HTMLDivElement>(null);
  const tooltipRef = React.useRef<HTMLDivElement>(null);
  const [visible, setVisible] = React.useState(false);
  const [tooltipStyle, setTooltipStyle] = React.useState<React.CSSProperties>({ top: -9999, left: -9999 });

  let desc = METRIC_DESCRIPTIONS[compKey] || 'ประเมินและให้คะแนนจากข้อมูลทางการเงินของบริษัท เพื่อวิเคราะห์ความแข็งแกร่งตามเกณฑ์ที่กำหนด';
  const evalCriteria = METRIC_CRITERIA[compKey] || 'ประเมินตามเกณฑ์มาตรฐาน';

  // Inject dynamic thresholds if present
  if (comp && comp.threshold !== undefined && comp.threshold !== null && typeof comp.threshold === 'number') {
      if (comp.threshold >= 0 && comp.threshold <= 1) {
          const percentVal = Math.round(comp.threshold * 100);
          desc = desc.replace(/\d+\s*%/, `${percentVal} %`);
      } else {
          desc = desc.replace(/\d+\s*เท่า/, `${comp.threshold} เท่า`).replace(/\d+\s*x/i, `${comp.threshold}x`);
      }
  }

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

    // Flip up if not enough room below
    if (top + tipH > vh - GAP) {
      top = anchor.top - tipH - GAP;
    }
    // Shift left if tooltip would overflow right edge
    if (left + tipW > vw - GAP) {
      left = vw - tipW - GAP;
    }
    if (left < GAP) left = GAP;
    if (top < GAP) top = GAP;

    setTooltipStyle({ top, left });
    setVisible(true);
  };

  const hideTooltip = () => setVisible(false);

  return (
    <span
      ref={wrapperRef}
      className={styles.infoIconWrapper}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onClick={() => setVisible(!visible)}
    >
      <HoverLottieIcon animationData={infoAnimation} width={20} height={20} className={styles.infoIcon} style={{ filter: "var(--icon-filter, none)" }} />
      <div
        ref={tooltipRef}
        className={styles.miniTableTooltip}
        data-visible={visible ? "true" : "false"}
        style={{...tooltipStyle, minWidth: '280px', maxWidth: '340px', padding: '16px', textAlign: 'left', lineHeight: '1.5', cursor: 'default'}}
      >
        <div style={{ fontSize: '14px', fontWeight: 700, color: 'var(--text-primary, #0f172a)', marginBottom: '8px', borderBottom: '1px solid var(--border-color, #e2e8f0)', paddingBottom: '6px' }}>
            {label}
        </div>
        <div style={{ fontSize: '13px', color: 'var(--text-secondary, #334155)', marginBottom: '12px', whiteSpace: 'normal', wordBreak: 'break-word' }}>
            {desc}
        </div>
        <div style={{ fontSize: '12px', color: 'var(--text-secondary, #64748b)', background: 'var(--background, #f8fafc)', padding: '8px', borderRadius: '6px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0px' }}>
                <span>เกณฑ์การประเมิน</span>
                <span style={{ fontWeight: 600, color: '#10b981' }}>{evalCriteria}</span>
            </div>
        </div>
      </div>
    </span>
  );
};

const Sparkline = ({ data, color, isPercent, title }: { data: { label: string, year: number, value: number }[], color: string, isPercent: boolean, title: string }) => {
  const values = data.map(d => d.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const padding = (max - min) * 0.1 || (max * 0.1);

  const wrapperRef = React.useRef<HTMLDivElement>(null);
  const tooltipRef = React.useRef<HTMLDivElement>(null);
  const [visible, setVisible] = React.useState(false);
  const [tooltipStyle, setTooltipStyle] = React.useState<React.CSSProperties>({ top: -9999, left: -9999 });
  const [hoveredYear, setHoveredYear] = React.useState<number | null>(null);

  const showTooltip = () => {
    if (!wrapperRef.current || !tooltipRef.current) return;
    const anchor = wrapperRef.current.getBoundingClientRect();
    // offsetWidth/Height works even when visibility:hidden (unlike getBoundingClientRect which gives 0)
    const tipW = tooltipRef.current.offsetWidth || 220;
    const tipH = tooltipRef.current.offsetHeight || 80;
    const GAP = 8;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    // Default: open upward, aligned to left of anchor
    let top = anchor.top - tipH - GAP;
    let left = anchor.left;

    // Flip down if not enough room above
    if (top < GAP) {
      top = anchor.bottom + GAP;
    }

    // Shift left if tooltip would overflow right edge
    if (left + tipW > vw - GAP) {
      left = vw - tipW - GAP;
    }

    // Ensure not off left edge
    if (left < GAP) left = GAP;

    // Clamp top
    if (top + tipH > vh - GAP) top = vh - tipH - GAP;
    if (top < GAP) top = GAP;

    setTooltipStyle({ top, left });
    setVisible(true);
  };

  const hideTooltip = () => setVisible(false);

  return (
    <div
      ref={wrapperRef}
      className={styles.sparklineWrapper}
      onMouseEnter={showTooltip}
      onMouseLeave={hideTooltip}
      onClick={() => setVisible(!visible)}
    >
      <div 
        style={{ width: 72, height: 28 }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const x = e.clientX - rect.left;
          const ratio = x / rect.width;
          const idx = Math.min(data.length - 1, Math.max(0, Math.round(ratio * (data.length - 1))));
          setHoveredYear(data[idx].year);
        }}
        onTouchMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const touch = e.touches[0];
          const x = touch.clientX - rect.left;
          const ratio = x / rect.width;
          const idx = Math.min(data.length - 1, Math.max(0, Math.round(ratio * (data.length - 1))));
          setHoveredYear(data[idx].year);
        }}
        onMouseLeave={() => setHoveredYear(null)}
        onTouchEnd={() => setHoveredYear(null)}
      >
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data}>
            <defs>
              <linearGradient id={`colorGradient-${color.replace('#','')}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.4}/>
                <stop offset="95%" stopColor={color} stopOpacity={0}/>
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="value"
              stroke={color}
              fill={`url(#colorGradient-${color.replace('#','')})`}
              strokeWidth={2}
              isAnimationActive={false}
            />
            <YAxis domain={[min - padding, max + padding]} hide />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <div
        ref={tooltipRef}
        className={styles.miniTableTooltip}
        data-visible={visible ? "true" : "false"}
        style={tooltipStyle}
      >
        <div className={styles.miniTableTitle}>{title}</div>
        <table className={styles.miniTable}>
          <thead>
            <tr>
              {data.map(d => (
                <th 
                  key={d.label}
                  style={{ fontWeight: hoveredYear === d.year ? 700 : 400, color: hoveredYear === d.year ? 'var(--link-color, #0f4dbc)' : undefined }}
                >
                  {d.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              {data.map(d => (
                <td 
                  key={d.label}
                  style={{ fontWeight: hoveredYear === d.year ? 700 : 400 }}
                >
                  {isPercent
                    ? `${(d.value * 100).toFixed(1)}%`
                    : d.value.toLocaleString(undefined, { maximumFractionDigits: 2, notation: "compact" })}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};

export const ConvictionDetailsModal: React.FC<Props> = ({
  isOpen,
  onClose,
  breakdown,
  score,
  financialData = [],
}) => {
  const [activeTab, setActiveTab] = useState<"quantitative" | "qualitative" | "ethical">("quantitative");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    if (isOpen) {
      document.body.style.overflow = "hidden";
      window.addEventListener('keydown', handleKeyDown);
    } else {
      document.body.style.overflow = "";
    }
    
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !breakdown || !mounted) return null;

  // Support both new flat structure and legacy phase1 structure
  const quantData = breakdown.quantitative || breakdown.phase1?.quantitative;
  const qualData = breakdown.qualitative || breakdown.phase1?.qualitative;
  const ethData = breakdown.ethical || breakdown.phase1?.ethical;

  if (!quantData && !qualData) return null;

  const finalDrStr = breakdown.final_dr ? (breakdown.final_dr * 100).toFixed(1) : null;

  // Calculate totals for tabs
  const quantTotal = quantData?.total ?? 0;
  // Fallback for max_points if missing (legacy weight or default)
  const quantMax = quantData?.max_points ?? (quantData as any)?.weight ?? 45;

  const qualTotal = qualData?.total ?? 0;
  const qualMax = qualData?.max_points ?? (qualData as any)?.weight ?? 45;

  const ethObj = ethData as EthicalBreakdown | undefined;
  const ethTotal = ethObj?.points ?? 0;
  const ethMax = ethObj?.max_points ?? 10;

  // Determine if this is a Financial company (Bank/Insurance) to use Net Income instead of FCF
  // Uses INDUSTRY_ASSET classification from AI qualitative analysis (e.g. "BANK", "INSURANCE")
  const industryAsset = (breakdown as any)?.industryAsset as string | undefined;
  const isFinance = industryAsset === 'BANK' || industryAsset === 'INSURANCE';

  // Process data for Radar Chart
  const chartData = (() => {
    const data: { subject: string; A: number; fullMark: number }[] = [];
    
    // Shorten labels for the radar chart specifically
    const shortenLabel = (label: string) => {
      const map: Record<string, string> = {
        "Profitability Quality": "Profitability",
        "Shareholder Friendliness": "Shareholders",
        "Capital Allocation Effectiveness": "Capital Alloc.",
        "Management Quality": "Management",
        "Governance Candor": "Governance",
        "Insider Alignment": "Insider Align.",
        "Options Alignment": "Options Align.",
      };
      // Stripping parentheticals like "(Excellent)", "(Strong)" from labels
      const cleanedLabel = label.replace(/\s*\(.*?\)\s*/g, '');
      return map[cleanedLabel] || cleanedLabel;
    };

    if (quantData?.blocks) {
      Object.entries(quantData.blocks).forEach(([key, block]) => {
        data.push({
          subject: shortenLabel(normalizeLabel(key, finalDrStr)),
          A: (block.points / block.max_points) * 100,
          fullMark: 100,
        });
      });
    }
    if (qualData?.blocks) {
      Object.entries(qualData.blocks).forEach(([key, block]) => {
        data.push({
          subject: shortenLabel(normalizeLabel(key, finalDrStr)),
          A: (block.points / block.max_points) * 100,
          fullMark: 100,
        });
      });
    }
    if (ethObj && typeof ethObj === "object") {
       data.push({
         subject: "Ethical",
         A: (ethObj.points / ethObj.max_points) * 100,
         fullMark: 100,
       });
    }
    return data;
  })();

  const renderCheckList = (category: "quantitative" | "qualitative" | "ethical") => {
    if (category === "ethical") {
        if (!ethObj) return <div className={styles.empty}>No ethical data available.</div>;
        
        const penalties = ethObj.components.penalty_tags as Record<string, number> | undefined;
        const hasPenalties = penalties && Object.keys(penalties).length > 0;

        // Contextual explanations for ethical penalty tags
        const ETHICAL_PENALTY_EXPLANATIONS: Record<string, string> = {
          ZERO_SUM_BUSINESS: "The core business model inherently involves one party's gain being another's loss, raising ethical concerns about customer welfare.",
          ZERO_SUM_ETHICAL: "Business depends on counterparties absorbing losses or adverse outcomes, creating ethical tension.",
          REGULATORY_UNPREDICTABLE: "Active regulatory actions or unpredictable policy shifts materially threaten the business model.",
          GEOPOLITICAL_RISK: "Operations or supply chain are significantly exposed to geopolitical tensions that could cause disruption.",
          SANCTION_RISK: "Business depends on regions or entities subject to international sanctions, creating compliance and ethical risks.",
          CUSTOMER_CONCENTRATION: "Heavy reliance on a single customer creates vulnerability and potential power imbalance.",
          KEY_PERSON_RISK: "Business viability is overly dependent on a specific individual, raising succession and governance concerns.",
          DISRUPTION_RISK: "Rapid technological or market shifts may render the current business model obsolete.",
          BLACK_BOX_ACCOUNTING: "Financial reporting lacks transparency, with opaque structures or noted internal control weaknesses.",
          HYPER_COMPETITIVE: "Intense competitive pressure may force ethically questionable practices to maintain market position.",
        };

        return (
            <div className={styles.listContainer}>
            <div className={styles.categoryGroup}>
                <div className={styles.categoryHeader}>
                    <span className={styles.categoryTitle}>Ethical Alignment</span>
                    <span className={styles.categoryScore}>{ethObj.points} / {ethObj.max_points}</span>
                </div>
                {hasPenalties && Object.entries(penalties).map(([tag, penalty]) => {
                    const explanation = ETHICAL_PENALTY_EXPLANATIONS[tag] 
                      ?? ETHICAL_PENALTY_EXPLANATIONS[tag.replace(/_/g, "_")] 
                      ?? "Penalty applied due to risk tag.";
                    return (
                    <details key={tag} className={styles.checkItemDetails} open>
                        <summary className={styles.checkItemSummary}>
                            <div className={styles.checkInfo}>
                                <span className={styles.checkLabel}>{normalizeLabel(tag, finalDrStr)}</span>
                            </div>
                            <div className={styles.checkStatus}>
                                 <span className={styles.scoreBadge} style={{ color: '#ef4444', fontWeight: 800 }}>- {penalty}</span>
                            </div>
                        </summary>
                        <div className={styles.checkDetailExpanded}>{explanation}</div>
                    </details>
                    );
                })}
                {!hasPenalties && (
                     <div className={styles.checkItem}>
                     <div className={styles.checkInfo}>
                         <span className={styles.checkLabel}>No Ethical Flags</span>
                         <span className={styles.checkDetail}>Business operates within ethical boundaries.</span>
                     </div>
                     <div className={styles.checkStatus}>
                          <span className={styles.scoreBadge}>Full Points</span>
                     </div>
                 </div>
                )}
            </div>
            </div>
        );
    }

    const section = (category === 'quantitative' ? quantData : qualData) as QuantitativeBreakdown | QualitativeBreakdown | undefined;
    if (!section || !section.blocks) return <div className={styles.empty}>No details available.</div>;

    return (
      <div className={styles.listContainer}>
        {Object.entries(section.blocks).map(([blockKey, block]) => (
          <div key={blockKey} className={styles.categoryGroup}>
            <div className={styles.categoryHeader}>
              <span className={styles.categoryTitle}>{normalizeLabel(blockKey, finalDrStr)}</span>
              <span className={styles.categoryScore}>
                {block.points} / {block.max_points}
              </span>
            </div>
            {Object.entries(block.components).map(([compKey, comp]) => {
                if (typeof comp !== 'object' || comp === null) return null;
                const c = comp as CheckComponent;
                
                const valueRaw = c.value ?? c.value_pp;
                if (!('points' in c)) return null;

                const isExempt = (c as any).note === "industry_exempt";
                const isPass = c.points > 0;
                const statusClass = c.points === c.max_points ? styles.pass : c.points > 0 ? styles.neutral : styles.fail;
                const icon = c.points === c.max_points ? "✓" : c.points > 0 ? "−" : "✕";
                const valueColor = isExempt ? '#3b82f6' : c.points === c.max_points ? '#10b981' : c.points > 0 ? '#f59e0b' : '#ef4444';

                const displayValue = formatValue(valueRaw, compKey);
                
                // Get trend data if available
                const trend = getTrendData(financialData, compKey, isFinance, c);

              return (
                <div key={compKey} className={styles.checkItem}>
                  <div className={styles.checkInfo}>
                    <span className={styles.checkLabel}>
                      {normalizeLabel(compKey, finalDrStr, c)}
                      {category === "quantitative" && (
                        <InfoTooltip 
                           label={normalizeLabel(compKey, finalDrStr, c)} 
                           compKey={compKey} 
                           data={financialData} 
                           comp={c}
                        />
                      )}
                    </span>
                    <div className={styles.valueRow}>
                        {valueRaw !== undefined && valueRaw !== null ? (
                            <span style={{ fontSize: '1.1em', fontWeight: 700, color: valueColor }}>
                                {displayValue}
                            </span>
                        ) : null}
                        
                        {trend && (
                            <Sparkline 
                                data={trend.data} 
                                color={valueColor} 
                                isPercent={trend.isPercent} 
                                title={trend.title}
                            />
                        )}
                        
                    </div>
                  </div>
                   <div className={styles.checkStatus}>
                       {isExempt ? (
                           <span style={{ fontSize: '11px', fontWeight: 700, color: 'var(--chart-blue, #3b82f6)', background: 'var(--background, #eff6ff)', border: '1px solid var(--border-color, #bfdbfe)', borderRadius: '6px', padding: '2px 8px' }}>Exempt</span>
                       ) : null}
                       <span className={styles.scoreBadge}>
                           {c.points < 0 ? `- ${Math.abs(c.points)}` : c.points} / {c.max_points}
                       </span>
                  </div>
                </div>
              );
            })}
          </div>
        ))}
      </div>
    );
  };

  const modalContent = (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <div className={styles.header}>
            <div className={styles.titleGroup}>
                <div className={styles.title}>Conviction Analysis Details</div>
                <div className={styles.subtitle}>
                    Total Score : <span style={{color: 'var(--link-color, #0f4dbc)', fontWeight: 700}}>{score ?? "—"} / 100</span>
                </div>
            </div>
          <button className={styles.closeButton} onClick={onClose} title="Close">
            <HoverLottieIcon animationData={exitAnimation} width={28} height={28} speed={1.8} />
          </button>
        </div>

        <div className={styles.body}>
            <div className={styles.contentGrid}>
                {/* Left Column: Radar Chart */}
                <div className={styles.chartSection}>
                    <div className={styles.chartTitle}>Score Balance</div>
                    <div style={{ width: '100%', height: 350 }}>
                    <ResponsiveContainer width="100%" height="100%">
                        <RadarChart cx="50%" cy="50%" outerRadius="75%" data={chartData}>
                        <PolarGrid />
                        <PolarAngleAxis dataKey="subject" tick={<RadarTick />} />
                        <PolarRadiusAxis angle={30} domain={[0, 100]} tick={false} axisLine={false} />
                        <Radar
                            name="Score %"
                            dataKey="A"
                            stroke="var(--link-color, #0f4dbc)"
                            fill="var(--link-color, #0f4dbc)"
                            fillOpacity={0.5}
                        />
                        <Tooltip content={<CustomTooltip />} />
                        </RadarChart>
                    </ResponsiveContainer>
                    </div>
                </div>

                {/* Right Column: Detailed List */}
                <div className={styles.detailsSection}>
                    <div className={styles.tabs}>
                        <button 
                            className={`${styles.tab} ${activeTab === 'quantitative' ? styles.active : ''}`}
                            onClick={() => setActiveTab('quantitative')}
                        >
                            Quant ({quantTotal}/{quantMax})
                        </button>
                        <button 
                            className={`${styles.tab} ${activeTab === 'qualitative' ? styles.active : ''}`}
                            onClick={() => setActiveTab('qualitative')}
                        >
                            Qual ({qualTotal}/{qualMax})
                        </button>
                        <button 
                            className={`${styles.tab} ${activeTab === 'ethical' ? styles.active : ''}`}
                            onClick={() => setActiveTab('ethical')}
                        >
                            Ethical ({ethTotal}/{ethMax})
                        </button>
                    </div>
                    {renderCheckList(activeTab)}
                </div>
            </div>
        </div>
      </div>
    </div>
  );

  return createPortal(modalContent, document.body);
};
