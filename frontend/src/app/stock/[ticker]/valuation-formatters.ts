export const formatCurrency = (value: number | null | undefined) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  const abs = Math.abs(value);
  if (abs >= 1_000_000_000_000) {
    return `${(value / 1_000_000_000_000).toFixed(2)}T`;
  }
  if (abs >= 1_000_000_000) {
    return `${(value / 1_000_000_000).toFixed(2)}B`;
  }
  if (abs >= 1_000_000) {
    return `${(value / 1_000_000).toFixed(1)}M`;
  }
  return value.toLocaleString(undefined, { maximumFractionDigits: 0 });
};

export const formatPercent = (value: number | null | undefined, digits = 1) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(digits)}%`;
};

export const formatRatio = (value: number | null | undefined, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(digits);
};

export const formatPercentFromRatio = (
  value: number | null | undefined,
  digits = 2,
) => {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return formatPercent(value * 100, digits);
};

export const cleanText = (value: string | null | undefined) => {
  if (!value) return "—";
  return value.replace(/\n+/g, "\n").replace(/\s{2,}/g, " ").trim();
};

