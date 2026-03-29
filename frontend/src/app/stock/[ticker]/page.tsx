import type { ReactNode, CSSProperties } from "react";
import {
  cleanText,
  formatPercent,
  formatPercentFromRatio,
  formatRatio,
} from "./valuation-formatters";
import { ValuationInputsPanel } from "./ValuationInputsPanel";
import { NAVTooltip } from "./NAVTooltip";
import { BackLink } from "./BackLink";
import { SearchBox } from "@/components/SearchBox";
import { UserProfileDropdown } from "@/components/UserProfileDropdown";
import { ConvictionWidget } from "./ConvictionWidget";
import { StockLogo } from "@/components/StockLogo";
import RevenueBreakdownChart from "./RevenueBreakdownChart";
import styles from "./stock.module.css";
import { getDetailedStockInfo } from "@/lib/stocks-service";
import { Castle, CircleUserRound, AlertTriangle, Briefcase, Search, Coins, Sunrise, Star, ShieldCheck, Banknote, Target } from "lucide-react";

type StockInfo = {
  ticker: string;
  company_name?: string;
  sector?: string;
  industry?: string;
  industry_group?: string;
  logo_url?: string | null;
};

type AnalysisResult = {
  conviction_score?: number | null;
  margin_of_safety?: number | null;
  current_price?: number | null;
  intrinsic_value_estimate?: number | null;
  intrinsic_value_reason?: string | null;
  ai_recommendation_summary?: string | null;
  moat_rating?: string | null;
  key_risks?: string | null;
  ai_reasoning?: string | null;
  portfolio_directive?: unknown;
  checklist_details?: unknown;
};

type ConvictionBreakdown = {
  final_score?: number | null;
  quantitative?: {
    total?: number | null;
    max_points?: number | null;
    blocks?: Record<string, unknown> | null;
  } | null;
  qualitative?: {
    total?: number | null;
    max_points?: number | null;
    blocks?: Record<string, unknown> | null;
  } | null;
  ethical?: {
    total?: number | null;
    max_points?: number | null;
    components?: Record<string, unknown> | null;
  } | null;
  final_dr?: number | null;
  // Legacy support (optional)
  phase1?: unknown;
  phase2?: unknown;
  weights?: unknown;
};

type ChecklistDetails = {
  valuation_insights?: ValuationInsights | null;
  conviction_breakdown?: ConvictionBreakdown | null;
  [key: string]: unknown;
} | null;

type FinancialRow = {
  report_date: string;
  total_revenue?: number | null;
  revenue_growth?: number | null;
  eps_growth_diluted?: number | null;
  net_income?: number | null;
  net_profit_margin?: number | null;
  eps_diluted?: number | null;
  gross_margin?: number | null;
  free_cash_flow?: number | null;
  fcf_margin?: number | null;
  roe?: number | null;
  roic?: number | null;
  debt_to_equity?: number | null;
  payout_ratio?: number | null;
  interest_coverage?: number | null;
};

type SegmentBreakdownRow = {
  segment_group?: string | null;
  segment_original_name?: string | null;
  revenue_amount?: number | null;
  revenue_amount_raw?: number | null;
  revenue_unit?: string | null;
  ai_confidence?: number | null;
};

type SegmentBreakdown = {
  period?: string | null;
  period_type?: string | null;
  rows?: SegmentBreakdownRow[] | null;
};

type SegmentRevenuePayload = {
  product?: SegmentBreakdown | null;
  geo?: SegmentBreakdown | null;
};

type PortfolioPosition = {
  quantity?: number | null;
  current_pct?: number | null;
  target_pct?: number | null;
  current_value?: number | null;
};

type SecFilingEntry = {
  report_date?: string | null;
  filing_date?: string | null;
  form_type?: string | null;
  sec_url?: string | null;
};

type SystemStatusMap = {
  status?: Record<string, unknown> | null;
  phase1?: Record<string, unknown> | null;
  phase2?: Record<string, unknown> | null;
};

type ApiResponse = {
  stockInfo: StockInfo | null;
  analysisResult: AnalysisResult | null;
  financialData: FinancialRow[];
  segmentRevenue?: SegmentRevenuePayload | null;
  portfolioPosition?: PortfolioPosition | null;
  documentSummary?: DocumentSummary | null;
  secFilings?: SecFilingEntry[] | null;
  systemStatus?: SystemStatusMap | null;
};

type DiscountRateAdjustment = {
  code?: string;
  label?: string;
  delta?: number | null;
  type?: string;
};

type DiscountRateInsight = {
  base_rate?: number | null;
  final_rate?: number | null;
  adjustments?: DiscountRateAdjustment[] | null;
  explanation?: string | null;
};

type ValuationInsights = {
  discount_rate?: DiscountRateInsight | null;
  growth_assumptions?: Record<string, GrowthAssumption | null> | null;
  models?: Record<string, ValuationModelDetail | null> | null;
  model_used?: string | null;
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
  discount_rate?: number | null;
  projection_years?: number | null;
  inputs?: Record<string, unknown> | null;
  projections?: ValuationProjectionRow[] | null;
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
};

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

type MetricCard = {
  key: string;
  label: string;
  icon: ReactNode;
  valuePrimary: string;
  valueSecondary?: ReactNode;
  valueColor?: string;
  footnote?: string;
  detail?: ReactNode;
  detailLabel?: string;
  action?: ReactNode;
};

type DocumentSummary = Record<string, unknown>;


type QualityItem = {
  label: string;
  detail?: string;
};

type QualityCard = {
  key: string;
  icon: ReactNode;
  title: string;
  subtitle?: string;
  items: QualityItem[];
};

const clamp = (value: number, min = 0, max = 1) =>
  Math.min(max, Math.max(min, value));

const safeNumber = (value: unknown): number | null => {
  if (value === null || value === undefined) return null;
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim().length > 0) {
    const parsed = Number(value);
    if (Number.isFinite(parsed)) {
      return parsed;
    }
  }
  return null;
};

const parseRiskList = (raw: string | null | undefined): string[] => {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed
        .map((item) => {
          if (typeof item === "string") return item.trim();
          if (item && typeof item === "object" && "note" in item) {
            const note = (item as { note?: unknown }).note;
            return typeof note === "string" ? note.trim() : "";
          }
          return typeof item === "number" ? String(item) : "";
        })
        .filter((entry) => entry.length > 0);
    }
  } catch {
    /* ignore parse failure */
  }
  return raw
    .replace(/^\||$/g, "")
    .split(/[\n•;,]+/) 
    .map((entry) => entry.replace(/^"+|"+$/g, "").trim())
    .filter((entry) => entry.length > 0);
};

const BUSINESS_RISK_EXPLANATIONS: Record<string, string> = {
  ZERO_SUM_ETHICAL:
    "ZERO_SUM_ETHICAL : Business model depends on counterparties absorbing losses or adverse outcomes.",
  ZERO_SUM_GAME:
    "ZERO_SUM_GAME : Growth relies on displacing entrenched rivals in mature, finite-share markets.",
  REGULATORY_UNPREDICTABLE:
    "REGULATORY_UNPREDICTABLE : Material outcomes depend on shifting, hard-to-predict policy or licensing regimes.",
  GEOPOLITICAL_RISK:
    "GEOPOLITICAL_RISK : Operations, supply chain, or demand hinge on regions exposed to geopolitical tension.",
  HYPER_COMPETITIVE:
    "HYPER_COMPETITIVE : Aggressive incumbents and new entrants pressure pricing, margins, and product differentiation.",
};

const GOVERNANCE_FLAG_EXPLANATIONS: Record<string, string> = {
  "POOR_MD&A":
    "POOR_MD&A : Management discussion and analysis omits clear drivers, key metrics, or reconciliations.",
  POOR_MDA:
    "POOR_MD&A : Management discussion and analysis omits clear drivers, key metrics, or reconciliations.",
  "AGGRESSIVE_M&A":
    "AGGRESSIVE_M&A : Rapid deal cadence risks dilution, integration strain, or value-destructive capital allocation.",
  OPAQUE_DISCLOSURE:
    "OPAQUE_DISCLOSURE : Critical operating or financial disclosures are missing or inconsistently presented.",
  INSTITUTIONAL_IMPERATIVE:
    "INSTITUTIONAL_IMPERATIVE : Management follows industry fads or peers despite weak economic justification.",
};

const explainTag = (
  raw: string,
  mapping: Record<string, string>,
): string => {
  const trimmed = raw.trim();
  if (trimmed.length === 0) return trimmed;
  if (trimmed.includes(":")) return trimmed;
  const mapped = mapping[trimmed];
  if (typeof mapped === "string" && mapped.length > 0) {
    return mapped.replace(/^[^:：]+[:：]\s*/, "").trim() || mapped;
  }
  return trimmed;
};

