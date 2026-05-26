"use client";

import Link from "next/link";
import { Suspense } from "react";
import OntologyWorkspace from "../../../../components/ontology/OntologyWorkspace";
import PageHeader from "../../../../components/PageHeader";

export default function KnowledgeBaseOntologyPage({ params }: { params: { id: string } }) {
  const kbId = Number(params.id);

  if (!Number.isFinite(kbId)) {
    return <main className="app-page text-app-secondary">无效的知识库 ID</main>;
  }

  return (
    <main className="app-page flex min-h-0 flex-col">
      <PageHeader
        breadcrumbs={[
          { label: "语义知识库", href: "/knowledge-bases" },
          { label: `知识库 ${kbId}`, href: `/knowledge-bases/${kbId}` },
          { label: "本体浏览" },
        ]}
        title="本体浏览"
        subtitle="从 RDF 生产图浏览业务语义、数据资产、关系图谱；清洗治理与侧栏「本体建模」对应同一能力。"
        actions={
          <Link href={`/knowledge-bases/${kbId}`} className="app-button-secondary app-toolbar-action no-underline">
            返回数据接入
          </Link>
        }
      />
      <div className="mt-4 flex min-h-0 flex-1 flex-col">
        <Suspense fallback={<p className="text-sm text-app-muted">加载中…</p>}>
          <OntologyWorkspace fixedKbId={kbId} />
        </Suspense>
      </div>
    </main>
  );
}
