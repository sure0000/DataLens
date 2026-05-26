"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/** 遗留五层详情页 → 重定向到 OntologyWorkspace「清洗治理」Tab */
export default function OntologyLayerRedirectPage({
  params,
}: {
  params: { id: string; layerKey: string };
}) {
  const router = useRouter();
  const kbId = Number(params.id);

  useEffect(() => {
    if (!Number.isFinite(kbId)) return;
    router.replace(`/knowledge-bases/${kbId}/ontology?tab=governance`);
  }, [kbId, router]);

  if (!Number.isFinite(kbId)) {
    return <main className="app-page text-app-secondary">无效的知识库 ID</main>;
  }

  return <main className="app-page text-app-secondary">正在跳转到本体工作台…</main>;
}
