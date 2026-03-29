"use client";

import React, { useState } from "react";
import { ConvictionDetailsModal, ConvictionBreakdown } from "./ConvictionDetailsModal";

type FinancialRow = {
  report_date: string;
  [key: string]: any;
};

type Props = {
  breakdown: ConvictionBreakdown | null;
  score: number | null;
  financialData: FinancialRow[];
  label: string;
  className?: string;
};

export const ConvictionWidget: React.FC<Props> = ({
  breakdown,
  score,
  financialData,
  label,
  className,
}) => {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        className={className}
        onClick={() => setIsOpen(true)}
      >
        {label}
      </button>
      <ConvictionDetailsModal
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        breakdown={breakdown}
        score={score}
        financialData={financialData}
      />
    </>
  );
};
