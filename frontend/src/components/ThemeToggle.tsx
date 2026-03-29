"use client";

import { useTheme } from "next-themes";
import { useEffect, useState, useRef } from "react";
import Lottie, { LottieRefCurrentProps } from "lottie-react";
import sunAnimation from "@/assets/lottie/sun.json";

export function ThemeToggle() {
  const { theme, setTheme, resolvedTheme } = useTheme();
  const [mounted, setMounted] = useState(false);
  const lottieRef = useRef<LottieRefCurrentProps>(null);
  const isFirstMount = useRef(true);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (!mounted || !lottieRef.current) return;
    
    if (isFirstMount.current) {
      if (resolvedTheme === "dark") {
        lottieRef.current.goToAndStop(14, true); // Go to night theme icon (middle of animation)
      } else {
        lottieRef.current.goToAndStop(0, true); // Go to sun
      }
      isFirstMount.current = false;
    } else {
      // Animate if theme changes after initial mount
      if (resolvedTheme === "dark") {
        lottieRef.current.playSegments([0, 14], true);
      } else {
        lottieRef.current.playSegments([14, 0], true);
      }
    }
  }, [mounted, resolvedTheme]);

  if (!mounted) {
    return <div style={{ width: 44, height: 44 }} />; // placeholder to prevent layout shift
  }

  const toggleTheme = () => {
    setTheme(resolvedTheme === "dark" ? "light" : "dark");
  };

  return (
    <button
      onClick={toggleTheme}
      className="rounded-full shadow-sm hover:scale-105 transition-transform flex items-center justify-center cursor-pointer"
      aria-label={resolvedTheme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
      title={resolvedTheme === "dark" ? "Switch to Light Mode" : "Switch to Dark Mode"}
      style={{ width: "44px", height: "44px", border: "1px solid var(--border-color, rgba(0,0,0,0.1))", background: "var(--card-bg, #ffffff)" }}
    >
      <div style={{ width: "30px", height: "30px", display: "flex", alignItems: "center", justifyContent: "center", filter: "var(--icon-filter, none)" }}>
        <Lottie
          lottieRef={lottieRef}
          animationData={sunAnimation}
          loop={false}
          autoplay={false}
          style={{ width: "100%", height: "100%" }}
        />
      </div>
    </button>
  );
}
