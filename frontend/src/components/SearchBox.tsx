"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useRouter } from "next/navigation";
import dynamic from "next/dynamic";
import { callApi } from "@/lib/api";
import searchAnimation from "@/assets/lottie/icons8-search.json";
import historyAnimation from "@/assets/lottie/icons8-clock.json";
import styles from "./SearchBox.module.css";
import { StockLogo } from "./StockLogo";

const Lottie = dynamic(() => import("lottie-react"), { ssr: false });

function RecentSearchItem({ 
  ticker, 
  companyName,
  logoUrl,
  saveRecentSearch, 
  router, 
  setSearchTerm, 
  setShowDropdown 
}: {
  ticker: string;
  companyName?: string;
  logoUrl?: string | null;
  saveRecentSearch: (t: string) => void;
  router: any;
  setSearchTerm: (t: string) => void;
  setShowDropdown: (b: boolean) => void;
}) {
  const lottieRef = useRef<any>(null);

  return (
    <li
      className={styles.searchDropdownItem}
      style={{ display: "flex", alignItems: "center" }}
      onMouseEnter={() => {
        lottieRef.current?.setDirection(1);
        lottieRef.current?.play();
      }}
      onMouseLeave={() => {
        lottieRef.current?.setDirection(-1);
        lottieRef.current?.play();
      }}
      onMouseDown={(e) => {
        e.preventDefault();
        setSearchTerm(ticker);
        setShowDropdown(false);
        saveRecentSearch(ticker);
        router.push(`/stock/${ticker}`);
      }}
    >
      <span className={styles.recentIcon} style={{ display: "flex" }}>
        <Lottie
          lottieRef={lottieRef}
          animationData={historyAnimation}
          loop={false}
          autoplay={false}
          style={{ width: 16, height: 16 }}
        />
      </span>
      <StockLogo ticker={ticker} companyName={companyName} logoUrl={logoUrl} size={20} className={styles.suggestionLogo} style={{ marginRight: '8px' }} />
      <span className={styles.suggestionTicker}>{ticker}</span>
      {companyName && (
        <>
          <span className={styles.suggestionDivider}>|</span>
          <span className={styles.suggestionName}>{companyName}</span>
        </>
      )}
    </li>
  );
}

type StockSummary = {
  ticker: string;
  company_name?: string;
  logo_url?: string | null;
};

type SearchBoxProps = {
  mode?: "dashboard" | "stock";
  placeholder?: string;
  className?: string;
  currentTicker?: string;
  expandedByDefault?: boolean;
};

