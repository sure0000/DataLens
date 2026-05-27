"use client";

import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import { kbModelingSectionUrl, normalizeModelingLayerKey } from "../../../../../lib/ontologyRoutes";

/** 五层明细深链 → 知识库「建模与质量」页面的五层 Tab */
export default function OntologyLayerDeepLinkPage() {
  const params = useParams();
  const router = useRouter();
  const kbId = Number(params.id);
  const layerKey = normalizeModelingLayerKey(
    typeof params.layerKey === "string" ? params.layerKey : null,
  );

  useEffect(() => {
    if (!Number.isFinite(kbId)) {
      router.replace("/knowledge-bases");
      return;
    }
    const layer = layerKey ?? "vocabulary";
    router.replace(
      kbModelingSectionUrl(kbId, {
        tab: "layers",
        layer: layer === "dimension" ? "dimension" : layer,
      }),
    );
  }, [kbId, layerKey, router]);

  return (
    <main className="app-page text-sm text-app-muted">
      正在打开清洗层明细…
    </main>
  );
}
