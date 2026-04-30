"use client";

import type { QueryResult } from "../lib/chatSessions";

function toCsv(result: QueryResult): string {
  const escape = (v: unknown) => {
    const s = String(v ?? "");
    if (s.includes(",") || s.includes('"') || s.includes("\n")) {
      return `"${s.replace(/"/g, '""')}"`;
    }
    return s;
  };
  const header = result.columns.map(escape).join(",");
  const rows = result.rows.map((row) => result.columns.map((c) => escape(row[c])).join(","));
  return [header, ...rows].join("\n");
}

type CsvExportButtonProps = {
  result: QueryResult;
  filename?: string;
};

export default function CsvExportButton({ result, filename = "query_result.csv" }: CsvExportButtonProps) {
  if (!result.ok || !result.rows.length) return null;

  function handleExport() {
    const csv = toCsv(result);
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <button
      className="rounded-md border border-[#e5e7eb] bg-white px-2.5 py-1 text-xs text-[#6b7280] transition hover:bg-[#f9fafb] hover:text-[#111827]"
      onClick={handleExport}
      aria-label="导出 CSV"
    >
      导出 CSV
    </button>
  );
}