const normalizeHeading = (input: string): string =>
  input
    .replace(/[:：]/g, "")
    .replace(/\s+/g, " ")
    .replace(/[^A-Za-z0-9ก-๙&/+\- ]/g, "")
    .trim()
    .toLowerCase();

const stripLeadingLabel = (label: string, detail: string): string => {
  const trimmedDetail = detail.trim();
  if (trimmedDetail.length === 0) {
    return trimmedDetail;
  }
  const match = trimmedDetail.match(/^(.+?)\s*[:：]\s*(.*)$/);
  if (!match) {
    return trimmedDetail;
  }
  const [, heading, body] = match;
  if (normalizeHeading(heading) === normalizeHeading(label)) {
    return body.trim();
  }
  return trimmedDetail;
};

const canonicalizeTag = (input: string | null | undefined): string | null => {
  if (!input) return null;
  const cleaned = input
    .toString()
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
    .toUpperCase();
  return cleaned.length > 0 ? cleaned : null;
};

const RISK_KEYWORDS: Record<string, RegExp[]> = {
  REGULATORY_UNPREDICTABLE: [
    /regulat/i,
    /export/i,
    /compliance/i,
    /ควบคุม/,
    /license/i,
    /อนุญาต/,
    /control/i,
  ],
  GEOPOLITICAL_RISK: [
    /geopolit/i,
    /china/i,
    /taiwan/i,
    /สงคราม/,
    /democrat/i,
    /sanction/i,
  ],
  HYPER_COMPETITIVE: [
    /compet/i,
    /คู่แข่ง/,
    /rival/i,
    /margin/i,
    /intense competition/i,
  ],
  ZERO_SUM_GAME: [/zero[-\s]?sum/i, /win[-\s]?loss/i],
  ZERO_SUM_ETHICAL: [/ethic/i, /moral/i, /ผลประโยชน์/, /ขัดแย้ง/],
};

const detailSignature = (value: string | null | undefined): string | null => {
  if (!value) return null;
  const normalized = value
    .toLowerCase()
    .replace(/[:：]/g, " ")
    .replace(/[^a-z0-9ก-๙\s]/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
  return normalized.length > 0 ? normalized : null;
};

const extractNarrativeBody = (input: string): string =>
  input.replace(/^[^:：]+[:：]\s*/, "").trim();

const gatherRiskNarratives = (
  summary: DocumentSummary | null,
  analysis: AnalysisResult | null,
): string[] => {
  const narratives = new Set<string>();
  const risksField = getSummaryField<{ value?: unknown }>(summary, "risks");
  extractStringArray(risksField?.value).forEach((entry) => {
    const cleaned = extractNarrativeBody(entry);
    if (cleaned.length > 0) {
      narratives.add(cleaned);
    }
  });
  parseRiskList(analysis?.key_risks ?? null).forEach((entry) => {
    const cleaned = extractNarrativeBody(entry);
    if (cleaned.length > 0) {
      narratives.add(cleaned);
    }
  });
  return Array.from(narratives);
};

const findTagNarrative = (
  tag: string | null,
  label: string | null,
  narratives: string[],
  claimedNarratives?: Set<string>,
): string | null => {
  const canonical = canonicalizeTag(tag);
  const keywordGroup =
    (canonical && RISK_KEYWORDS[canonical]) || (canonical && RISK_KEYWORDS[tag ?? ""]);
  const loweredLabel = label ? label.toLowerCase() : null;
  for (const narrative of narratives) {
    if (claimedNarratives && claimedNarratives.has(narrative)) continue;
    const loweredNarrative = narrative.toLowerCase();
    let matched = false;
    if (canonical && loweredNarrative.includes(canonical.toLowerCase())) {
      matched = true;
    }
    if (!matched && Array.isArray(keywordGroup)) {
      matched = keywordGroup.some((pattern) => pattern.test(narrative));
    }
    if (!matched && loweredLabel) {
      matched = loweredNarrative.includes(loweredLabel);
    }
    if (matched) {
      if (claimedNarratives) claimedNarratives.add(narrative);
      return narrative;
    }
  }
  return null;
};

const extractRiskLabel = (detail: string) => {
  const cleaned = detail.trim();
  const sanitized = cleaned
    .replace(/\(.*\)/g, "")
    .replace(/\s+/g, " ")
    .trim();
  const byDelimiter =
    sanitized
      .split(/[:–—-]/)
      .map((part) => part.trim())
      .find((part) => part.length > 0) ??
    sanitized
      .split(/[.]/)
      .map((part) => part.trim())
      .find((part) => part.length > 0) ??
    sanitized;
  return byDelimiter.length > 64 ? `${byDelimiter.slice(0, 61)}…` : byDelimiter;
};

const shortenText = (input: string, limit = 160) => {
  const trimmed = input.trim();
  if (trimmed.length <= limit) return trimmed;
  return `${trimmed.slice(0, limit).trim()}…`;
};

const sentenceList = (input: string | null | undefined, limit = 160) => {
  if (!input) return [];
  const sentences = input
    .split(/(?<=[.!?])\s+/) 
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 0);
  if (sentences.length === 0) {
    return [shortenText(input, limit)];
  }
  return sentences.slice(0, 2).map((sentence) => sentence);
};

const dedupeList = (values: string[]) =>
  Array.from(new Set(values.filter((entry) => entry.trim().length > 0)));

const dedupeQualityItems = (items: QualityItem[]): QualityItem[] => {
  const map = new Map<string, QualityItem>();

  for (const item of items) {
    let baseKey = item.label;
    if (item.label.includes(" ระดับ ")) {
      baseKey = item.label.split(" ระดับ ")[0].trim();
    } else if (item.label.includes(" : ")) {
      baseKey = item.label.split(" : ")[0].trim();
    }
    
    // Normalize case to catch duplicates like "Cybersecurity Threats" vs "Cybersecurity threats"
    baseKey = baseKey.toLowerCase();

    if (map.has(baseKey)) {
      const existing = map.get(baseKey)!;
      if (item.detail) {
        if (!existing.detail) {
          existing.detail = item.detail;
        } else if (!existing.detail.includes(item.detail)) {
          existing.detail = `${existing.detail}\n\n${item.detail}`;
        }
      }
    } else {
      map.set(baseKey, { ...item });
    }
  }

  return Array.from(map.values());
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const parseISODate = (value: unknown): Date | null => {
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : new Date(value.getTime());
  }
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (!trimmed) return null;
    const parsed = new Date(trimmed);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }
  return null;
};

const formatPhaseDate = (date: Date | null): string | null => {
  if (!date) return null;
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, "0");
  const day = `${date.getDate()}`.padStart(2, "0");
  return `${year} - ${month} - ${day}`;
};

type PhaseDisplay = {
  phaseLabel: string;
  dateLabel: string | null;
};

const derivePhaseDisplay = (
  status: SystemStatusMap | null | undefined,
): PhaseDisplay | null => {
  const statusKeys: Array<keyof SystemStatusMap> = ["status", "phase2", "phase1"];
  for (const key of statusKeys) {
    const raw = status?.[key];
    if (!isRecord(raw)) continue;

    const phaseSource =
      typeof raw.phase === "string"
        ? raw.phase
        : typeof raw.status === "string"
        ? raw.status
        : key;

    const normalizedPhase = String(phaseSource).trim();
    let phaseLabel = normalizedPhase.toUpperCase();
    
    if (key === "status" || normalizedPhase.toLowerCase() === "standard") {
        phaseLabel = "UPDATED";
    } else {
        const phaseMatch = /phase\s*(\d+)/i.exec(normalizedPhase);
        if (phaseMatch?.[1]) {
            phaseLabel = `PHASE ${phaseMatch[1]}`;
        }
    }

    const candidateFields = [
      "analysis_date",
      "analysisDate",
      "analysis_completed_at",
      "analysisCompletedAt",
      "analysis_at",
      "analysisAt",
      "last_analysis_date",
      "lastAnalysisDate",
      "latest_filing_processed_at",
      "latestFilingProcessedAt",
      "latest_filing_date",
      "latestFilingDate",
      "next_full_analysis_after",
      "nextFullAnalysisAfter",
      "last_run_at",
      "lastRunAt",
      "checked_at",
      "checkedAt",
      "updated_at",
      "updatedAt",
      "last_updated",
      "lastUpdated",
    ] as const;
    let parsedDate: Date | null = null;
    for (const field of candidateFields) {
      if (field in raw) {
        const candidateValue = raw[field];
        parsedDate = parseISODate(candidateValue);
        if (parsedDate) break;
      }
    }

    const dateLabel = formatPhaseDate(parsedDate);
    return { phaseLabel, dateLabel };
  }
  return null;
};

type FilingLink = {
  label: string;
  href: string;
};

