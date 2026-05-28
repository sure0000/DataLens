"use client";

import { useMemo } from "react";
import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import c from "highlight.js/lib/languages/c";
import cpp from "highlight.js/lib/languages/cpp";
import csharp from "highlight.js/lib/languages/csharp";
import css from "highlight.js/lib/languages/css";
import go from "highlight.js/lib/languages/go";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import kotlin from "highlight.js/lib/languages/kotlin";
import lua from "highlight.js/lib/languages/lua";
import markdown from "highlight.js/lib/languages/markdown";
import php from "highlight.js/lib/languages/php";
import plaintext from "highlight.js/lib/languages/plaintext";
import python from "highlight.js/lib/languages/python";
import ruby from "highlight.js/lib/languages/ruby";
import rust from "highlight.js/lib/languages/rust";
import scala from "highlight.js/lib/languages/scala";
import scss from "highlight.js/lib/languages/scss";
import sql from "highlight.js/lib/languages/sql";
import swift from "highlight.js/lib/languages/swift";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";
import { languageDisplayName, languageFromFilePath } from "../lib/highlightLanguage";

hljs.registerLanguage("plaintext", plaintext);
hljs.registerLanguage("python", python);
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("json", json);
hljs.registerLanguage("markdown", markdown);
hljs.registerLanguage("sql", sql);
hljs.registerLanguage("yaml", yaml);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("go", go);
hljs.registerLanguage("rust", rust);
hljs.registerLanguage("java", java);
hljs.registerLanguage("kotlin", kotlin);
hljs.registerLanguage("ruby", ruby);
hljs.registerLanguage("php", php);
hljs.registerLanguage("cpp", cpp);
hljs.registerLanguage("c", c);
hljs.registerLanguage("csharp", csharp);
hljs.registerLanguage("swift", swift);
hljs.registerLanguage("scala", scala);
hljs.registerLanguage("lua", lua);
hljs.registerLanguage("css", css);
hljs.registerLanguage("scss", scss);
hljs.registerLanguage("xml", xml);

function highlightCode(code: string, language: string): string {
  const lang = hljs.getLanguage(language) ? language : "plaintext";
  try {
    return hljs.highlight(code, { language: lang, ignoreIllegals: true }).value;
  } catch {
    return hljs.highlight(code, { language: "plaintext", ignoreIllegals: true }).value;
  }
}

export type CodeEditorViewProps = {
  code: string;
  /** highlight.js 语言 id；未传时从 filePath 推断 */
  language?: string;
  filePath?: string;
  /** 顶栏左侧标题，默认取文件名 */
  title?: string;
  /** 顶栏右侧副标题（如「块 #2」） */
  subtitle?: string;
  className?: string;
  /** 是否显示行号，默认 true */
  lineNumbers?: boolean;
  /**
   * fixed：固定高度，内容在框内滚动（默认）
   * fill：占满父级 flex 剩余高度（父级需有明确高度）
   */
  layout?: "fixed" | "fill";
};

export default function CodeEditorView({
  code,
  language,
  filePath,
  title,
  subtitle,
  className = "",
  lineNumbers = true,
  layout = "fixed",
}: CodeEditorViewProps) {
  const lang = language || (filePath ? languageFromFilePath(filePath) : "plaintext");
  const fileName = title || (filePath ? filePath.split("/").pop() : undefined) || "代码";
  const langLabel = languageDisplayName(lang);

  const lines = useMemo(() => code.replace(/\r\n/g, "\n").split("\n"), [code]);
  const lineCount = lines.length;

  const highlightedHtml = useMemo(
    () => highlightCode(code.replace(/\r\n/g, "\n"), lang),
    [code, lang],
  );

  const layoutClass =
    layout === "fill"
      ? "app-code-editor--fill h-full max-h-full min-h-0"
      : "app-code-editor--fixed h-[min(34rem,calc(100vh-12rem))] max-h-[min(34rem,calc(100vh-12rem))]";

  return (
    <div
      className={`app-code-editor flex flex-col min-h-0 overflow-hidden rounded-lg border border-[#30363d] ${layoutClass} ${className}`}
    >
      <div className="app-code-editor-header flex items-center gap-2 px-3 py-2 shrink-0 border-b border-[#30363d] bg-[#161b22]">
        <span className="text-[11px] font-medium text-[#e6edf3] truncate">{fileName}</span>
        <span className="text-[10px] text-[#8b949e] shrink-0">{langLabel}</span>
        {subtitle && (
          <span className="text-[10px] text-[#8b949e] ml-auto shrink-0">{subtitle}</span>
        )}
        {!subtitle && (
          <span className="text-[10px] text-[#6e7681] ml-auto shrink-0 tabular-nums">
            {lineCount.toLocaleString()} 行
          </span>
        )}
      </div>
      <div className="app-code-editor-body relative flex-1 min-h-0 overflow-auto bg-[#0d1117]">
        <div className="flex min-w-max">
          {lineNumbers && (
            <div
              className="app-code-editor-gutter shrink-0 select-none py-3 pr-2 pl-3 text-right text-[12px] leading-[1.6] text-[#6e7681] font-mono tabular-nums border-r border-[#21262d] bg-[#0d1117]"
              aria-hidden="true"
            >
              {lines.map((_, i) => (
                <div key={i}>{i + 1}</div>
              ))}
            </div>
          )}
          <pre className="app-code-editor-pre flex-1 py-3 px-4 m-0 text-[13px] leading-[1.6] font-mono">
          <code
            className={`hljs language-${lang}`}
            // eslint-disable-next-line react/no-danger -- highlight.js 输出
            dangerouslySetInnerHTML={{ __html: highlightedHtml }}
          />
          </pre>
        </div>
      </div>
    </div>
  );
}
