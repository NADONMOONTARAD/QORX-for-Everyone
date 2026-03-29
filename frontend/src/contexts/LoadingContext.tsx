"use client";

import React, { createContext, useContext, useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

type LoadingContextType = {
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
};

const LoadingContext = createContext<LoadingContextType>({
  isLoading: false,
  setIsLoading: () => {},
});

export const useLoading = () => useContext(LoadingContext);

export function LoadingProvider({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(false);
  const pathname = usePathname();
  const searchParams = useSearchParams();

  useEffect(() => {
    setIsLoading(false);
  }, [pathname, searchParams]);

  useEffect(() => {
    let timeout: NodeJS.Timeout;
    
    const handleInterceptClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      const anchor = target.closest("a");

      if (!anchor) return;
      
      const href = anchor.getAttribute("href");
      if (!href) return;
      
      const isExternal = href.startsWith("http");
      const isSamePage = href.startsWith("#");
      const isNewTab = anchor.getAttribute("target") === "_blank";

      // If it's a normal Next.js link to another internal page
      if (!isExternal && !isSamePage && !isNewTab) {
         // Optionally delay setting loading to prevent flicker on fast loads
         timeout = setTimeout(() => {
           setIsLoading(true);
         }, 100);
      }
    };

    document.documentElement.addEventListener("click", handleInterceptClick, { capture: true });

    return () => {
      document.documentElement.removeEventListener("click", handleInterceptClick, { capture: true });
      clearTimeout(timeout);
    };
  }, []);

  return (
    <LoadingContext.Provider value={{ isLoading, setIsLoading }}>
      {children}
    </LoadingContext.Provider>
  );
}
