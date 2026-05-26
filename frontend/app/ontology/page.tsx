"use client";

import OntologyWorkspace from "../../components/ontology/OntologyWorkspace";
import PageHeader from "../../components/PageHeader";

/** 全局本体浏览入口 — 与知识库内 /ontology 使用同一工作台 */
export default function OntologyPage() {
  return (
    <main className="app-page flex min-h-0 flex-col">
      <PageHeader
        title="本体浏览"
        subtitle="选择知识库后按总览、业务语义、数据资产、关系图谱、清洗治理与专家视图浏览 RDF。"
      />
      <div className="mt-4 min-h-0 flex-1">
        <OntologyWorkspace />
      </div>
    </main>
  );
}
