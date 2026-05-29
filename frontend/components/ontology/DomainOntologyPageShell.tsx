"use client";

import { Suspense, useEffect, useState } from "react";
import PageHeader from "../PageHeader";
import DomainOntologyWorkspace from "./DomainOntologyWorkspace";
import { api } from "../../lib/api";
import {
  getActiveBusinessDomainId,
  getBusinessDomainUpdatedEventName,
} from "../../lib/businessDomain";

function DomainOntologyPageInner() {
  const [domainId, setDomainId] = useState<number | null>(null);
  const [domainName, setDomainName] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [noDomain, setNoDomain] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setNoDomain(false);
      const resolvedId = getActiveBusinessDomainId();
      if (!resolvedId) {
        if (!cancelled) {
          setDomainId(null);
          setNoDomain(true);
          setLoading(false);
        }
        return;
      }
      try {
        const res = await api<{
          domain: { id: number; name: string };
        }>(`/api/business-domains/${resolvedId}`);
        if (cancelled) return;
        setDomainId(resolvedId);
        setDomainName(res.domain.name);
      } catch {
        if (!cancelled) {
          setDomainId(null);
          setNoDomain(true);
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();

    const onDomainUpdated = () => {
      void load();
    };
    window.addEventListener(getBusinessDomainUpdatedEventName(), onDomainUpdated);
    return () => {
      cancelled = true;
      window.removeEventListener(getBusinessDomainUpdatedEventName(), onDomainUpdated);
    };
  }, []);

  if (loading) {
    return (
      <main className="app-page">
        <p className="text-sm text-app-muted">加载语义资产…</p>
      </main>
    );
  }

  if (noDomain || domainId == null) {
    return (
      <main className="app-page">
        <PageHeader breadcrumbs={[{ label: "语义资产" }]} title="语义资产" />
        <div className="app-card mt-4 p-8 text-center">
          <p className="text-sm text-app-secondary">请先在侧栏选择当前业务域。</p>
        </div>
      </main>
    );
  }

  return (
    <main className="app-page flex min-h-0 flex-col">
      <PageHeader
        breadcrumbs={[{ label: "语义资产" }]}
        title="语义资产"
        subtitle={`汇总「${domainName}」五层语义资产（实体概念、关系、规则、属性、词汇），支持追溯来源。`}
      />
      <div className="mt-4 flex min-h-0 flex-1 flex-col">
        <DomainOntologyWorkspace domainId={domainId} domainName={domainName} />
      </div>
    </main>
  );
}

export default function DomainOntologyPageShell() {
  return (
    <Suspense fallback={<main className="app-page text-sm text-app-muted">加载中…</main>}>
      <DomainOntologyPageInner />
    </Suspense>
  );
}
