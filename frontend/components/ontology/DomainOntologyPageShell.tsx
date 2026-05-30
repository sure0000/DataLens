"use client";

import { Suspense, useEffect, useState } from "react";
import PageHeader from "../PageHeader";
import { useBusinessDomain } from "../../hooks/useBusinessDomain";
import DomainOntologyWorkspace from "./DomainOntologyWorkspace";
import { api } from "../../lib/api";

function DomainOntologyPageInner() {
  const activeDomainId = useBusinessDomain();
  const [domainId, setDomainId] = useState<number | null>(null);
  const [domainName, setDomainName] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [noDomain, setNoDomain] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setNoDomain(false);
      const resolvedId = activeDomainId;
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
    return () => {
      cancelled = true;
    };
  }, [activeDomainId]);

  if (loading) {
    return (
      <div className="app-page">
        <p className="text-sm text-app-muted">加载语义资产…</p>
      </div>
    );
  }

  if (noDomain || domainId == null) {
    return (
      <div className="app-page">
        <PageHeader breadcrumbs={[{ label: "语义资产" }]} title="语义资产" />
        <div className="app-card mt-4 p-8 text-center">
          <p className="text-sm text-app-secondary">请先在侧栏选择当前业务域。</p>
        </div>
      </div>
    );
  }

  return (
    <div className="app-page flex min-h-0 flex-col">
      <PageHeader
        breadcrumbs={[{ label: "语义资产" }]}
        title="语义资产"
        subtitle={`汇总「${domainName}」五层语义资产（实体概念、关系、规则、属性、词汇），支持追溯来源。`}
      />
      <div className="mt-4 flex min-h-0 flex-1 flex-col">
        <DomainOntologyWorkspace domainId={domainId} domainName={domainName} />
      </div>
    </div>
  );
}

export default function DomainOntologyPageShell() {
  return (
    <Suspense fallback={<div className="app-page text-sm text-app-muted">加载中…</div>}>
      <DomainOntologyPageInner />
    </Suspense>
  );
}
