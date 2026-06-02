"use client";

import { useState } from "react";
import { Icon } from "../AppIcons";
import { API } from "../../lib/api";

interface OntologyExportProps {
  /** Knowledge base ID for TTL export. */
  kbId: number;
  /** CSS selector for the SVG element to export as SVG/PNG. */
  svgSelector?: string;
  /** SPARQL query results to export as JSON. */
  sparqlResults?: Record<string, string>[];
  className?: string;
}

type ExportFormat = "svg" | "png" | "ttl" | "sparql-json";

const FORMAT_LABELS: Record<ExportFormat, string> = {
  svg: "SVG",
  png: "PNG",
  ttl: "Turtle (.ttl)",
  "sparql-json": "SPARQL JSON",
};

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function serializeSvgElement(svgEl: SVGSVGElement): string {
  const clone = svgEl.cloneNode(true) as SVGSVGElement;
  // Inline computed styles for reliable export
  const allElements = clone.querySelectorAll("*");
  for (const el of allElements) {
    const computed = window.getComputedStyle(el as Element);
    (el as SVGElement).setAttribute("fill", computed.fill);
    (el as SVGElement).setAttribute("stroke", computed.stroke);
    (el as SVGElement).setAttribute("font-family", computed.fontFamily);
    (el as SVGElement).setAttribute("font-size", computed.fontSize);
  }
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  return new XMLSerializer().serializeToString(clone);
}

async function exportSvg(selector: string, filename: string) {
  const svgEl = document.querySelector<SVGSVGElement>(selector);
  if (!svgEl) throw new Error("未找到 SVG 元素");
  const svgString = serializeSvgElement(svgEl);
  downloadBlob(svgString, filename, "image/svg+xml");
}

async function exportPng(selector: string, filename: string) {
  const svgEl = document.querySelector<SVGSVGElement>(selector);
  if (!svgEl) throw new Error("未找到 SVG 元素");
  const svgString = serializeSvgElement(svgEl);
  const canvas = document.createElement("canvas");
  const rect = svgEl.getBoundingClientRect();
  const scale = 2;
  canvas.width = (rect.width || 800) * scale;
  canvas.height = (rect.height || 600) * scale;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D 上下文不可用");
  const img = await new Promise<HTMLImageElement>((resolve, reject) => {
    const i = new Image();
    i.onload = () => resolve(i);
    i.onerror = () => reject(new Error("SVG 图片加载失败"));
    i.src = "data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(svgString)));
  });
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  canvas.toBlob((blob) => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, "image/png");
}

export default function OntologyExport({
  kbId,
  svgSelector,
  sparqlResults,
  className = "",
}: OntologyExportProps) {
  const [exporting, setExporting] = useState<ExportFormat | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleExport(format: ExportFormat) {
    setExporting(format);
    setError(null);
    const ts = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
    try {
      switch (format) {
        case "svg": {
          if (!svgSelector) throw new Error("未配置 SVG 选择器");
          await exportSvg(svgSelector, `ontology-kb${kbId}-${ts}.svg`);
          break;
        }
        case "png": {
          if (!svgSelector) throw new Error("未配置 SVG 选择器");
          await exportPng(svgSelector, `ontology-kb${kbId}-${ts}.png`);
          break;
        }
        case "ttl": {
          const resp = await fetch(
            `${API}/api/ontology/knowledge-bases/${kbId}/export`,
            { headers: { "Content-Type": "application/json" } },
          );
          if (!resp.ok) throw new Error(`API 返回 ${resp.status}`);
          const data = await resp.json();
          const ttl = (data as any).ttl || "";
          if (!ttl.trim()) throw new Error("本体图为空，无数据可导出");
          downloadBlob(ttl, `ontology-kb${kbId}-${ts}.ttl`, "text/turtle");
          break;
        }
        case "sparql-json": {
          if (!sparqlResults || sparqlResults.length === 0) {
            throw new Error("无 SPARQL 结果可导出");
          }
          downloadBlob(
            JSON.stringify(sparqlResults, null, 2),
            `sparql-results-${ts}.json`,
            "application/json",
          );
          break;
        }
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "导出失败");
    } finally {
      setExporting(null);
    }
  }

  const formats: ExportFormat[] = svgSelector
    ? ["svg", "png", "ttl"]
    : ["ttl"];
  if (sparqlResults && sparqlResults.length > 0) {
    formats.push("sparql-json");
  }

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      {formats.map((fmt) => (
        <button
          key={fmt}
          type="button"
          className={`app-button text-xs ${exporting === fmt ? "is-loading" : ""}`}
          disabled={exporting !== null}
          onClick={() => handleExport(fmt)}
          title={`导出 ${FORMAT_LABELS[fmt]}`}
        >
          <Icon name="code" className="inline h-3.5 w-3.5 mr-1" />
          {FORMAT_LABELS[fmt]}
        </button>
      ))}
      {error && (
        <span className="text-xs text-red-600 ml-2">{error}</span>
      )}
    </div>
  );
}
