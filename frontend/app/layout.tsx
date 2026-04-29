import "./globals.css";
import type { ReactNode } from "react";
import AppShell from "../components/AppShell";

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="min-h-screen">
        <a href="#main-content" className="app-skip-to-content">
          跳到主内容
        </a>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
