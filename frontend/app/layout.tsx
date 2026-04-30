import "./globals.css";
import type { ReactNode } from "react";
import { Inter } from "next/font/google";
import AppShell from "../components/AppShell";
import ErrorBoundary from "../components/ErrorBoundary";
import ProgressBar from "../components/ProgressBar";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap"
});

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN" className={inter.variable}>
      <body className="min-h-screen">
        <a href="#main-content" className="app-skip-to-content">
          跳到主内容
        </a>
        <ProgressBar />
        <ErrorBoundary>
          <AppShell>{children}</AppShell>
        </ErrorBoundary>
      </body>
    </html>
  );
}
