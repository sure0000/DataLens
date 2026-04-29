"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Breadcrumbs from "../../../components/Breadcrumbs";

type ChatRecord = {
  id: string;
  question: string;
  sql: string;
  explanation: string;
  created_at: string;
};

const RECORDS_KEY = "chatbi_records";

function CopilotResultContent() {
  const router = useRouter();
  const params = useSearchParams();
  const id = params.get("id") || "";
  const [record, setRecord] = useState<ChatRecord | null>(null);

  useEffect(() => {
    if (!id) {
      setRecord(null);
      return;
    }
    try {
      const raw = localStorage.getItem(RECORDS_KEY);
      const list = raw ? (JSON.parse(raw) as ChatRecord[]) : [];
      setRecord(list.find((x) => x.id === id) || null);
    } catch {
      setRecord(null);
    }
  }, [id]);

  return (
    <main className="app-page">
      <div className="app-page-header mb-4">
        <div>
          <Breadcrumbs items={[{ label: "首页", href: "/" }, { label: "Copilot", href: "/copilot" }, { label: "查询结果" }]} />
          <h1 className="app-page-title">查询结果</h1>
        </div>
        <div className="app-page-header-actions">
          <button className="app-button-secondary" onClick={() => router.push("/copilot")}>
            返回 chatBI
          </button>
        </div>
      </div>

      {!record && <p className="app-card p-4 app-text-secondary-strong text-sm">未找到对应结果，请从 chatBI 页面重新提问。</p>}

      {record && (
        <section className="space-y-4">
          <div className="app-card p-4">
            <p className="app-text-muted text-xs">问题</p>
            <p className="app-text-secondary-strong mt-1 text-sm">{record.question}</p>
          </div>

          <div className="app-card p-4">
            <p className="app-text-muted text-xs">生成 SQL</p>
            <pre className="mt-2 overflow-x-auto rounded bg-[#f3f4f6] p-3 text-xs text-[#111827]">{record.sql || "-- 暂无 SQL 结果 --"}</pre>
          </div>

          <div className="app-card p-4">
            <p className="app-text-muted text-xs">解释</p>
            <p className="app-text-secondary-strong mt-1 text-sm">{record.explanation || "暂无解释内容"}</p>
          </div>

          <p className="app-text-muted text-xs">当前结果为自然语言查询生成结果。如需执行 SQL，可在数据库客户端执行上面的语句。</p>
        </section>
      )}
    </main>
  );
}

export default function CopilotResultPage() {
  return (
    <Suspense fallback={<main className="app-page text-[#6b7280]">加载中...</main>}>
      <CopilotResultContent />
    </Suspense>
  );
}
