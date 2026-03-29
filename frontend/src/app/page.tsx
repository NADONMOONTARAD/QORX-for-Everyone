"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Star } from "lucide-react";

import { SearchBox } from "@/components/SearchBox";
import { InteractiveHeroBackground } from "@/components/InteractiveHeroBackground";
import { UserProfileDropdown } from "@/components/UserProfileDropdown";
import styles from "./page.module.css";

type StockItem = {
  ticker: string;
  company_name: string;
  logo_url: string | null;
  sector: string | null;
  industry: string | null;
  conviction_score: string | null;
  margin_of_safety: string | null;
  current_price: string | null;
  portfolio_directive: any;
};

type SortKey = "rank" | "company" | "sector" | "mos" | "conviction" | "price";
type SortDirection = "asc" | "desc";
type FilterSelection =
  | { kind: "all"; value: "All" }
  | { kind: "sector"; value: string }
  | { kind: "industry"; value: string };

export default function PublicDashboardPage() {
  const [stocks, setStocks] = useState<StockItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [mounted, setMounted] = useState(false);
  const [filterSelection, setFilterSelection] = useState<FilterSelection>({ kind: "all", value: "All" });
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [filterSectorStage, setFilterSectorStage] = useState<string | null>(null);
  const [sortConfig, setSortConfig] = useState<{ key: SortKey; direction: SortDirection }>({
    key: "conviction",
    direction: "desc",
  });

  useEffect(() => {
    setMounted(true);
    fetch("/api/stocks")
      .then((res) => {
        if (!res.ok) throw new Error("Failed to fetch stocks");
        return res.json();
      })
      .then((data) => {
        // Assign initial rank to preserve the original sorted order (by Conviction Desc from API)
        const rankedData = (data || []).map((s: any, idx: number) => ({ ...s, initial_rank: idx + 1 }));
        setStocks(rankedData);
        setLoading(false);
      })
      .catch((err) => {
        console.error("Error fetching stocks:", err);
        setLoading(false);
      });
  }, []);

  const uniqueSectors = useMemo(() => {
    const sectors = new Set<string>();
    stocks.forEach((s) => {
      if (s.sector) sectors.add(s.sector);
    });
    return Array.from(sectors).sort();
  }, [stocks]);

  const sectorsWithIndustries = useMemo(() => {
    return uniqueSectors.map((sector) => {
      const industries = Array.from(
        new Set(
          stocks
            .filter((stock) => stock.sector === sector && stock.industry)
            .map((stock) => stock.industry as string),
        ),
      ).sort();

      return { sector, industries };
    });
  }, [stocks, uniqueSectors]);

  useEffect(() => {
    if (!isFilterOpen) return;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;

      if (filterSectorStage) {
        setFilterSectorStage(null);
      } else {
        setIsFilterOpen(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isFilterOpen, filterSectorStage]);

  const filteredAndSortedStocks = useMemo(() => {
    let result = [...stocks];

    if (filterSelection.kind === "sector") {
      result = result.filter((stock) => stock.sector === filterSelection.value);
    } else if (filterSelection.kind === "industry") {
      result = result.filter((stock) => stock.industry === filterSelection.value);
    }

    result.sort((a, b) => {
      const { key, direction } = sortConfig;
      const modifier = direction === "asc" ? 1 : -1;

      if (key === "rank") {
        return ((a as any).initial_rank - (b as any).initial_rank) * modifier;
      }
      if (key === "company") {
        return a.ticker.localeCompare(b.ticker) * modifier;
      }
      if (key === "sector") {
        const secA = a.sector || "";
        const secB = b.sector || "";
        return secA.localeCompare(secB) * modifier;
      }
      if (key === "mos") {
        const valA = a.margin_of_safety ? Number(a.margin_of_safety) : -999;
        const valB = b.margin_of_safety ? Number(b.margin_of_safety) : -999;
        return (valA - valB) * modifier;
      }
      if (key === "conviction") {
        const valA = a.conviction_score ? Number(a.conviction_score) : -999;
        const valB = b.conviction_score ? Number(b.conviction_score) : -999;
        return (valA - valB) * modifier;
      }
      if (key === "price") {
        const valA = a.current_price ? Number(a.current_price) : 0;
        const valB = b.current_price ? Number(b.current_price) : 0;
        return (valA - valB) * modifier;
      }
      return 0;
    });

    return result;
  }, [stocks, filterSelection, sortConfig]);

  const currentFilterLabel = useMemo(() => {
    if (filterSelection.kind === "all") return "All Sectors";
    return filterSelection.value;
  }, [filterSelection]);

  const activeFilterSectorEntry = useMemo(() => {
    if (!filterSectorStage) return null;
    return sectorsWithIndustries.find((entry) => entry.sector === filterSectorStage) ?? null;
  }, [filterSectorStage, sectorsWithIndustries]);

  const closeFilterModal = () => {
    setIsFilterOpen(false);
    setFilterSectorStage(null);
  };

  const handleSort = (key: SortKey) => {
    setSortConfig((prev) => {
      if (prev.key === key) {
        return { key, direction: prev.direction === "asc" ? "desc" : "asc" };
      }
      return { key, direction: "desc" };
    });
  };

  const renderSortIcon = (key: SortKey) => {
    const isActive = sortConfig.key === key;
    const direction = sortConfig.direction;
    return (
      <svg
        className={styles.sortIcon}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        {isActive ? (
          direction === "asc" ? (
            <path d="M12 20V4M5 11l7-7 7 7" />
          ) : (
            <path d="M12 4v16m7-7-7 7-7-7" />
          )
        ) : (
          <path d="M7 15l5 5 5-5M7 9l5-5 5 5" opacity="0.4" />
        )}
      </svg>
    );
  };

  const getMoSColorClass = (mosRaw: string | null) => {
    if (!mosRaw) return styles.scoreNeutral;
    const mos = Number(mosRaw);
    if (mos > 0.15) return styles.scorePositive;
    if (mos < 0) return styles.scoreNegative;
    return styles.scoreNeutral;
  };

  const getConvictionColorClass = (scoreRaw: string | null) => {
    if (!scoreRaw) return styles.scoreNeutral;
    const score = Number(scoreRaw);
    if (score >= 80) return styles.scorePositive;
    if (score < 60) return styles.scoreNegative;
    return styles.scoreNeutral;
  };

  return (
    <div className={styles.page}>
      <div className={styles.floatingProfile}>
        <UserProfileDropdown />
      </div>
      <section className={styles.hero}>
        <InteractiveHeroBackground className={styles.heroBackground} />
        <div className={styles.heroGlow} />

        <header className={styles.topBar}>
          <Link href="/" className={styles.brandLink} aria-label="QORX home">
            <span className={styles.brandName}>QORX</span>
            <span className={styles.brandTagline}>Small to Great.</span>
          </Link>

          <div className={styles.topControls}>
            <SearchBox
              placeholder="ค้นหาตาม Ticker หรือ ชื่อบริษัท..."
              className={styles.heroSearch}
              expandedByDefault
            />
          </div>
        </header>
      </section>

      <section className={styles.tableCard}>
        <div className={styles.controlsRow}>
          <h2>Top Rated Stocks</h2>
          <div className={styles.filterPopover}>
            <button
              type="button"
              className={`${styles.filterTrigger} ${isFilterOpen ? styles.filterTriggerOpen : ""}`}
              onClick={() => {
                setFilterSectorStage(null);
                setIsFilterOpen(true);
              }}
              aria-expanded={isFilterOpen}
              aria-label="Filter by sector or industry"
            >
              <span className={styles.filterTriggerText}>
                <span className={styles.filterTriggerLabel}>Filter</span>
                <span className={styles.filterTriggerValue}>{currentFilterLabel}</span>
              </span>
              <span className={styles.filterTriggerIcon}>⌄</span>
            </button>
          </div>
        </div>

        {!mounted ? null : loading ? (
          <div style={{ padding: 40, textAlign: "center", color: "var(--text-muted)" }}>
            กำลังโหลดข้อมูลหุ้น...
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table className={styles.screenerTable}>
              <thead>
                <tr>
                  <th onClick={() => handleSort("rank")} className={sortConfig.key === "rank" ? styles.sortActive : ""}>
                    Rank {renderSortIcon("rank")}
                  </th>
                  <th onClick={() => handleSort("company")} className={sortConfig.key === "company" ? styles.sortActive : ""}>
                    Company {renderSortIcon("company")}
                  </th>
                  <th onClick={() => handleSort("sector")} className={sortConfig.key === "sector" ? styles.sortActive : ""}>
                    Sector | Industry {renderSortIcon("sector")}
                  </th>
                  <th onClick={() => handleSort("mos")} className={sortConfig.key === "mos" ? styles.sortActive : ""}>
                    MoS {renderSortIcon("mos")}
                  </th>
                  <th onClick={() => handleSort("conviction")} className={sortConfig.key === "conviction" ? styles.sortActive : ""}>
                    Conviction {renderSortIcon("conviction")}
                  </th>
                  <th onClick={() => handleSort("price")} className={sortConfig.key === "price" ? styles.sortActive : ""}>
                    Price {renderSortIcon("price")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {filteredAndSortedStocks.map((stock) => {
                  const mosPct = stock.margin_of_safety 
                    ? (Number(stock.margin_of_safety) * 100).toFixed(1) + "%" 
                    : "—";
                  
                  const conviction = stock.conviction_score 
                    ? Number(stock.conviction_score).toFixed(0) 
                    : "—";
                    
                  const price = stock.current_price 
                    ? "$" + Number(stock.current_price).toFixed(2) 
                    : "—";

                  const initialRank = (stock as any).initial_rank;

                  return (
                    <tr key={stock.ticker}>
                      <td>
                        <span className={styles.rankBadge}>{initialRank}</span>
                      </td>
                      <td>
                        <div className={styles.companyCell}>
                          <a href={`/stock/${stock.ticker}`} className={styles.ticker}>
                            {stock.ticker}
                          </a>
                          <span className={styles.companyName} title={stock.company_name}>
                            {stock.company_name}
                          </span>
                        </div>
                      </td>
                      <td>
                        <div className={styles.sectorCell}>
                          <span className={styles.sectorPill}>{stock.sector || "N/A"}</span>
                          <span className={styles.industryText} title={stock.industry || ""}>
                            {stock.industry || "—"}
                          </span>
                        </div>
                      </td>
                      <td className={getMoSColorClass(stock.margin_of_safety)}>
                        {mosPct}
                      </td>
                      <td className={getConvictionColorClass(stock.conviction_score)}>
                        <div className="flex items-center gap-1">
                          <Star className="w-3.5 h-3.5 fill-current" />
                          {conviction}
                        </div>
                      </td>
                      <td style={{ fontWeight: 500 }}>{price}</td>
                    </tr>
                  );
                })}
                {filteredAndSortedStocks.length === 0 && (
                  <tr>
                    <td colSpan={6} style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}>
                      ไม่พบข้อมูลหุ้นในหมวดหมู่ที่เลือก
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {isFilterOpen ? (
        <div className={styles.filterOverlay} onClick={closeFilterModal}>
          <div
            className={styles.filterModal}
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="filter-modal-title"
          >
            <div className={styles.filterModalHeader}>
              <div className={styles.filterModalHeading}>
                <h3 id="filter-modal-title" className={styles.filterModalTitle}>
                  {activeFilterSectorEntry ? activeFilterSectorEntry.sector : "Choose a Sector"}
                </h3>
              </div>

              <div className={styles.filterModalActions}>
                {activeFilterSectorEntry ? (
                  <button
                    type="button"
                    className={styles.filterSecondaryAction}
                    onClick={() => setFilterSectorStage(null)}
                  >
                    Back to Sectors
                  </button>
                ) : null}
                <button
                  type="button"
                  className={styles.filterCloseAction}
                  onClick={closeFilterModal}
                  aria-label="Close filter"
                >
                  Close
                </button>
              </div>
            </div>

            {!activeFilterSectorEntry ? (
              <>
                <button
                  type="button"
                  className={`${styles.filterLeadCard} ${filterSelection.kind === "all" ? styles.filterItemActive : ""}`}
                  onClick={() => {
                    setFilterSelection({ kind: "all", value: "All" });
                    closeFilterModal();
                  }}
                >
                  <span className={styles.filterItemPrimary}>All Sectors</span>
                  <span className={styles.filterItemSecondary}>Show every stock in the screener</span>
                </button>

                <div className={styles.filterModalGrid}>
                  {sectorsWithIndustries.map(({ sector, industries }) => (
                    <button
                      key={sector}
                      type="button"
                      className={`${styles.filterItem} ${filterSelection.kind === "sector" && filterSelection.value === sector ? styles.filterItemActive : ""}`}
                      onClick={() => setFilterSectorStage(sector)}
                    >
                      <span className={styles.filterItemPrimary}>{sector}</span>
                      <span className={styles.filterItemSecondary}>
                        {industries.length} {industries.length === 1 ? "industry" : "industries"}
                      </span>
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <>
                <button
                  type="button"
                  className={`${styles.filterLeadCard} ${filterSelection.kind === "sector" && filterSelection.value === activeFilterSectorEntry.sector ? styles.filterItemActive : ""}`}
                  onClick={() => {
                    setFilterSelection({ kind: "sector", value: activeFilterSectorEntry.sector });
                    closeFilterModal();
                  }}
                >
                  <span className={styles.filterItemPrimary}>{activeFilterSectorEntry.sector}</span>
                  <span className={styles.filterItemSecondary}>All stocks in this sector</span>
                </button>

                <div className={styles.filterModalGrid}>
                  {activeFilterSectorEntry.industries.map((industry) => (
                    <button
                      key={industry}
                      type="button"
                      className={`${styles.filterItem} ${filterSelection.kind === "industry" && filterSelection.value === industry ? styles.filterItemActive : ""}`}
                      onClick={() => {
                        setFilterSelection({ kind: "industry", value: industry });
                        closeFilterModal();
                      }}
                    >
                      <span className={styles.filterItemPrimary}>{industry}</span>
                    </button>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