const buildTenKFilingLinks = (
  filings: SecFilingEntry[] | null | undefined,
): FilingLink[] => {
  if (!Array.isArray(filings)) return [];
  const seen = new Set<string>();
  return filings
    .map((filing) => {
      if (!filing) return null;
      const url =
        typeof filing.sec_url === "string" ? filing.sec_url.trim() : "";
      if (!url) return null;
      const dateValue =
        parseISODate(filing.report_date) ?? parseISODate(filing.filing_date);
      const yearLabel = dateValue ? `${dateValue.getFullYear()}` : null;
      const label =
        (yearLabel && yearLabel.trim().length > 0
          ? yearLabel
          : typeof filing.form_type === "string"
          ? filing.form_type.trim()
          : "10-K") || "10-K";
      const dedupeKey = `${label}|${url}`;
      if (seen.has(dedupeKey)) {
        return null;
      }
      seen.add(dedupeKey);
      return { label, href: url };
    })
    .filter((entry): entry is FilingLink => Boolean(entry));
};

const getSummaryField = <T,>(
  summary: DocumentSummary | null,
  key: string,
): T | undefined => {
  if (!summary) return undefined;
  const field = summary[key];
  if (field === undefined || field === null) return undefined;
  return field as T;
};

const extractString = (input: unknown): string | null => {
  if (!input) return null;
  if (typeof input === "string") {
    const value = input.trim();
    return value.length > 0 ? value : null;
  }
  if (typeof input === "object" && input !== null && "value" in input) {
    return extractString((input as { value?: unknown }).value);
  }
  return null;
};

const extractStringArray = (input: unknown): string[] => {
  if (!input) return [];
  if (Array.isArray(input)) {
    return input
      .map((entry) => extractString(entry))
      .filter((entry): entry is string => entry !== null);
  }
  if (typeof input === "object" && input !== null && "value" in input) {
    return extractStringArray((input as { value?: unknown }).value);
  }
  return [];
};

const toQualityItemsFromSentences = (
  sentences: string[],
): QualityItem[] => {
  const unique = dedupeList(
    sentences.map((sentence) => sentence.replace(/\s+/g, " ").trim()),
  );
  return unique.map((sentence) => ({
    label: extractRiskLabel(sentence),
    detail: sentence,
  }));
};

const toMetricHue = (normalized: number) =>
  `hsl(${Math.round(normalized * 120)}, 78%, 34%)`;

const buildRiskCards = (
  summary: DocumentSummary | null,
  additionalRisks: string[],
  excludedDetails?: Set<string>,
): QualityCard[] => {
  const summaryRisksField = getSummaryField<{ value?: unknown }>(
    summary,
    "risks",
  );
  const summaryRisks = Array.isArray(summaryRisksField?.value)
    ? (summaryRisksField?.value as string[])
    : [];

  const combinedRisks = dedupeList([...summaryRisks, ...additionalRisks]);
  const primaryRisks = combinedRisks.slice(0, 3);
  const remainingRisks = combinedRisks.slice(3);

  const businessModelField = getSummaryField<{ value?: string }>(
    summary,
    "business_model",
  );
  const industryAssetField = getSummaryField<{ value?: string; rationale?: string }>(
    summary,
    "INDUSTRY_ASSET",
  );
  const hamSandwichField = getSummaryField<Record<string, unknown>>(
    summary,
    "ham_sandwich_test",
  );

  const institutionalField = getSummaryField<{ evidence?: string }>(
    summary,
    "institutional_imperative_assessment",
  );
  const stockAlignmentField = getSummaryField<{ rationale?: string }>(
    summary,
    "stock_option_alignment",
  );

  const watchpointExtras = [
    ...(institutionalField?.evidence
      ? sentenceList(institutionalField.evidence, 180)
      : []),
    ...(stockAlignmentField?.rationale
      ? sentenceList(stockAlignmentField.rationale, 180)
      : []),
  ];

  const watchpointStrings = dedupeList([...remainingRisks, ...watchpointExtras]);

  const cards: QualityCard[] = [];

  const riskItemsRaw = dedupeQualityItems(
    primaryRisks.map((detail) => ({
      label: extractRiskLabel(detail),
      detail: explainTag(detail.trim(), BUSINESS_RISK_EXPLANATIONS),
    })),
  );
  const riskItems = 
    excludedDetails && excludedDetails.size > 0
      ? riskItemsRaw.filter((item) => {
          const sig = detailSignature(item.detail);
          return !(sig && excludedDetails.has(sig));
        })
      : riskItemsRaw;
  if (riskItems.length > 0) {
    cards.push({
      key: "risks",
      icon: <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />,
      title: "RISKS",
      items: riskItems,
    });
  }

  const businessModelDetail = extractString(businessModelField?.value);
  const industryAssetValue = extractString(industryAssetField?.value);
  const industryAssetRationale = extractString(industryAssetField?.rationale);

  const businessQualityItems: QualityItem[] = [];
  if (businessModelDetail) {
    businessQualityItems.push({
      label: "Business Model Overview",
      detail: businessModelDetail,
    });
  }
  if (industryAssetValue) {
    businessQualityItems.push({
      label: `Asset Profile : ${industryAssetValue}`,
      detail: industryAssetRationale ? industryAssetRationale : undefined,
    });
  } else if (industryAssetRationale) {
    businessQualityItems.push({
      label: "Asset Strategy Rationale",
      detail: industryAssetRationale,
    });
  }
  const hamValue = extractString(hamSandwichField);
  const hamRationale = hamSandwichField
    ? extractString(hamSandwichField["rationale"])
    : null;
  if (hamValue) {
    businessQualityItems.push({
      label: `Ham Sandwich Test : ${hamValue}`,
      detail: hamRationale ? hamRationale : undefined,
    });
  } else if (hamRationale) {
    businessQualityItems.push({
      label: "Ham Sandwich Test Rationale",
      detail: hamRationale,
    });
  }

  const businessItems = dedupeQualityItems(businessQualityItems);
  if (businessItems.length > 0) {
    cards.push({
      key: "business",
      icon: <Briefcase className="w-5 h-5 text-blue-500 shrink-0" />,
      title: "BUSINESS MODEL & INDUSTRY PROFILE",
      items: businessItems,
    });
  }

  const watchpointItemsRaw = dedupeQualityItems(
    watchpointStrings.map((detail) => ({
      label: extractRiskLabel(detail),
      detail: explainTag(detail.trim(), BUSINESS_RISK_EXPLANATIONS),
    })),
  );
  const watchpointItems =
    excludedDetails && excludedDetails.size > 0
      ? watchpointItemsRaw.filter((item) => {
          const detailSig = detailSignature(item.detail);
          if (detailSig && excludedDetails.has(detailSig)) {
            return false;
          }
          const labelSig = normalizeHeading(item.label);
          if (labelSig === normalizeHeading("Geopolitical and Regulatory Risks")) {
            return false;
          }
          return true;
        })
      : watchpointItemsRaw.filter((item) => {
          const labelSig = normalizeHeading(item.label);
          if (labelSig === normalizeHeading("Geopolitical and Regulatory Risks")) {
            return false;
          }
          return true;
        });

  if (watchpointItems.length > 0) {
    cards.push({
      key: "watchpoints",
      icon: <Search className="w-5 h-5 text-gray-500 shrink-0" />,
      title: "OTHER WATCHPOINTS",
      items: watchpointItems,
    });
  }

  return cards;
};

