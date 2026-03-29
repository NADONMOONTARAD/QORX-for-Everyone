import type { Metadata } from "next";
import { Noto_Sans_Thai_Looped, Geist_Mono } from "next/font/google";
import "./globals.css";

const notoSansThaiLooped = Noto_Sans_Thai_Looped({
  variable: "--font-noto-sans-thai",
  subsets: ["latin", "thai"],
  weight: ["100", "200", "300", "400", "500", "600", "700", "800", "900"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "QORX",
  description: "AI-powered fundamental stock analysis with intrinsic value estimates, financial health scoring, and portfolio management.",
  icons: {
    icon: "/QORX Logo.png",
  },
};

import { Suspense } from "react";
import { LoadingProvider } from "@/contexts/LoadingContext";
import { ThemeProvider } from "@/components/ThemeProvider";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${notoSansThaiLooped.variable} ${geistMono.variable}`}>
        <ThemeProvider attribute="class" defaultTheme="system" enableSystem>
          <Suspense>
            <LoadingProvider>
              {children}
            </LoadingProvider>
          </Suspense>
        </ThemeProvider>
      </body>
    </html>
  );
}
