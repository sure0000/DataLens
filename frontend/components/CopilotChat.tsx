"use client";

import { useState } from "react";
import { api } from "../lib/api";

type Msg = { q: string; sql: string; explanation: string };

export default function CopilotChat() {
  const [question, setQuestion] = useState("");
  const [tableId, setTableId] = useState<string>("");
  const [messages, setMessages] = useState<Msg[]>([]);

  async function submit() {
    const res = await api<{ sql: string; explanation: string }>("/api/ask", {
      method: "POST",
      body: JSON.stringify({ question, table_id: tableId ? Number(tableId) : null })
    });
    setMessages((m) => [...m, { q: question, sql: res.sql, explanation: res.explanation }]);
    setQuestion("");
  }

  return (
    <div className="grid gap-4">
      <div className="app-toolbar">
        <input
          placeholder="可选 table_id"
          className="app-input w-full sm:w-[180px] sm:flex-none"
          value={tableId}
          onChange={(e) => setTableId(e.target.value)}
        />
        <input
          placeholder="输入问题，比如：最近7天GMV"
          className="app-input app-toolbar-input"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button className="app-button app-toolbar-action" onClick={submit}>
          生成SQL
        </button>
      </div>
      <div className="space-y-3">
        {messages.map((m, i) => (
          <article className="app-card app-card-interactive p-4" key={i}>
            <p className="app-text-muted text-sm">Q: {m.q}</p>
            <pre className="mt-2 overflow-auto rounded-lg bg-slate-900 p-3 text-xs text-slate-100">{m.sql}</pre>
            <p className="app-text-secondary-strong mt-2 text-sm">{m.explanation}</p>
          </article>
        ))}
      </div>
    </div>
  );
}