const buildQualityCards = (
  summary: DocumentSummary | null,
  moatHeading: string,
  moatSummary: string,
  moatEntries: QualityItem[],
): QualityCard[] => {
  const cards: QualityCard[] = [];

  const moatItems = 
    moatEntries.length > 0
      ? moatEntries
      : moatSummary
      ? [{ label: moatSummary }]
      : [];

  if (moatHeading || moatItems.length > 0) {
    cards.push({
      key: "moat",
      icon: <Castle className="w-5 h-5 text-indigo-500 shrink-0" />,
      title: "MOAT",
      subtitle: moatHeading,
      items: moatItems,
    });
  }

  const managementField = getSummaryField<Record<string, unknown>>(
    summary,
    "management_quality",
  );
  const leadershipItems: QualityItem[] = [];
  if (managementField) {
    const attributes: Record<string, string> = {
      intelligence: "Intelligence",
      energy: "Energy",
      rationality: "Rationality",
    };

    const managementNotes = extractString(managementField["notes"]);

    Object.entries(attributes).forEach(([key, label]) => {
      const fieldObj = managementField[key];
      const value = extractString(fieldObj);
      const rat = fieldObj && typeof fieldObj === "object" ? extractString((fieldObj as Record<string,unknown>)["rationale"]) : null;
      if (value) {
        leadershipItems.push({
          label: `${label} : ${value}`,
          detail: rat ? rat : (key === "intelligence" ? (managementNotes ?? undefined) : undefined),
        });
      }
    });

    if (managementNotes && !leadershipItems.some(i => i.label.includes("Intelligence"))) {
       leadershipItems.push({ label: "Leadership Notes", detail: managementNotes });
    }
  }

  const stockAlignmentField = getSummaryField<Record<string, unknown>>(
    summary,
    "stock_option_alignment",
  );
  if (stockAlignmentField) {
    const rating = extractString(stockAlignmentField["rating"]);
    const rationale = extractString(stockAlignmentField["rationale"]);
    if (rating) {
      leadershipItems.push({
        label: `Incentive Alignment : ${rating}`,
        detail: rationale ?? undefined,
      });
    } else if (rationale) {
      leadershipItems.push({ label: "Incentive Alignment Details", detail: rationale });
    }
  }
  const institutionalField = getSummaryField<Record<string, unknown>>(
    summary,
    "institutional_imperative_assessment",
  );
  if (institutionalField) {
    const rating = extractString(institutionalField["rating"]);
    const evidence = extractString(institutionalField["evidence"]);
    if (rating) {
      leadershipItems.push({
        label: `Institutional Imperative : ${rating}`,
        detail: evidence ?? undefined,
      });
    } else if (evidence) {
      leadershipItems.push({ label: "Institutional Imperative Details", detail: evidence });
    }
  }
  const governanceFlagsField = getSummaryField<Record<string, unknown>>(
    summary,
    "governance_flags",
  );
  if (governanceFlagsField) {
    const flags = extractStringArray(governanceFlagsField["value"]);
    if (flags.length > 0) {
      flags.forEach((flag) =>
        leadershipItems.push({
          label: extractRiskLabel(flag),
          detail: explainTag(flag, GOVERNANCE_FLAG_EXPLANATIONS),
        }),
      );
    } else {
      leadershipItems.push({
        label: "No governance flags reported",
      });
    }
  }
  const managementCandorField = getSummaryField<Record<string, unknown>>(
    summary,
    "management_candor",
  );
  const managementCandorValue = extractString(managementCandorField);
  const managementCandorRationale = managementCandorField
    ? extractString(managementCandorField["rationale"])
    : null;
  if (managementCandorValue) {
    leadershipItems.push({
      label: `Management Candor : ${managementCandorValue}`,
      detail: managementCandorRationale ?? undefined,
    });
  } else if (managementCandorRationale) {
    leadershipItems.push({ label: "Management Candor Rationale", detail: managementCandorRationale });
  }
  if (leadershipItems.length > 0) {
    cards.push({
      key: "leadership",
      icon: <CircleUserRound className="w-5 h-5 text-emerald-500 shrink-0" />,
      title: "LEADERSHIP & GOVERNANCE",
      items: dedupeQualityItems(leadershipItems),
    });
  }

  const pricingField = getSummaryField<Record<string, unknown>>(
    summary,
    "pricing_power",
  );

  const pricingItems: QualityItem[] = [];
  let pricingDetail = "";
  if (pricingField) {
    const rating = extractString(pricingField["rating"]);
    const evidence = extractString(pricingField["evidence"]);
    if (rating) {
      pricingItems.push({
        label: `Pricing Power : ${rating}`,
        detail: evidence ?? undefined,
      });
    } else if (evidence) {
      pricingDetail = evidence;
    }
  }
  const pricingEvidenceField = getSummaryField<Record<string, unknown>>(
    summary,
    "pricing_power_evidence",
  );
  const pricingEvidence = extractString(pricingEvidenceField);
  if (pricingEvidence) {
    if (pricingItems.length > 0 && !pricingItems[0].detail) {
        pricingItems[0].detail = pricingEvidence;
    } else {
        pricingItems.push({ label: "Pricing Power Evidence", detail: pricingEvidence });
    }
  } else if (pricingDetail) {
      pricingItems.push({ label: "Pricing Power Evidence", detail: pricingDetail });
  }
  if (pricingItems.length > 0) {
    cards.push({
      key: "pricing",
      icon: <Coins className="w-5 h-5 text-yellow-500 shrink-0" />,
      title: "PRICING POWER",
      items: pricingItems,
    });
  }

  const prospectsField = getSummaryField<Record<string, unknown>>(
    summary,
    "long_term_prospects",
  );
  const prospectsValue = extractString(prospectsField);
  const prospectsRationale = prospectsField
    ? extractString(prospectsField["rationale"])
    : null;
  const prospectsItems: QualityItem[] = [];
  if (prospectsValue) {
    prospectsItems.push(
      ...toQualityItemsFromSentences(sentenceList(prospectsValue, 200)),
    );
  }
  if (prospectsRationale) {
    prospectsItems.push(
      ...toQualityItemsFromSentences(sentenceList(prospectsRationale, 200)),
    );
  }
  if (prospectsItems.length > 0) {
    cards.push({
      key: "prospects",
      icon: <Sunrise className="w-5 h-5 text-orange-500 shrink-0" />,
      title: "LONG-TERM PROSPECTS",
      items: dedupeQualityItems(prospectsItems),
    });
  }

  return cards;
};

const getConvictionColor = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return undefined;
  }
  const normalized = clamp(value / 100, 0, 1);
  return toMetricHue(normalized);
};

const getMarginColor = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return undefined;
  }
  if (value < 0) {
    return "hsl(8, 72%, 48%)";
  }
  const normalized = clamp(value / 0.5, 0, 1); // map 0..50% to 0..1
  return toMetricHue(0.5 + normalized / 2);
};

const getPriceColor = () => "hsl(212, 82%, 34%)";

const getTargetColor = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return undefined;
  }
  return "hsl(200, 82%, 34%)";
};

const parseDirective = (raw: unknown):
  | { label?: string; target_pct?: number; notes?: string }
  | null => {
  if (!raw) return null;
  if (typeof raw === "string") {
    try {
      return JSON.parse(raw);
    } catch (error) {
      console.warn("Failed to parse directive string", error);
      return null;
    }
  }
  if (typeof raw === "object") {
    return raw as { label?: string; target_pct?: number; notes?: string };
  }
  return null;
};

const buildSegmentDataset = (
  breakdown: SegmentBreakdown | null | undefined,
  title: string,
  subtitle: string,
): ChartDataset | null => {
  if (!breakdown || !Array.isArray(breakdown.rows) || breakdown.rows.length === 0) {
    return null;
  }
  const aggregation = new Map<string, number>();
  breakdown.rows.forEach((row) => {
    if (!row) return;
    const label =
      (row.segment_group ?? row.segment_original_name ?? "Other").trim() || "Other";
    const amount =
      safeNumber(row.revenue_amount) ?? safeNumber(row.revenue_amount_raw);
    if (amount === null || !Number.isFinite(amount) || amount === 0) {
      return;
    }
    aggregation.set(label, (aggregation.get(label) ?? 0) + amount);
  });
  const data = Array.from(aggregation.entries())
    .map(([name, value]) => ({ name, value }))
    .filter((entry) => entry.value !== 0)
    .sort((a, b) => b.value - a.value);
  if (data.length === 0) return null;
  const periodLabel = (() => {
    if (!breakdown.period) return null;
    const dt = new Date(breakdown.period);
    if (Number.isNaN(dt.getTime())) {
      return breakdown.period;
    }
    return String(dt.getFullYear());
  })();
  return {
    title,
    subtitle,
    periodLabel,
    periodType: breakdown.period_type ?? null,
    data,
  };
};

const buildSummaryRevenueDataset = (
  entries: unknown,
  labelKey: "segment" | "region",
  title: string,
  subtitle: string,
): ChartDataset | null => {
  if (!Array.isArray(entries)) return null;
  const rows = (entries as unknown[]).filter(
    (row): row is Record<string, unknown> =>
      row !== null && typeof row === "object",
  );
  if (rows.length === 0) return null;

  const years = rows
    .map((row) => safeNumber(row.year))
    .filter((year): year is number => year !== null);
  if (years.length === 0) return null;

  const latestYear = Math.max(...years);
  const latestRows = rows.filter(
    (row) => safeNumber(row.year) === latestYear,
  );

  const data = latestRows
    .map((row) => {
      const labelRaw = row[labelKey];
      const label =
        typeof labelRaw === "string"
          ? labelRaw.trim() || "Other"
          : "Other";

      const valueField = row.value;
      let amount = safeNumber(valueField);
      if (amount === null && valueField && typeof valueField === "object") {
        amount = safeNumber(
          (valueField as { value?: unknown }).value,
        );
      }
      if (amount === null || !Number.isFinite(amount) || amount === 0) {
        return null;
      }
      if (valueField && typeof valueField === "object") {
        const unitRaw = (valueField as { unit?: unknown }).unit;
        if (typeof unitRaw === "string") {
          const unit = unitRaw.toLowerCase();
          if (unit.includes("billion")) {
            amount *= 1_000_000_000;
          } else if (unit.includes("million")) {
            amount *= 1_000_000;
          } else if (unit.includes("thousand")) {
            amount *= 1_000;
          }
        }
      }
      return { name: label, value: amount };
    })
    .filter((entry): entry is ChartDatum => entry !== null)
    .sort((a, b) => b.value - a.value);

  if (data.length === 0) return null;

  return {
    title,
    subtitle,
    periodLabel: String(latestYear),
    periodType: "annual",
    data,
  };
};

