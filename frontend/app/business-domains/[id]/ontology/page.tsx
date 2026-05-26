"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import PageHeader from "../../../../components/PageHeader";
import { api } from "../../../../lib/api";

/** 业务域入口：解析绑定的知识库后跳转到知识库「本体建模」Tab */
export default function DomainOntologyPage() {
  const params = useParams();
  const router = useRouter();
  const domainId = String(params.id || "");

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await api<{
          knowledge_bases: { id: number; name: string }[];
        }>(`/api/business-domains/${domainId}`);
        const first = res.knowledge_bases?.[0];
        if (!cancelled && first) {
          router.replace(`/knowledge-bases/${first.id}/ontology`);
        }
      } catch {
        /* 无绑定知识库时留在本页 */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [domainId, router]);

  return (
    <main className="app-page">
      <PageHeader
        title="业务域本体"
        subtitle={`业务域 ${domainId} 的本体数据位于关联知识库的「本体建模」页。若已绑定知识库，将自动跳转。`}
      />
      <div className="app-card mt-4 p-6 text-sm text-app-secondary">
        <p>正在查找该业务域关联的知识库…</p>
        <p className="mt-2 text-app-muted">
          若未自动跳转，请先在业务域设置中绑定知识库，或进入语义知识库详情页切换「本体建模」标签。
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link href="/knowledge-bases" className="app-button no-underline">
            打开语义知识库
          </Link>
          <Link href={`/business-domains/${domainId}`} className="app-button-secondary no-underline">
            返回业务域
          </Link>
        </div>
      </div>
    </main>
  );
}