export function SearchBox({ 
  mode = "dashboard", 
  placeholder = "Search stocks",
  className = "",
  currentTicker = "",
  expandedByDefault = false,
}: SearchBoxProps) {
  const router = useRouter();
  const lottieRef = useRef<any>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  
  const [recentSearches, setRecentSearches] = useState<StockSummary[]>([]);
  const [searchTerm, setSearchTerm] = useState("");
  const [allStocks, setAllStocks] = useState<StockSummary[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [isSearchHovered, setIsSearchHovered] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem("recentSearches");
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        // Compatibility check: if it's an array of strings, we'll clear it or migrate it.
        // For simplicity, we'll assume new metadata format or filter out strings.
        if (Array.isArray(parsed)) {
          const valid = parsed.filter(item => typeof item === 'object' && item.ticker);
          setRecentSearches(valid);
        }
      } catch (e) {
        console.error("Failed to parse recent searches", e);
      }
    }
  }, []);

  const saveRecentSearch = (ticker: string) => {
    // Find the full info from allStocks to cache it
    const stockInfo = allStocks.find(s => s.ticker === ticker);
    if (!stockInfo) return;

    setRecentSearches((prev) => {
      const filtered = prev.filter((s) => s.ticker !== ticker);
      const updated = [stockInfo, ...filtered].slice(0, 4);
      localStorage.setItem("recentSearches", JSON.stringify(updated));
      return updated;
    });
  };

  const fetchStockDirectory = useCallback(async () => {
    try {
      const res = await callApi("/api/stocks", { cache: "no-store" });
      const rows = ((await res.json()) as StockSummary[]) ?? [];
      setAllStocks(rows);
    } catch (err) {
      console.error("Failed to fetch stock list", err);
    }
  }, []);

  useEffect(() => {
    fetchStockDirectory();
  }, [fetchStockDirectory]);

  const isExpanded = expandedByDefault || showDropdown || searchTerm.trim().length > 0;

  const filteredSuggestions = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return allStocks.slice(0, 10); // Show some initially if no term
    return allStocks.filter((stock) => 
      stock.ticker.toLowerCase().includes(term) || 
      (stock.company_name && stock.company_name.toLowerCase().includes(term))
    );
  }, [searchTerm, allStocks]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // Reset animation if collapsed and not hovered
  useEffect(() => {
    if (!isExpanded && !isSearchHovered) {
      lottieRef.current?.stop();
      lottieRef.current?.goToAndStop(0, true);
    }
  }, [isExpanded, isSearchHovered]);

  const handleSearchKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      const term = searchTerm.trim().toLowerCase();
      const match = allStocks.find((stock) =>
        stock.ticker.toLowerCase() === term ||
        (stock.company_name && stock.company_name.toLowerCase() === term)
      );
      const fallback = allStocks.find((stock) =>
        stock.ticker.toLowerCase().includes(term) ||
        (stock.company_name && stock.company_name.toLowerCase().includes(term))
      );
      const targetTicker = match?.ticker ?? fallback?.ticker;
      if (targetTicker) {
        saveRecentSearch(targetTicker);
        router.push(`/stock/${targetTicker}`);
        setShowDropdown(false);
        setSearchTerm("");
      }
    }
  };

  return (
    <div
      className={`${styles.searchBox} ${isExpanded ? styles.searchBoxExpanded : ""} ${expandedByDefault ? styles.searchBoxAlwaysExpanded : ""} ${mode === "stock" ? styles.searchBoxStock : ""} ${className}`}
      ref={searchRef}
      onMouseEnter={() => {
        setIsSearchHovered(true);
        lottieRef.current?.setSpeed(1.8);
        lottieRef.current?.setDirection(1);
        lottieRef.current?.play();
      }}
      onMouseLeave={() => {
        setIsSearchHovered(false);
        if (!isExpanded) {
          lottieRef.current?.stop();
          lottieRef.current?.goToAndStop(0, true);
        }
      }}
      onClick={() => {
        inputRef.current?.focus();
      }}
    >
      <div className={styles.searchIconWrapper}>
        <Lottie
          lottieRef={lottieRef}
          animationData={searchAnimation}
          loop={false}
          autoplay={false}
          style={{ width: 28, height: 28 }}
        />
      </div>
      <input
        ref={inputRef}
        className={styles.searchInput}
        placeholder={placeholder}
        value={searchTerm}
        onChange={(event) => {
          setSearchTerm(event.target.value);
          setShowDropdown(true);
        }}
        onFocus={() => {
          setShowDropdown(true);
          lottieRef.current?.setSpeed(1.8);
          lottieRef.current?.setDirection(1);
          lottieRef.current?.play();
        }}
        onKeyDown={handleSearchKeyDown}
        autoComplete="off"
      />
      {showDropdown && (
        <ul className={styles.searchDropdown}>
          {!searchTerm.trim() && (
            <>
              {recentSearches.filter(s => s.ticker !== currentTicker).length > 0 && (
                <>
                  <div className={styles.recentSearchesHeader}>Recent Searches</div>
                  {recentSearches.filter(s => s.ticker !== currentTicker).map((stock) => {
                    return (
                      <RecentSearchItem
                        key={`recent-${stock.ticker}`}
                        ticker={stock.ticker}
                        companyName={stock.company_name}
                        logoUrl={stock.logo_url}
                        saveRecentSearch={saveRecentSearch}
                        router={router}
                        setSearchTerm={setSearchTerm}
                        setShowDropdown={setShowDropdown}
                      />
                    );
                  })}
                </>
              )}
              
              {(() => {
                const featuredSuggestions = allStocks
                  .filter(s => !recentSearches.some(rs => rs.ticker === s.ticker))
                  .filter(s => s.ticker !== currentTicker)
                  .slice(0, 4);

                if (featuredSuggestions.length === 0) return null;

                return (
                  <>
                    <div 
                      className={styles.recentSearchesHeader} 
                      style={{ marginTop: recentSearches.length > 0 ? "8px" : "0" }}
                    >
                      Featured Analysis
                    </div>
                    {featuredSuggestions.map((stock) => {
                      const { ticker } = stock;
                      return (
                        <li
                          key={`featured-${ticker}`}
                          className={styles.searchDropdownItem}
                          style={{ display: "flex", alignItems: "center" }}
                          onMouseDown={(e) => {
                            e.preventDefault();
                            setShowDropdown(false);
                            saveRecentSearch(ticker);
                            router.push(`/stock/${ticker}`);
                            setSearchTerm("");
                          }}
                          title={`${ticker} | ${stock.company_name || ""}`}
                        >
                          <StockLogo ticker={ticker} companyName={stock.company_name} logoUrl={stock.logo_url} size={20} style={{ marginRight: '8px' }} />
                          <span className={styles.suggestionTicker}>{ticker}</span>
                          {stock.company_name && (
                            <>
                              <span className={styles.suggestionDivider}>|</span>
                              <span className={styles.suggestionName}>{stock.company_name}</span>
                            </>
                          )}
                        </li>
                      );
                    })}
                  </>
                );
              })()}
            </>
          )}
          {searchTerm.trim() && filteredSuggestions.length > 0 && (
            <>
              {filteredSuggestions.slice(0, 8).map((stock) => (
                <li
                  key={stock.ticker}
                  className={styles.searchDropdownItem}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    setShowDropdown(false);
                    saveRecentSearch(stock.ticker);
                    router.push(`/stock/${stock.ticker}`);
                    setSearchTerm("");
                  }}
                  title={`${stock.ticker} | ${stock.company_name || ""}`}
                >
                  <StockLogo ticker={stock.ticker} companyName={stock.company_name} logoUrl={stock.logo_url} size={20} style={{ marginRight: '8px' }} />
                  <span className={styles.suggestionTicker}>{stock.ticker}</span>
                  {stock.company_name && (
                    <>
                      <span className={styles.suggestionDivider}>|</span>
                      <span className={styles.suggestionName}>{stock.company_name}</span>
                    </>
                  )}
                </li>
              ))}
            </>
          )}
        </ul>
      )}
    </div>
  );
}