const formatQuantity = (value: number | null | undefined) => {
  if (value === null || value === undefined) return null;
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return null;
  if (numeric >= 1_000_000_000) {
    return `${(numeric / 1_000_000_000).toFixed(2)}B`;
  }
  if (numeric >= 1_000_000) {
    return `${(numeric / 1_000_000).toFixed(2)}M`;
  }
  if (numeric >= 1_000) {
    return `${(numeric / 1_000).toFixed(1)}K`;
  }
  return numeric.toLocaleString(undefined, {
    maximumFractionDigits: numeric % 1 === 0 ? 0 : 2,
  });
};

type MoatStrengthData = {
  level: "สูง" | "กลาง" | "ต่ำ";
  score: 1 | 2 | 3;
  tone: "strong" | "medium" | "weak";
  heading: string;
  summary: string;
  highlights: string[];
};

const parseChecklistDetails = (raw: unknown): ChecklistDetails => {
  if (!raw) return null;

  let payload: unknown = raw;
  if (typeof raw === "string") {
    try {
      payload = JSON.parse(raw);
    } catch (error) {
      console.warn("Failed to parse checklist_details string", error);
      return null;
    }
  }

  if (typeof payload !== "object" || payload === null) {
    return null;
  }

  return payload as ChecklistDetails;
};

const extractValuationInsights = (
  details: ChecklistDetails,
): ValuationInsights | null => {
  if (!details) return null;
  const insights = details.valuation_insights;
  return insights && typeof insights === "object" ? insights : null;
};

const extractConvictionBreakdown = (
  details: ChecklistDetails,
): ConvictionBreakdown | null => {
  if (!details) return null;
  const breakdown = details.conviction_breakdown;
  return breakdown && typeof breakdown === "object" ? breakdown : null;
};

const formatScoreValue = (value: number) =>
  value % 1 === 0 ? value.toFixed(0) : value.toFixed(1);

type ConvictionGroup = {
  key: string;
  title: string;
  items: { key: string; label: string; value: string }[];
};

const buildConvictionGroups = (
  breakdown: ConvictionBreakdown | null,
): ConvictionGroup[] => {
  if (!breakdown) return [];

  const groups: ConvictionGroup[] = [];
  
  // New Flat Structure
  if (breakdown.quantitative || breakdown.qualitative || breakdown.ethical) {
      const sections: ConvictionGroup["items"] = [];
      
      const quantScore = safeNumber(breakdown.quantitative?.total);
      const quantMax = safeNumber(breakdown.quantitative?.max_points);
      if (quantScore !== null && quantMax !== null) {
        sections.push({
            key: "quant",
            label: "Quantitative",
            value: `${formatScoreValue(quantScore)} / ${formatScoreValue(quantMax)}`
        });
      }

      const qualScore = safeNumber(breakdown.qualitative?.total);
      const qualMax = safeNumber(breakdown.qualitative?.max_points);
      if (qualScore !== null && qualMax !== null) {
        sections.push({
            key: "qual",
            label: "Qualitative",
            value: `${formatScoreValue(qualScore)} / ${formatScoreValue(qualMax)}`
        });
      }

      const ethScore = safeNumber(breakdown.ethical?.total);
      const ethMax = safeNumber(breakdown.ethical?.max_points);
      if (ethScore !== null && ethMax !== null) {
        sections.push({
            key: "ethical",
            label: "Ethical Alignment",
            value: `${formatScoreValue(ethScore)} / ${formatScoreValue(ethMax)}`
        });
      }
      
      if (sections.length > 0) {
          groups.push({
              key: "core_analysis",
              title: "Core Analysis",
              items: sections
          });
      }
      return groups;
  }

  // Fallback to old Phase 1/2 logic if flat structure is missing
  const phase1 = (breakdown as any).phase1 ?? null;
  const phase2 = (breakdown as any).phase2 ?? null;
  const phase1Weights = (breakdown as any).weights?.phase1 ?? {};
  const phase2Weights = (breakdown as any).weights?.phase2 ?? {};

  const sectionsPhase1: ConvictionGroup["items"] = [];
  const phase1QuantScore = safeNumber(phase1?.quantitative?.total);
  const phase1QuantMax =
    safeNumber(phase1?.quantitative?.weight) ?? safeNumber(phase1Weights?.quant);
  if (phase1QuantScore !== null && phase1QuantMax !== null) {
    sectionsPhase1.push({
      key: "phase1-quant",
      label: "Quantitative",
      value: `${formatScoreValue(phase1QuantScore)} / ${formatScoreValue(
        phase1QuantMax,
      )}`,
    });
  }

  const phase1QualScore = safeNumber(phase1?.qualitative?.total);
  const phase1QualMax =
    safeNumber(phase1?.qualitative?.weight) ?? safeNumber(phase1Weights?.qual);
  if (phase1QualScore !== null && phase1QualMax !== null) {
    sectionsPhase1.push({
      key: "phase1-qual",
      label: "Qualitative",
      value: `${formatScoreValue(phase1QualScore)} / ${formatScoreValue(
        phase1QualMax,
      )}`,
    });
  }

  const phase1EthicalScore = safeNumber(phase1?.ethical?.points);
  const phase1EthicalMax =
    safeNumber(phase1?.ethical?.max_points) ?? safeNumber(phase1Weights?.ethical);
  if (phase1EthicalScore !== null && phase1EthicalMax !== null) {
    sectionsPhase1.push({
      key: "phase1-ethical",
      label: "Ethical Alignment",
      value: `${formatScoreValue(phase1EthicalScore)} / ${formatScoreValue(
        phase1EthicalMax,
      )}`,
    });
  }

  const phase1TotalScore = safeNumber(phase1?.total);
  const phase1TotalMax = [phase1QuantMax, phase1QualMax, phase1EthicalMax]
    .filter((value): value is number => value !== null)
    .reduce((sum, value) => sum + value, 0);
  if (phase1TotalScore !== null && phase1TotalMax > 0) {
    sectionsPhase1.unshift({
      key: "phase1-total",
      label: "รวม Phase 1",
      value: `${formatScoreValue(phase1TotalScore)} / ${formatScoreValue(
        phase1TotalMax,
      )}`,
    });
  }
  if (sectionsPhase1.length > 0) {
    groups.push({
      key: "phase1",
      title: "Phase 1 – Core Analysis",
      items: sectionsPhase1,
    });
  }

  const sectionsPhase2: ConvictionGroup["items"] = [];
  const phase2QuantScore = safeNumber(phase2?.quantitative?.total);
  const phase2QuantMax =
    safeNumber(phase2?.quantitative?.weight) ?? safeNumber(phase2Weights?.quant);
  if (phase2QuantScore !== null && phase2QuantMax !== null) {
    sectionsPhase2.push({
      key: "phase2-quant",
      label: "Quantitative",
      value: `${formatScoreValue(phase2QuantScore)} / ${formatScoreValue(
        phase2QuantMax,
      )}`,
    });
  }

  const phase2QualScore = safeNumber(phase2?.qualitative?.total);
  const phase2QualMax =
    safeNumber(phase2?.qualitative?.weight) ?? safeNumber(phase2Weights?.qual);
  if (phase2QualScore !== null && phase2QualMax !== null) {
    sectionsPhase2.push({
      key: "phase2-qual",
      label: "Qualitative",
      value: `${formatScoreValue(phase2QualScore)} / ${formatScoreValue(
        phase2QualMax,
      )}`,
    });
  }

  const phase2EthicalScore = safeNumber(phase2?.ethical);
  const phase2EthicalMax = safeNumber(phase2Weights?.ethical);
  if (phase2EthicalScore !== null && phase2EthicalMax !== null) {
    sectionsPhase2.push({
      key: "phase2-ethical",
      label: "Ethical Alignment",
      value: `${formatScoreValue(phase2EthicalScore)} / ${formatScoreValue(
        phase2EthicalMax,
      )}`,
    });
  }

  const phase2LeadershipScore = safeNumber(phase2?.market_leadership?.points);
  const phase2LeadershipMax = safeNumber(phase2Weights?.market_leadership);
  if (phase2LeadershipScore !== null && phase2LeadershipMax !== null) {
    sectionsPhase2.push({
      key: "phase2-leadership",
      label: "Market Leadership",
      value: `${formatScoreValue(phase2LeadershipScore)} / ${formatScoreValue(
        phase2LeadershipMax,
      )}`,
    });
  }

  const phase2RegionalScore = safeNumber(
    phase2?.regional_diversification?.points,
  );
  const phase2RegionalMax = safeNumber(phase2Weights?.regional);
  if (phase2RegionalScore !== null && phase2RegionalMax !== null) {
    sectionsPhase2.push({
      key: "phase2-regional",
      label: "Regional Diversification",
      value: `${formatScoreValue(phase2RegionalScore)} / ${formatScoreValue(
        phase2RegionalMax,
      )}`,
    });
  }

  const phase2TotalScore = safeNumber(phase2?.total);
  const phase2TotalMax = [
    phase2QuantMax,
    phase2QualMax,
    phase2EthicalMax,
    phase2LeadershipMax,
    phase2RegionalMax,
  ]
    .filter((value): value is number => value !== null)
    .reduce((sum, value) => sum + value, 0);
  if (phase2TotalScore !== null && phase2TotalMax > 0) {
    sectionsPhase2.unshift({
      key: "phase2-total",
      label: "รวม Phase 2",
      value: `${formatScoreValue(phase2TotalScore)} / ${formatScoreValue(
        phase2TotalMax,
      )}`,
    });
  }
  if (sectionsPhase2.length > 0) {
    groups.push({
      key: "phase2",
      title: "Phase 2 – Advanced Review",
      items: sectionsPhase2,
    });
  }

  return groups;
};

