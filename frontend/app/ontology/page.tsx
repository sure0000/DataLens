"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** 独立 /ontology 路由：重定向到语义知识库列表 */
export default function OntologyPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/knowledge-bases");
  }, [router]);

  return (
    <main className="app-page">
      <p className="text-sm text-app-muted">本体建模已合并到各知识库详情页，正在跳转…</p>
    </main>
  );
}
