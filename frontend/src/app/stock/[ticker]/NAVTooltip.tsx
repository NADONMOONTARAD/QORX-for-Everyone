"use client";

import React, { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { LottieIcon } from "@/components/LottieIcon";
import questionAnimation from "@/assets/lottie/icons8-info.json";

export function NAVTooltip() {
  const wrapperRef = useRef<HTMLSpanElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [tooltipStyle, setTooltipStyle] = useState<React.CSSProperties>({
    top: -9999,
    left: -9999,
  });
  const [play, setPlay] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const showTooltip = () => {
    if (!wrapperRef.current || !tooltipRef.current) {
      return;
    }
    const anchor = wrapperRef.current.getBoundingClientRect();
    const tipW = tooltipRef.current.offsetWidth || 320;
    const tipH = tooltipRef.current.offsetHeight || 220;
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
    setPlay(true);
    setVisible(true);
  };

  const hideTooltip = () => { setPlay(false); setVisible(false); };

  return (
    <>
      <span
        ref={wrapperRef}
        onMouseEnter={showTooltip}
        onMouseLeave={hideTooltip}
        onClick={() => visible ? hideTooltip() : showTooltip()}
        style={{ position: "relative", display: "inline-flex", alignItems: "center", marginLeft: "8px", cursor: "pointer" }}
      >
        <span style={{ display: "inline-flex", width: 22, height: 22, filter: "var(--icon-filter, none)" }}>
          <LottieIcon animationData={questionAnimation} loop={false} play={play} />
        </span>
      </span>

      {mounted
        ? createPortal(
            <div
              ref={tooltipRef}
              data-visible={visible ? "true" : "false"}
              style={{
                ...tooltipStyle,
                position: "fixed",
                zIndex: 9999,
                minWidth: "320px",
                maxWidth: "400px",
                padding: "20px",
                textAlign: "left",
                lineHeight: "1.6",
                cursor: "default",
                backgroundColor: "var(--card-bg, #ffffff)",
                border: "1px solid var(--border-color, #e2e8f0)",
                borderRadius: "12px",
                boxShadow: "0 10px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1)",
                pointerEvents: visible ? "auto" : "none",
                opacity: visible ? 1 : 0,
                transform: visible ? "translateY(0)" : "translateY(5px)",
                transition: "all 0.2s cubic-bezier(0.16, 1, 0.3, 1)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "12px", borderBottom: "1px solid var(--border-color, #e2e8f0)", paddingBottom: "10px" }}>
                <div style={{ fontSize: "15px", fontWeight: 700, color: "var(--text-primary, #0f172a)" }}>
                  วิธีการประเมินมูลค่า (Valuation Logic)
                </div>
              </div>

              <div style={{ fontSize: "13px", color: "var(--text-secondary, #475569)", marginBottom: "16px" }}>
                ระบบใช้ <strong>Fund Net Asset Value (NAV)</strong> สำหรับกองทุนประเภทนี้
                เพราะไม่สามารถใช้ Free Cash Flow แบบธุรกิจทั่วไปมาคำนวณ DCF ได้โดยตรง
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div style={{ background: "var(--background, #f8fafc)", padding: "12px", borderRadius: "8px", borderLeft: "3px solid var(--chart-orange, #ea580c)" }}>
                  <div style={{ fontSize: "11px", textTransform: "uppercase", fontWeight: 600, color: "var(--text-muted, #64748b)", marginBottom: "2px" }}>
                    NAV Base (จุดเริ่มต้น)
                  </div>
                  <div style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-primary, #1e293b)" }}>
                    Net Assets per Share
                  </div>
                </div>

                <div style={{ background: "var(--background, #f8fafc)", padding: "12px", borderRadius: "8px", borderLeft: "3px solid var(--chart-growth, #10b981)" }}>
                  <div style={{ fontSize: "11px", textTransform: "uppercase", fontWeight: 600, color: "var(--text-muted, #64748b)", marginBottom: "2px" }}>
                    Valuation Method
                  </div>
                  <div style={{ fontSize: "13px", fontWeight: 500, color: "var(--text-primary, #1e293b)" }}>
                    มูลค่าภายในคำนวณจากสินทรัพย์สุทธิรวม หารด้วยจำนวนหน่วยลงทุน
                  </div>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