const buildConvictionDetail = (
  breakdown: ConvictionBreakdown | null,
  finalScore: number | null,
): ReactNode => {
  const groups = buildConvictionGroups(breakdown);
  const totalScore =
    typeof finalScore === "number" && Number.isFinite(finalScore)
      ? finalScore
      : null;

  if (groups.length === 0 && totalScore === null) {
    return null;
  }

  return (
    <div className={styles.convictionDetail}>
      {totalScore !== null ? (
        <div className={styles.convictionDetailTotal}>
          Conviction : {formatScoreValue(totalScore)} / 100
        </div>
      ) : null}
      {groups.map((group) => (
        <div key={group.key} className={styles.convictionDetailGroup}>
          <div className={styles.convictionDetailGroupTitle}>{group.title}</div>
          <ul className={styles.convictionDetailList}>
            {group.items.map((item) => (
              <li key={item.key} className={styles.convictionDetailItem}>
                <span>{item.label}</span>
                <span>{item.value}</span>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
};

// Shared data fetching logic moved to @/lib/stocks-service.ts
// Direct DB access is used to avoid internal HTTP fetch issues on Vercel.

const deriveMoatStrength = (raw: string | null | undefined): MoatStrengthData => {
  const source = typeof raw === "string" ? raw.trim() : "";
  const hasContent = source.length > 0 && source !== "—";
  const lower = source.toLowerCase();
  const firstSentence =
    source
      .split(/[.!?•\n]/)
      .map((line) => line.trim())
      .find((line) => line.length > 0) ?? "";

  let data: MoatStrengthData = {
    level: "กลาง",
    score: 2,
    tone: "medium",
    heading: "Moat ระดับปานกลาง",
    summary: hasContent
      ? firstSentence || "มีความได้เปรียบเชิงการแข่งขันระดับปานกลาง"
      : "ข้อมูล Moat ยังไม่ชัดเจน",
    highlights: [],
  };

  if (lower.includes("wide") || lower.includes("strong") || lower.includes("durable")) {
    data = {
      level: "สูง",
      score: 3,
      tone: "strong",
      heading: "Moat แข็งแกร่ง",
      summary: hasContent
        ? firstSentence || "บริษัทมีความได้เปรียบเชิงการแข่งขันสูง"
        : "บริษัทมีความได้เปรียบเชิงการแข่งขันสูง",
      highlights: [],
    };
  } else if (
    lower.includes("none") ||
    lower.includes("weak") ||
    lower.includes("limited")
  ) {
    data = {
      level: "ต่ำ",
      score: 1,
      tone: "weak",
      heading: "Moat จำกัด",
      summary: hasContent
        ? firstSentence || "ความได้เปรียบเชิงการแข่งขันยังไม่ชัดเจน"
        : "ความได้เปรียบเชิงการแข่งขันยังไม่เด่นชัด",
      highlights: [],
    };
  }

  const highlightCandidates = source
    .split(/[\n•\-]+/)
    .map((item) => item.replace(/^[\[\s:•\-]+/, "").trim())
    .filter((item) => item.length > 0);

  data.highlights = highlightCandidates
    .filter((item) => item !== firstSentence)
    .slice(0, 3);
  return data;
};

const QUALITY_CARD_PRIORITY: Record<string, number> = {
  moat: 1,
  business: 2,
  pricing: 3,
  leadership: 4,
  prospects: 5,
  risks: 6,
  watchpoints: 7,
};

const chunkArray = <T,>(values: T[], chunkSize: number): T[][] => {
  if (chunkSize <= 0) {
    return [values];
  }
  const chunks: T[][] = [];
  for (let index = 0; index < values.length; index += chunkSize) {
    chunks.push(values.slice(index, index + chunkSize));
  }
  return chunks;
};

const joinClasses = (...classes: (string | undefined)[]) =>
  classes.filter(Boolean).join(" ");

export default async function StockOverviewPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker: rawTicker } = await params;
  const ticker = rawTicker?.toUpperCase();

  if (!ticker) {
    return (
      <div className={styles.page}>
        <BackLink href="/" />
        <div className={styles.emptyState}>ไม่พบ Ticker ที่ระบุ</div>
      </div>
    );
  }

  const {
    stockInfo,
    analysisResult,
    financialData,
    segmentRevenue,
    portfolioPosition,
    documentSummary,
    secFilings,
    systemStatus,
  } = await getDetailedStockInfo(ticker);

  if (!stockInfo) {
    return (
      <div className={styles.page}>
        <BackLink href="/" />
        <div className={styles.emptyState}>ยังไม่มีข้อมูลสำหรับ {ticker}</div>
      </div>
    );
  }

  const conviction = analysisResult?.conviction_score ?? null;
  const mos = analysisResult?.margin_of_safety ?? null;
  const intrinsic = analysisResult?.intrinsic_value_estimate ?? null;
  const currentPrice = analysisResult?.current_price ?? null;

  const directive = parseDirective(analysisResult?.portfolio_directive);

  const checklistDetails = parseChecklistDetails(
    analysisResult?.checklist_details,
  );
  const valuationInsights = extractValuationInsights(checklistDetails);
  const convictionBreakdown = extractConvictionBreakdown(checklistDetails);
  const convictionDetail = buildConvictionDetail(convictionBreakdown, conviction);
  const discountInfo = valuationInsights?.discount_rate ?? null;
  const discountExplanation =
    discountInfo && typeof discountInfo.explanation === "string"
      ? cleanText(discountInfo.explanation)
      : "—";
  const rawAdjustmentEntries: DiscountRateAdjustment[] = Array.isArray(
    discountInfo?.adjustments,
  )
    ? (discountInfo.adjustments as unknown[]).filter(
        (item): item is DiscountRateAdjustment =>
          !!item && typeof item === "object",
      )
    : [];
  const growthMap = valuationInsights?.growth_assumptions ?? null;
  const growthEntries: [string, GrowthAssumption][] = growthMap
    ? Object.entries(growthMap)
        .filter(
          ([, info]) => info && typeof info === "object",
        )
        .map(
          ([label, info]) =>
            [label, info as GrowthAssumption] as [string, GrowthAssumption],
        )
        .sort((a, b) => a[0].localeCompare(b[0]))
    : [];
  const modelsMap = valuationInsights?.models ?? null;
  const modelEntries: [string, ValuationModelDetail][] = modelsMap
    ? Object.entries(modelsMap)
        .filter(
          ([, detail]) => detail && typeof detail === "object",
        )
        .map(
          ([label, detail]) =>
            [label, detail as ValuationModelDetail] as [
              string,
              ValuationModelDetail,
            ],
        )
        .sort((a, b) => a[0].localeCompare(b[0]))
    : [];
  const modelUsedKey = valuationInsights?.model_used ?? null;
  // DB stores 'Fund Net Asset Value (NAV)'; old code may have 'Fund NAV Valuation'
  const isFundNAV = Boolean(
    modelUsedKey &&
      (modelUsedKey.includes("NAV") ||
        modelUsedKey.toLowerCase().includes("fund net asset"))
  );

  const summaryData = (documentSummary ?? null) as DocumentSummary | null;
  const riskNarratives = gatherRiskNarratives(summaryData, analysisResult);
  const claimedNarratives = new Set<string>();
  const discountReasonSignatures = new Set<string>();
  const discountReasonsList: string[] = [];
  const seenReasonSignatures = new Set<string>();
  const adjustmentEntries: DiscountRateAdjustment[] = rawAdjustmentEntries.map(
    (entry) => {
      const codeCandidates = [
        canonicalizeTag(entry.code),
        canonicalizeTag(entry.type),
        canonicalizeTag(entry.label),
      ].filter((value): value is string => Boolean(value));
      let reason: string | null = null;
      for (const candidate of codeCandidates) {
        reason = findTagNarrative(candidate, entry.label ?? null, riskNarratives, claimedNarratives);
        if (reason) {
          break;
        }
      }
      if (!reason && codeCandidates.length > 0) {
        const canonical = codeCandidates[0];
        const mapped =
          BUSINESS_RISK_EXPLANATIONS[canonical] ??
          GOVERNANCE_FLAG_EXPLANATIONS[canonical];
        if (mapped) {
          reason = mapped.replace(/^[^:：]+[:：]\s*/, "").trim();
        }
      }
      if (reason) {
        const sig = detailSignature(reason);
        if (sig) {
          discountReasonSignatures.add(sig);
          if (!seenReasonSignatures.has(sig)) {
            discountReasonsList.push(reason);
            seenReasonSignatures.add(sig);
          }
        }
      }
      return {
        ...entry,
        reason: reason ?? null,
      };
    },
  );
  const discountReasons = discountReasonsList;
  const riskItems = parseRiskList(analysisResult?.key_risks ?? null);
  const directiveTargetPct = safeNumber(directive?.target_pct);
  const positionTargetRatio = safeNumber(portfolioPosition?.target_pct);
  const targetPercent =
    directiveTargetPct !== null
      ? directiveTargetPct
      : positionTargetRatio !== null
      ? positionTargetRatio * 100
      : null;

  const holdingsQuantity = safeNumber(portfolioPosition?.quantity);
  const holdingsQuantityLabel =
    holdingsQuantity !== null ? formatQuantity(holdingsQuantity) : null;

  const currentPercentRatio = safeNumber(portfolioPosition?.current_pct);
  const currentPercentLabel =
    currentPercentRatio !== null
      ? formatPercent(currentPercentRatio * 100, 1)
      : null;

  const rawIntrinsicReason =
    typeof analysisResult?.intrinsic_value_reason === "string"
      ? analysisResult.intrinsic_value_reason
      : null;
  const intrinsicReason =
    rawIntrinsicReason && rawIntrinsicReason.trim().length > 0
      ? cleanText(rawIntrinsicReason)
      : null;

  // Extract INDUSTRY_ASSET from documentSummary for ConvictionDetailsModal
  const industryAssetRaw = (summaryData as any)?.INDUSTRY_ASSET;
  const industryAsset: string | undefined = typeof industryAssetRaw === 'object' && industryAssetRaw?.value
    ? String(industryAssetRaw.value).toUpperCase()
    : typeof industryAssetRaw === 'string' ? industryAssetRaw.toUpperCase() : undefined;

  const metricCards: MetricCard[] = [
    {
      key: "conviction",
      label: "CONVICTION",
      icon: <Star className="w-5 h-5 text-yellow-500 animate-pulse" fill="currentColor" />,
      valuePrimary:
        conviction === null ? "—" : `${conviction.toFixed(0)} / 100`,
      valueColor: getConvictionColor(conviction),
      action: (
        <ConvictionWidget
          breakdown={{ ...(convictionBreakdown as any), industryAsset }}
          score={conviction}
          financialData={financialData}
          label="ดูรายละเอียดคะแนน"
          className={styles.metricDetailTrigger}
        />
      ),
    },
    {
      key: "mos",
      label: "MARGIN OF SAFETY",
      icon: <ShieldCheck className="w-5 h-5 text-indigo-500 animate-bounce" />,
      valuePrimary: mos === null ? "—" : formatPercent(mos * 100),
      valueColor: getMarginColor(mos),
    },
    {
      key: "price",
      label: "CURRENT PRICE",
      icon: <Banknote className="w-5 h-5 text-emerald-500 animate-pulse" />,
      valuePrimary: currentPrice === null ? "—" : `$${currentPrice.toFixed(2)}`,
      valueSecondary:
        intrinsic !== null ? (
          <span style={{ display: 'inline-flex', alignItems: 'center' }}>
            Intrinsic ${intrinsic.toFixed(2)}
            {isFundNAV && (
              <NAVTooltip />
            )}
          </span>
        ) : undefined,
      valueColor: getPriceColor(),
    },
  ];

  const targetPrimary =
    holdingsQuantityLabel !== null
      ? `${holdingsQuantityLabel} shares`
      : targetPercent !== null
      ? formatPercent(targetPercent, 1)
      : "—";

  const targetSecondary =
    currentPercentLabel !== null
      ? `Current ${currentPercentLabel}`
      : undefined;

  metricCards.push({
    key: "target",
    label: "TARGET ALLOCATION",
    icon: <Target className="w-5 h-5 text-red-500 animate-pulse" />,
    valuePrimary: targetPrimary,
    valueSecondary: targetSecondary,
    footnote: undefined,
    valueColor: getTargetColor(targetPercent),
  });

  const revenueBySegmentField = getSummaryField<{ value?: unknown }>(
    summaryData,
    "revenue_by_segment",
  );
  const revenueByRegionField = getSummaryField<{ value?: unknown }>(
    summaryData,
    "revenue_by_region",
  );

  const productDataset =
    buildSegmentDataset(
      segmentRevenue?.product ?? null,
      "By source / business",
      "Revenue streams & business lines",
    ) ??
    buildSummaryRevenueDataset(
      revenueBySegmentField?.value ?? null,
      "segment",
      "By source/business",
      "Revenue streams & business lines",
    );

  const geoDataset =
    buildSegmentDataset(
      segmentRevenue?.geo ?? null,
      "By country",
      "Regional revenue contribution",
    ) ??
    buildSummaryRevenueDataset(
      revenueByRegionField?.value ?? null,
      "region",
      "By country",
      "Regional revenue contribution",
    );

  const moatData = deriveMoatStrength(analysisResult?.moat_rating);
  const moatHeadingDisplay = moatData.heading
    ? moatData.heading.replace("Moat แข็งแกร่ง", "Wide Durable Moat")
    : "Wide Durable Moat";
  const moatsIdentifiedField = getSummaryField<{ value?: unknown }>(
    summaryData,
    "moats_identified",
  );
  const structuredMoats: QualityItem[] = Array.isArray(moatsIdentifiedField?.value)
    ? (moatsIdentifiedField.value as unknown[])
        .filter(
          (entry): entry is Record<string, unknown> =>
            entry !== null && typeof entry === "object",
        )
        .map((entry) => {
          const type =
            typeof entry.type === "string"
              ? entry.type.trim()
              : typeof entry["type"] === "string"
              ? (entry["type"] as string).trim()
              : null;
          const strength =
            typeof entry.strength === "string"
              ? entry.strength.trim()
              : typeof entry["strength"] === "string"
              ? (entry["strength"] as string).trim()
              : null;
          const rationale =
            typeof entry.rationale === "string"
              ? entry.rationale.trim()
              : typeof entry["rationale"] === "string"
              ? (entry["rationale"] as string).trim()
              : undefined;
          if (!type) return null;
          const item: QualityItem = { label: `${type} ระดับ ${strength ?? "Strong"}` };
          if (rationale) item.detail = rationale;
          return item;
        })
        .filter((value): value is QualityItem => value !== null)
    : [];
  const moatHighlights: QualityItem[] =
    structuredMoats.length > 0
      ? dedupeQualityItems(structuredMoats)
      : moatData.highlights.map(h => ({ label: h }));

  const riskCards = buildRiskCards(summaryData, riskItems, discountReasonSignatures);

  let qualityCards = [
    ...buildQualityCards(
      summaryData,
      moatHeadingDisplay,
      moatData.summary,
      moatHighlights,
    ),
    ...riskCards,
  ];

  const occupiedDetailSignatures = new Set<string>();
  discountReasonSignatures.forEach((sig) => occupiedDetailSignatures.add(sig));
  qualityCards.forEach((card) => {
    if (card.key === "watchpoints") return;
    card.items.forEach((item) => {
      const detailSig = detailSignature(item.detail);
      if (detailSig) {
        occupiedDetailSignatures.add(detailSig);
      }
      const labelSig = detailSignature(item.label);
      if (labelSig) {
        occupiedDetailSignatures.add(labelSig);
      }
    });
  });

  qualityCards = qualityCards
    .map((card) => {
      if (card.key !== "watchpoints") {
        return card;
      }
      const filteredItems = card.items.filter((item) => {
        const detailSig = detailSignature(item.detail);
        if (detailSig && occupiedDetailSignatures.has(detailSig)) {
          return false;
        }
        const labelSig = detailSignature(item.label);
        if (labelSig && occupiedDetailSignatures.has(labelSig)) {
          return false;
        }
        return true;
      });
      if (filteredItems.length === 0) {
        return null;
      }
      filteredItems.forEach((item) => {
        const detailSig = detailSignature(item.detail);
        if (detailSig) {
          occupiedDetailSignatures.add(detailSig);
        }
        const labelSig = detailSignature(item.label);
        if (labelSig) {
          occupiedDetailSignatures.add(labelSig);
        }
      });
      return { ...card, items: filteredItems };
    })
    .filter((card): card is QualityCard => Boolean(card));

  qualityCards.sort((a, b) => {
    const priorityA = QUALITY_CARD_PRIORITY[a.key] ?? 50;
    const priorityB = QUALITY_CARD_PRIORITY[b.key] ?? 50;
    if (priorityA !== priorityB) {
      return priorityA - priorityB;
    }
    return a.title.localeCompare(b.title);
  });

  const qualityRowsData = chunkArray(qualityCards, 3);
  const hasQualityContent = qualityCards.length > 0;
  
  const isShellOrUnsupported = 
    modelUsedKey === "shell_company" ||
    modelUsedKey?.includes("Shell Company") || 
    modelUsedKey?.includes("No DCF") ||
    intrinsicReason?.includes("Blank Check") || 
    intrinsicReason?.includes("Shell Company") ||
    (intrinsic === 0 && Boolean(intrinsicReason));

  const forceUnavailable = Boolean(isShellOrUnsupported);

  const showAnalysisUnavailable = Boolean(intrinsicReason && (!hasQualityContent || forceUnavailable));
  const qualitySectionTitle = showAnalysisUnavailable
    ? "สถานะการวิเคราะห์"
    : "Quality Overview";

  if (intrinsicReason && !showAnalysisUnavailable) {
    const priceCard = metricCards.find((metric) => metric.key === "price");
    if (priceCard) {
      priceCard.footnote = intrinsicReason;
    }
  }

  const renderQualityCard = (card: QualityCard) => (
    <article key={card.key} className={styles.qualityPanelCard}>
      <div className={styles.qualityPanelCardHeader}>
        <span className={styles.qualityPanelIcon}>{card.icon}</span>
        <div className={styles.qualityPanelHeading}>
          <span className={styles.qualityPanelTitle}>{card.title}</span>
          {card.subtitle ? (
            <span className={styles.qualityPanelSubtitle}>{card.subtitle}</span>
          ) : null}
        </div>
      </div>
      <div className={styles.qualityPanelBody}>
        {card.items.length === 0 ? (
          <div className={styles.qualityPanelEmpty}>—</div>
        ) : (
          card.items.map((item, index) => {
            const detailRaw = item.detail?.trim() ?? "";
            const detailText = detailRaw
              ? stripLeadingLabel(item.label, detailRaw)
              : "";
            if (detailText) {
              return (
                <details
                  key={`${card.key}-${index}`}
                  className={styles.qualityPanelDetail}
                >
                  <summary title={detailText}>{item.label}</summary>
                  <p>{detailText}</p>
                </details>
              );
            }
            return (
              <div
                key={`${card.key}-${index}`}
                className={styles.qualityPanelBadge}
                title={detailRaw || undefined}
              >
                {item.label}
              </div>
            );
          })
        )}
      </div>
    </article>
  );

  const phaseDisplay = derivePhaseDisplay(systemStatus ?? null);
  const analysisStatusText = phaseDisplay
    ? phaseDisplay.dateLabel
      ? `${phaseDisplay.phaseLabel} | ${phaseDisplay.dateLabel}`
      : phaseDisplay.phaseLabel
    : null;

  return (
    <div className={styles.page}>
      {/* Floating sticky home logo - sits outside the header to avoid crowding */}
      <div className={styles.floatingBackLink}>
        <BackLink href="/" />
      </div>
      <div className={styles.floatingProfile}>
        <UserProfileDropdown />
      </div>

      <header className={styles.header}>
        <div className={styles.headerTopRow}>
          <div className={styles.titleGroup}>
            <StockLogo
              ticker={ticker}
              companyName={stockInfo.company_name}
              logoUrl={stockInfo.logo_url}
              size={56}
              className={styles.headerLogo}
            />
            <div className={styles.titleStack}>
              <div className={styles.titleTickerRow}>
                <span className={styles.titleTicker}>{ticker}</span>
              </div>
              <h1 className={styles.title}>
                {stockInfo.company_name ?? ticker}
              </h1>
            </div>
          </div>
          {analysisStatusText ? (
            <div className={styles.analysisStatusBadge}>
              {analysisStatusText}
            </div>
          ) : null}
          <SearchBox mode="stock" placeholder={`Search stocks...`} className={styles.headerSearch} currentTicker={ticker} />
        </div>
        <div className={styles.subtitleRow}>
          {stockInfo.sector ? (
            <span className={styles.titleMetaPill}>{stockInfo.sector}</span>
          ) : null}
          <div className={styles.subtitle}>
            {stockInfo.industry ?? stockInfo.sector ?? "—"}
          </div>
        </div>
      </header>

      <section className={styles.metricPanel}>
        {metricCards.map((metric) => (
          <div
            key={metric.key}
            className={styles.metricCardModern}
          >
            <div className={styles.metricCardHeader}>
              <span className={styles.metricIcon}>{metric.icon}</span>
              <span className={styles.metricLabelText}>{metric.label}</span>
            </div>
            <div
              className={styles.metricValuePrimary}
              style={
                metric.valueColor
                  ? { color: metric.valueColor }
                  : undefined
              }
            >
              {metric.valuePrimary}
            </div>
            {metric.valueSecondary ? (
              <div className={styles.metricValueSecondary}>
                {metric.valueSecondary}
              </div>
            ) : null}
            {metric.footnote ? (
              <div className={styles.metricValueFootnote}>{metric.footnote}</div>
            ) : null}
            {metric.action ? (
              <div className={styles.metricDetailWrapper}>{metric.action}</div>
            ) : metric.detail ? (
              <div className={styles.metricDetailWrapper}>
                <button
                  type="button"
                  className={styles.metricDetailTrigger}
                  aria-label={metric.detailLabel ?? "ดูรายละเอียดเพิ่มเติม"}
                >
                  {metric.detailLabel ?? "รายละเอียด"}
                </button>
                <div className={styles.metricDetailPopover}>{metric.detail}</div>
              </div>
            ) : null}
          </div>
        ))}
      </section>

      <section className={styles.qualityPanel}>
        <div className={styles.qualityPanelHeader}>
          <h2>{qualitySectionTitle}</h2>
        </div>
        {showAnalysisUnavailable ? (
          <div className={styles.analysisUnavailableCard}>
            <div className={styles.analysisUnavailableIcon}>
              {modelUsedKey === "shell_company" ? "🚫" : "⚠️"}
            </div>
            <div className={styles.analysisUnavailableContent}>
              <p className={styles.analysisUnavailableHeading}>
                {modelUsedKey === "shell_company"
                  ? "ไม่สามารถวิเคราะห์หุ้นกลุ่มนี้ได้ (Shell Company)"
                  : "ยังไม่สามารถแสดงผลการวิเคราะห์เชิงคุณภาพสำหรับหุ้นนี้ได้"}
              </p>
              <p className={styles.analysisUnavailableReason}>
                {intrinsicReason}
              </p>
            </div>
          </div>
        ) : (
          <div className={styles.qualityRows}>
            {qualityRowsData.map((rowCards, index) => {
              const rowClass = joinClasses(
                styles.qualityRow,
                index === 0 ? styles.qualityRowTop : styles.qualityRowBottom,
                rowCards.length === 1 ? styles.qualityRowSingle : undefined,
              );
              const rowStyle: CSSProperties | undefined =
                rowCards.length === 1
                  ? {
                      justifyContent: "center",
                      gridTemplateColumns: "minmax(260px, 420px)",
                    }
                  : rowCards.length === 2
                  ? {
                      justifyContent: "center",
                      gridTemplateColumns: "repeat(2, minmax(240px, 1fr))",
                    }
                  : undefined;
              return (
                <div
                  key={`quality-row-${index}`}
                  className={rowClass}
                  style={rowStyle}
                >
                  {rowCards.map(renderQualityCard)}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {!forceUnavailable && (productDataset || geoDataset) ? (
        <section className={styles.revenuePanel}>
          <div className={styles.revenueHeader}>
            <h3>Revenue Breakdown</h3>
          </div>
          <RevenueBreakdownChart
            product={productDataset}
            geo={geoDataset}
          />
        </section>
      ) : null}

      {!forceUnavailable && !isFundNAV && (discountInfo || growthEntries.length > 0 || modelEntries.length > 0) && (
        <section className={styles.valuationCard}>
          <ValuationInputsPanel
            discountInfo={discountInfo}
            discountExplanation={discountExplanation}
            adjustments={adjustmentEntries}
            discountReasons={discountReasons}
            growthEntries={growthEntries}
            modelEntries={modelEntries}
            modelUsedKey={modelUsedKey}
          />
        </section>
      )}
    </div>
  );
}
