"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import PageHeader from "../../../../components/PageHeader";
import KbModelingQualitySection from "../../../../components/knowledge-bases/KbModelingQualitySection";
import type { KB, OntologyCleaningResults } from "../../../../components/knowledge-bases/types";
import { api } from "../../../../lib/api";

export default function KnowledgeBaseModelingQualityPage({
  params,
}: {
  params: { id: string };
}) {
  const kbId = Number(params.id);
  const [kb, setKb] = useState<KB | null>(null);
  const [loading, setLoading] = useState(false);
  const [cleaningResults, setCleaningResults] = useState<OntologyCleaningResults | null>(null);
  const [cleaningResultsLoading, setCleaningResultsLoading] = useState(false);

  const loadCleaningResults = useCallback(async () => {
    if (!Number.isFinite(kbId)) return;
    setCleaningResultsLoading(true);
    try {
      const res = await api<OntologyCleaningResults>(
        `/api/ontology/knowledge-bases/${kbId}/ontology-cleaning-results`,
      );
      setCleaningResults(res);
    } catch {
      setCleaningResults(null);
    } finally {
      setCleaningResultsLoading(false);
    }
  }, [kbId]);

  const loadPage = useCallback(async () => {
    if (!Number.isFinite(kbId)) return;
    setLoading(true);
    try {
      const res = await api<{ knowledge_base: KB }>(`/api/knowledge-bases/${kbId}`);
      setKb(res.knowledge_base);
    } catch {
      setKb(null);
    } finally {
      setLoading(false);
    }
  }, [kbId]);

  useEffect(() => {
    void loadPage();
    void loadCleaningResults();
  }, [loadPage, loadCleaningResults]);

  if (!Number.isFinite(kbId)) {
    return <main className="app-page text-app-secondary">无效的知识库 ID</main>;
  }

  if (!loading && !kb) {
    return (
      <main className="app-page">
        <p className="text-app-secondary">知识库不存在或已删除。</p>
        <Link className="app-link mt-2 inline-block" href="/knowledge-bases">
          返回列表
        </Link>
      </main>
    );
  }

  return (
    <main className="app-page">
      <PageHeader
        breadcrumbs={[
          { label: "语义知识库", href: "/knowledge-bases" },
          ...(kb ? [{ label: kb.name, href: `/knowledge-bases/${kb.id}` }] : []),
          { label: "建模与质量" },
        ]}
        title="建模与质量"
        subtitle={kb?.name ? `知识库「${kb.name}」的五层结果、SHACL 与隔离区治理视图。` : undefined}
        actions={
          kb ? (
            <Link href={`/knowledge-bases/${kb.id}`} className="app-button-secondary no-underline">
              返回知识库详情
            </Link>
          ) : undefined
        }
      />

      {loading && <p className="mt-4 text-sm text-app-muted">加载中…</p>}

      {!loading && kb && (
        <section className="mt-6 space-y-4">
          <KbModelingQualitySection
            kbId={kbId}
            cleaningResults={cleaningResults}
            cleaningResultsLoading={cleaningResultsLoading}
            onPipelineChange={loadCleaningResults}
          />
        </section>
      )}
    </main>
  );
}
