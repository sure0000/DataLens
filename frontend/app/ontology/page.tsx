"use client";

import { Suspense } from "react";
import OntologyWorkspace from "../../components/ontology/OntologyWorkspace";
import PageHeader from "../../components/PageHeader";

/** 全局本体浏览入口；建模进度见各知识库详情「建模与质量」 */
export default function OntologyPage() {
  return (
    <main className="app-page flex min-h-0 flex-col">
      <PageHeader
        title="本体浏览"
        subtitle="选择知识库后浏览已入图的术语、指标、数据资产与关系图谱。语义清洗与建模进度请在「数据接入」知识库详情中查看。"
      />
      <div className="mt-4 flex min-h-0 flex-1 flex-col">
        <Suspense fallback={<p className="text-sm text-app-muted">加载中…</p>}>
          <OntologyWorkspace />
        </Suspense>
      </div>
    </main>
  );
}
