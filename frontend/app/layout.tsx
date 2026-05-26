import "./globals.css";
import type { ReactNode } from "react";
import { Suspense } from "react";
import { Inter } from "next/font/google";
import AppShell from "../components/AppShell";
import ErrorBoundary from "../components/ErrorBoundary";
import ProgressBar from "../components/ProgressBar";
import ThemeProvider from "../components/ThemeProvider";
import { THEME_BOOTSTRAP_SCRIPT } from "../lib/theme";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap"
});

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" className={inter.variable} data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_BOOTSTRAP_SCRIPT }} />
      </head>
      <body className="min-h-screen">
        <a href="#main-content" className="app-skip-to-content">
          跳到主内容
        </a>
        <ProgressBar />
        <ErrorBoundary>
          <ThemeProvider>
            <Suspense fallback={<div className="min-h-screen bg-app-bg">{children}</div>}>
              <AppShell>{children}</AppShell>
            </Suspense>
          </ThemeProvider>
        </ErrorBoundary>
      </body>
    </html>
  );
}
